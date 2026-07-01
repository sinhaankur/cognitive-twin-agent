//! Cognitive Twin — portable core.
//!
//! Pure, platform-agnostic logic shared by every front end (macOS, iOS, Windows,
//! Linux, Android, WASM): the persona, local-memory pattern derivation, and the
//! policy-driven model router. Platform shells provide I/O (HTTP, files, audio)
//! and call into this.
//!
//! Two consumption paths:
//!   - Rust/WASM: use the modules directly.
//!   - Swift/C (iOS, macOS): the `ffi` module exposes a tiny C ABI.

pub mod agent;
pub mod llm;
pub mod persona;
pub mod memory;
pub mod router;

#[cfg(target_arch = "wasm32")]
pub mod wasm;

pub use agent::{Agent, AgentReply};
pub use llm::{ChatClient, ChatMessage, LlmError};
pub use memory::{summary_for_prompt, top_topics, Entry};
pub use persona::Persona;
pub use router::{classify, Policy, RouteDecision, Router};

/// Build the full system prompt the way the agent loop does: base persona +
/// the user's persona profile + a private summary of how they behave.
pub fn build_system_prompt(base: &str, persona_json: &str, recent_prompts: &[String]) -> String {
    let mut parts = vec![base.to_string()];
    let who = Persona::from_json(persona_json).to_prompt();
    if !who.is_empty() {
        parts.push(who);
    }
    let ctx = summary_for_prompt(recent_prompts);
    if !ctx.is_empty() {
        parts.push(ctx);
    }
    parts.join("\n\n")
}

/// Build a graph snapshot of how the twin thinks + learns, as JSON.
///
/// Mirrors the Python `cognitive_twin/brain.py`: cognitive faculties are CORE
/// nodes, topics derived from the user's recent prompts are LEARNED nodes, and
/// edges are tagged by provenance (wired / observed). Given a `prompt`, also
/// returns the likely thought-path through the faculties. All local; the host
/// supplies the prompts, this is pure logic.
pub fn brain_graph(recent_prompts: &[String], prompt: &str) -> String {
    // faculties + the role each plays (kept in sync with brain.py)
    let faculties: &[(&str, &str, &str)] = &[
        ("memory", "Memory", "Recalls your recurring interests + recent asks (local log)."),
        ("persona", "Persona", "Who the twin is — the character you shaped."),
        ("soul", "Soul", "An evolving personality + reflections while you're away."),
        ("mood", "Mood", "Colors tone and how warm/measured the answer feels."),
        ("rhythms", "Rhythms", "Time-of-day + life-rhythm awareness."),
        ("activity", "Activity", "Learns how you work by watching your active app (opt-in)."),
        ("voice", "Voice", "Speaks the answer in a loved one's cloned voice, on-device."),
        ("router", "Model router", "Picks the local model that reasons the reply."),
    ];
    let wiring: &[(&str, &str)] = &[
        ("memory", "router"), ("persona", "router"), ("soul", "router"),
        ("mood", "router"), ("rhythms", "router"), ("activity", "memory"),
        ("router", "voice"), ("soul", "mood"), ("rhythms", "mood"),
    ];

    let mut nodes: Vec<serde_json::Value> = Vec::new();
    let mut edges: Vec<serde_json::Value> = Vec::new();
    for (id, label, role) in faculties {
        nodes.push(serde_json::json!({"id": id, "label": label, "kind": "core", "role": role}));
    }
    for (a, b) in wiring {
        edges.push(serde_json::json!({"source": a, "target": b, "kind": "wired"}));
    }

    let topics = top_topics(recent_prompts, 6);
    let n = topics.len().max(1);
    for (i, t) in topics.iter().enumerate() {
        let id = format!("topic:{t}");
        let weight = (1.0 - (i as f64 / n as f64) * 0.5 * 100.0).round() / 100.0;
        nodes.push(serde_json::json!({"id": id, "label": t, "kind": "learned", "weight": weight}));
        edges.push(serde_json::json!({"source": id, "target": "memory", "kind": "observed"}));
    }

    let mut obj = serde_json::json!({
        "nodes": nodes,
        "edges": edges,
        "state": {"memory_count": recent_prompts.len()},
    });
    if !prompt.trim().is_empty() {
        obj["thought_path"] = serde_json::json!({"prompt": prompt, "path": thought_path(prompt)});
    }
    obj.to_string()
}

/// Heuristic ordered faculty path a prompt is likely to route through.
fn thought_path(prompt: &str) -> Vec<&'static str> {
    let p = prompt.to_lowercase();
    let mut path: Vec<&'static str> = vec!["memory", "persona"];
    if ["feel", "sad", "miss", "love", "tired", "happy"].iter().any(|w| p.contains(w)) {
        path.push("mood");
    }
    if ["today", "now", "tonight", "morning", "sleep", "work"].iter().any(|w| p.contains(w)) {
        path.push("rhythms");
    }
    if ["working on", "my app", "my project", "screen", "what am i"].iter().any(|w| p.contains(w)) {
        path.push("activity");
    }
    path.push("router");
    path.push("voice");
    let mut seen = std::collections::BTreeSet::new();
    path.into_iter().filter(|x| seen.insert(*x)).collect()
}

// ---------------------------------------------------------------------------
// C FFI — so Swift (iOS/macOS) and other C callers can use the core. Strings
// cross the boundary as UTF-8 C strings; the caller must free returned strings
// with `ctwin_string_free`.
// ---------------------------------------------------------------------------
#[cfg(not(target_arch = "wasm32"))]
pub mod ffi {
    use super::*;
    use std::ffi::{CStr, CString};
    use std::os::raw::c_char;

