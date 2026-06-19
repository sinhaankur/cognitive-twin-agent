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
}
