//! Model client — the core's link to a local LLM.
//!
//! Transport differs per platform (and WASM can't use std sockets), so the core
//! defines the *shape* of a chat call as a trait. A native implementation
//! (Ollama over HTTP via std) is provided behind `cfg(not(wasm))`; platform
//! shells can supply their own (URLSession on iOS, fetch on web) by implementing
//! `ChatClient`.

use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ChatMessage {
    pub role: String, // system | user | assistant | tool
    #[serde(default)]
    pub content: String,
}

impl ChatMessage {
    pub fn system(s: impl Into<String>) -> Self {
        Self { role: "system".into(), content: s.into() }
    }
    pub fn user(s: impl Into<String>) -> Self {
        Self { role: "user".into(), content: s.into() }
    }
    pub fn assistant(s: impl Into<String>) -> Self {
        Self { role: "assistant".into(), content: s.into() }
    }
}

#[derive(Debug)]
pub enum LlmError {
    Unreachable(String),
    Decode(String),
}

impl std::fmt::Display for LlmError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            LlmError::Unreachable(s) => write!(f, "model unreachable: {s}"),
            LlmError::Decode(s) => write!(f, "bad response: {s}"),
        }
    }
}

impl std::error::Error for LlmError {}

/// Any model transport the agent can use. Implement this for a platform's native
/// HTTP if the built-in client doesn't fit.
pub trait ChatClient {
    fn chat(&self, messages: &[ChatMessage]) -> Result<String, LlmError>;
    fn model(&self) -> &str;
}

// ---------------------------------------------------------------------------
// Native Ollama client (std HTTP). Not built for WASM.
// ---------------------------------------------------------------------------
#[cfg(not(target_arch = "wasm32"))]
pub use native::OllamaClient;

#[cfg(not(target_arch = "wasm32"))]
mod native {
    use super::*;
    use std::io::{Read, Write};
    use std::net::TcpStream;
    use std::time::Duration;

    /// Minimal Ollama client over raw HTTP/1.1 (std only — no external crates,
    /// keeps the core dependency-light and portable). Talks to /api/chat.
    pub struct OllamaClient {
        pub model: String,
        host: String, // e.g. "localhost"
        port: u16,    // e.g. 11434
    }

    impl OllamaClient {
        pub fn new(model: impl Into<String>) -> Self {
            Self::with_host(model, "localhost", 11434)
        }

        pub fn with_host(model: impl Into<String>, host: impl Into<String>, port: u16) -> Self {
            Self { model: model.into(), host: host.into(), port }
        }

        fn post(&self, path: &str, body: &str) -> Result<String, LlmError> {
            let addr = format!("{}:{}", self.host, self.port);
            let mut stream = TcpStream::connect(&addr)
                .map_err(|e| LlmError::Unreachable(format!("connect {addr}: {e}")))?;
            stream
                .set_read_timeout(Some(Duration::from_secs(120)))
                .ok();
            let req = format!(
                "POST {path} HTTP/1.1\r\nHost: {host}\r\nContent-Type: application/json\r\n\
                 Content-Length: {len}\r\nConnection: close\r\n\r\n{body}",
                path = path,
                host = self.host,
                len = body.len(),
                body = body
            );
            stream
                .write_all(req.as_bytes())
                .map_err(|e| LlmError::Unreachable(e.to_string()))?;

            let mut raw = Vec::new();
            stream
                .read_to_end(&mut raw)
                .map_err(|e| LlmError::Unreachable(e.to_string()))?;
            let text = String::from_utf8_lossy(&raw);
            // split headers / body on the blank line
            let body = text
                .split_once("\r\n\r\n")
                .map(|(_, b)| b.to_string())
                .unwrap_or_else(|| text.to_string());
            Ok(body)
        }
    }

    impl ChatClient for OllamaClient {
        fn chat(&self, messages: &[ChatMessage]) -> Result<String, LlmError> {
            let payload = serde_json::json!({
                "model": self.model,
                "messages": messages,
                "stream": false,
            });
            let body = self.post("/api/chat", &payload.to_string())?;
            let v: serde_json::Value =
                serde_json::from_str(&body).map_err(|e| LlmError::Decode(e.to_string()))?;
            let content = v
                .get("message")
                .and_then(|m| m.get("content"))
                .and_then(|c| c.as_str())
                .unwrap_or("")
                .to_string();
            Ok(content)
        }

        fn model(&self) -> &str {
            &self.model
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    struct MockClient;
    impl ChatClient for MockClient {
        fn chat(&self, messages: &[ChatMessage]) -> Result<String, LlmError> {
            // echo the last user message so we can assert wiring
            let last = messages.iter().rev().find(|m| m.role == "user");
            Ok(format!("echo: {}", last.map(|m| m.content.as_str()).unwrap_or("")))
        }
        fn model(&self) -> &str {
            "mock"
        }
    }

    #[test]
    fn chat_client_trait_works() {
        let c = MockClient;
        let out = c.chat(&[ChatMessage::user("hello")]).unwrap();
        assert_eq!(out, "echo: hello");
        assert_eq!(c.model(), "mock");
    }

    #[test]
    fn message_helpers() {
        assert_eq!(ChatMessage::system("x").role, "system");
        assert_eq!(ChatMessage::user("x").role, "user");
    }
}