    unsafe fn cstr<'a>(p: *const c_char) -> &'a str {
        if p.is_null() {
            return "";
        }
        CStr::from_ptr(p).to_str().unwrap_or("")
    }

    fn out(s: String) -> *mut c_char {
        CString::new(s).unwrap_or_default().into_raw()
    }

    /// Compile a persona (JSON) into its system-prompt block.
    #[no_mangle]
    pub extern "C" fn ctwin_persona_prompt(persona_json: *const c_char) -> *mut c_char {
        let p = Persona::from_json(unsafe { cstr(persona_json) });
        out(p.to_prompt())
    }

    /// Route a prompt against a policy (JSON). Returns a JSON decision:
    /// {"model","model_key","rule_id","complexity","risk"}.
    #[no_mangle]
    pub extern "C" fn ctwin_route(
        policy_json: *const c_char,
        prompt: *const c_char,
        device_state: *const c_char,
    ) -> *mut c_char {
        let router = Router::from_json(unsafe { cstr(policy_json) });
        let dev = unsafe { cstr(device_state) };
        let dev_opt = if dev.is_empty() { None } else { Some(dev) };
        let d = router.route(unsafe { cstr(prompt) }, dev_opt);
        let obj = serde_json::json!({
            "model": d.model,
            "model_key": d.model_key,
            "rule_id": d.rule_id,
            "complexity": format!("{:?}", d.complexity).to_lowercase(),
            "risk": format!("{:?}", d.risk).to_lowercase(),
        });
        out(obj.to_string())
    }

    /// Build the full system prompt (base + persona + memory summary).
    /// `recent_prompts_json` is a JSON array of strings.
    #[no_mangle]
    pub extern "C" fn ctwin_system_prompt(
        base: *const c_char,
        persona_json: *const c_char,
        recent_prompts_json: *const c_char,
    ) -> *mut c_char {
        let recents: Vec<String> =
            serde_json::from_str(unsafe { cstr(recent_prompts_json) }).unwrap_or_default();
        out(build_system_prompt(
            unsafe { cstr(base) },
            unsafe { cstr(persona_json) },
            &recents,
        ))
    }

    /// Run one full agent turn against a local Ollama model and return the
    /// answer. Inputs: model name, persona JSON, recent-prompts JSON array, and
    /// the user's message. Returns the answer text (or an "[error] …" string).
    /// This is the one call an iOS/macOS shell needs to talk to the twin.
    #[no_mangle]
    pub extern "C" fn ctwin_ask(
        model: *const c_char,
        persona_json: *const c_char,
        recent_prompts_json: *const c_char,
        user_input: *const c_char,
    ) -> *mut c_char {
        let model = unsafe { cstr(model) };
        let persona = Persona::from_json(unsafe { cstr(persona_json) });
        let recents: Vec<String> =
            serde_json::from_str(unsafe { cstr(recent_prompts_json) }).unwrap_or_default();
        let input = unsafe { cstr(user_input) };

        let client = llm::OllamaClient::new(if model.is_empty() { "llama3.2" } else { model });
        let mut agent = Agent::new(client).with_persona(persona);
        agent.set_history(recents);
        match agent.ask(input) {
            Ok(reply) => out(reply.answer),
            Err(e) => out(format!("[error] {e}")),
        }
    }

    /// Build a graph snapshot of how the twin thinks + learns (JSON).
    /// `recent_prompts_json` is a JSON array of strings; `prompt` (may be "")
    /// adds the thought-path. Returns the same shape as the desktop /api/brain.
    #[no_mangle]
    pub extern "C" fn ctwin_brain(
        recent_prompts_json: *const c_char,
        prompt: *const c_char,
    ) -> *mut c_char {
        let recents: Vec<String> =
            serde_json::from_str(unsafe { cstr(recent_prompts_json) }).unwrap_or_default();
        out(brain_graph(&recents, unsafe { cstr(prompt) }))
    }

    /// Free a string returned by this library.
    #[no_mangle]
    pub extern "C" fn ctwin_string_free(p: *mut c_char) {
        if !p.is_null() {
            unsafe { drop(CString::from_raw(p)) };
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn system_prompt_combines_all_three() {
        let persona = Persona {
            name: "Ankur".into(),
            likes: vec!["local-first".into()],
            ..Default::default()
        };
        let recents = vec!["tell me about ollama".to_string()];
        let sys = build_system_prompt("BASE", &persona.to_json(), &recents);
        assert!(sys.contains("BASE"));
        assert!(sys.contains("Ankur") && sys.contains("local-first"));
        assert!(sys.to_lowercase().contains("ollama"));
    }

    #[test]
    fn brain_graph_has_core_and_learned() {
        let prompts = vec![
            "how is my portfolio going".to_string(),
            "help with the portfolio redesign".to_string(),
            "prep me for the interview".to_string(),
        ];
        let json = brain_graph(&prompts, "how am I feeling today");
        let v: serde_json::Value = serde_json::from_str(&json).unwrap();
        let nodes = v["nodes"].as_array().unwrap();
        assert!(nodes.iter().any(|n| n["id"] == "router" && n["kind"] == "core"));
        assert!(nodes.iter().any(|n| n["kind"] == "learned" && n["label"] == "portfolio"));
        // thought-path present + includes mood (prompt says "feeling") and rhythms ("today")
        let path = v["thought_path"]["path"].as_array().unwrap();
        let names: Vec<&str> = path.iter().map(|x| x.as_str().unwrap()).collect();
        assert!(names.contains(&"mood") && names.contains(&"rhythms") && names.contains(&"voice"));
    }
}
