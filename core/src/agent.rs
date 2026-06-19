//! The agent — composes persona + memory + router + a model client into one
//! `ask()`. Portable: it owns no I/O beyond the injected `ChatClient`, so the
//! same agent runs on macOS, iOS, and (with a platform client) the web.

use crate::llm::{ChatClient, ChatMessage, LlmError};
use crate::persona::Persona;
use crate::{memory, router::Router};

pub struct Agent<C: ChatClient> {
    client: C,
    base_persona: String,
    persona: Persona,
    /// recent prompts feeding the private memory summary (host-managed history)
    history: Vec<String>,
    router: Option<Router>,
}

pub struct AgentReply {
    pub answer: String,
    pub model: String,
}

impl<C: ChatClient> Agent<C> {
    pub fn new(client: C) -> Self {
        Self {
            client,
            base_persona: default_base_persona(),
            persona: Persona::default(),
            history: Vec::new(),
            router: None,
        }
    }

    pub fn with_base_persona(mut self, base: impl Into<String>) -> Self {
        self.base_persona = base.into();
        self
    }

    pub fn with_persona(mut self, p: Persona) -> Self {
        self.persona = p;
        self
    }

    pub fn with_router(mut self, r: Router) -> Self {
        self.router = Some(r);
        self
    }

    /// Seed prior prompts (e.g. loaded from the on-device memory file).
    pub fn set_history(&mut self, prompts: Vec<String>) {
        self.history = prompts;
    }

    fn system_prompt(&self) -> String {
        let mut parts = vec![self.base_persona.clone()];
        let who = self.persona.to_prompt();
        if !who.is_empty() {
            parts.push(who);
        }
        let ctx = memory::summary_for_prompt(&self.history);
        if !ctx.is_empty() {
            parts.push(ctx);
        }
        parts.join("\n\n")
    }

    /// Ask the twin. Builds the personalized system prompt, optionally routes a
    /// model (advisory — the host decides whether to swap clients), calls the
    /// model, and records the prompt to in-memory history.
    pub fn ask(&mut self, user_input: &str) -> Result<AgentReply, LlmError> {
        let messages = vec![
            ChatMessage::system(self.system_prompt()),
            ChatMessage::user(user_input),
        ];
        let answer = self.client.chat(&messages)?;
        self.history.push(user_input.to_string());
        Ok(AgentReply { answer, model: self.client.model().to_string() })
    }

    /// What the router would pick for this prompt (for UI/telemetry).
    pub fn route_hint(&self, prompt: &str, device: Option<&str>) -> Option<String> {
        self.router.as_ref().map(|r| r.route(prompt, device).model)
    }
}

fn default_base_persona() -> String {
    "You are a local-first personal AI twin — pragmatic, concise, no fluff. \
     Use the user's persona and history to answer as they would. Start with the \
     answer, then trade-offs."
        .into()
}

#[cfg(test)]
mod tests {
    use super::*;

    struct EchoSystem; // returns the system prompt so we can assert composition
    impl ChatClient for EchoSystem {
        fn chat(&self, messages: &[ChatMessage]) -> Result<String, LlmError> {
            Ok(messages
                .iter()
                .find(|m| m.role == "system")
                .map(|m| m.content.clone())
                .unwrap_or_default())
        }
        fn model(&self) -> &str {
            "echo"
        }
    }

    #[test]
    fn ask_composes_persona_and_history() {
        let persona = Persona {
            name: "Ankur".into(),
            likes: vec!["local-first".into()],
            ..Default::default()
        };
        let mut agent = Agent::new(EchoSystem)
            .with_base_persona("BASE")
            .with_persona(persona);
        agent.set_history(vec!["tell me about ollama".into()]);
        let reply = agent.ask("hi").unwrap();
        assert!(reply.answer.contains("BASE"));
        assert!(reply.answer.contains("Ankur") && reply.answer.contains("local-first"));
        assert!(reply.answer.to_lowercase().contains("ollama"));
        assert_eq!(reply.model, "echo");
    }

    #[test]
    fn ask_records_history() {
        let mut agent = Agent::new(EchoSystem);
        agent.ask("first").unwrap();
        agent.ask("second").unwrap();
        // history now feeds the memory summary on the next turn
        let reply = agent.ask("third").unwrap();
        assert!(reply.answer.to_lowercase().contains("recently asked"));
    }
}
