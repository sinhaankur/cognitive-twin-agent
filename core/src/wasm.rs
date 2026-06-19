//! WebAssembly bindings — the twin's brain in the browser.
//!
//! Browsers have no raw sockets, so the WASM build exposes the *logic* (persona,
//! routing, system-prompt assembly) to JavaScript; JS does the actual model
//! `fetch`. Same core code as macOS/iOS — only the transport differs.

#![cfg(target_arch = "wasm32")]

use wasm_bindgen::prelude::*;

use crate::persona::Persona;
use crate::router::Router;
use crate::{build_system_prompt, memory};

/// Compile a persona (JSON) into its system-prompt block.
#[wasm_bindgen]
pub fn persona_prompt(persona_json: &str) -> String {
    Persona::from_json(persona_json).to_prompt()
}

/// Build the full system prompt: base + persona + memory summary.
/// `recent_prompts_json` is a JSON array of strings.
#[wasm_bindgen]
pub fn system_prompt(base: &str, persona_json: &str, recent_prompts_json: &str) -> String {
    let recents: Vec<String> = serde_json::from_str(recent_prompts_json).unwrap_or_default();
    build_system_prompt(base, persona_json, &recents)
}

/// Route a prompt against a policy (JSON). Returns a JSON decision string.
#[wasm_bindgen]
pub fn route(policy_json: &str, prompt: &str, device_state: &str) -> String {
    let router = Router::from_json(policy_json);
    let dev = if device_state.is_empty() { None } else { Some(device_state) };
    let d = router.route(prompt, dev);
    serde_json::json!({
        "model": d.model,
        "model_key": d.model_key,
        "rule_id": d.rule_id,
        "complexity": format!("{:?}", d.complexity).to_lowercase(),
        "risk": format!("{:?}", d.risk).to_lowercase(),
    })
    .to_string()
}

/// Private, on-device memory summary from recent prompts (JSON array).
#[wasm_bindgen]
pub fn memory_summary(recent_prompts_json: &str) -> String {
    let recents: Vec<String> = serde_json::from_str(recent_prompts_json).unwrap_or_default();
    memory::summary_for_prompt(&recents)
}
