// Live proof: the Rust core talking to a real local Ollama model.
use cognitive_twin_core::{Agent, Persona};
use cognitive_twin_core::llm::OllamaClient;

fn main() {
    let prompt = std::env::args().skip(1).collect::<Vec<_>>().join(" ");
    let prompt = if prompt.is_empty() { "Say hello from the Rust core in one short sentence.".into() } else { prompt };

    let persona = Persona { name: "Ankur".into(), likes: vec!["Rust".into(), "local-first".into()], ..Default::default() };
    let client = OllamaClient::new("qwen2.5:3b");
    let mut agent = Agent::new(client).with_persona(persona);

    match agent.ask(&prompt) {
        Ok(r) => println!("[{}] {}", r.model, r.answer),
        Err(e) => eprintln!("error: {e}"),
    }
}
