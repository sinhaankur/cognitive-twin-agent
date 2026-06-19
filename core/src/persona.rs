//! Persona — who the twin is. The thing that makes this *your* twin.
//!
//! Pure data + prompt compilation; no I/O, so it works identically on every
//! platform. Mirrors the Python `cognitive_twin.persona.Persona`.

use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
#[serde(default)]
pub struct Persona {
    pub name: String,
    pub about: String,
    pub traits: Vec<String>,
    pub likes: Vec<String>,
    pub dislikes: Vec<String>,
    pub values: Vec<String>,
    pub style: String,
    pub expertise: Vec<String>,
}

impl Persona {
    pub fn is_empty(&self) -> bool {
        self.name.is_empty()
            && self.about.is_empty()
            && self.traits.is_empty()
            && self.likes.is_empty()
            && self.dislikes.is_empty()
            && self.values.is_empty()
            && self.style.is_empty()
            && self.expertise.is_empty()
    }

    /// Compile into a system-prompt block written in the twin's voice.
    pub fn to_prompt(&self) -> String {
        if self.is_empty() {
            return String::new();
        }
        let mut lines: Vec<String> = vec!["# WHO YOU ARE (your persona)".into()];
        if !self.name.is_empty() {
            lines.push(format!(
                "You are {}'s digital twin — reason, decide, and speak as {} would.",
                self.name, self.name
            ));
        }
        if !self.about.is_empty() {
            lines.push(self.about.clone());
        }
        if !self.traits.is_empty() {
            lines.push(format!("Personality: {}.", self.traits.join(", ")));
        }
        if !self.values.is_empty() {
            lines.push(format!("You care about: {}.", self.values.join(", ")));
        }
        if !self.likes.is_empty() {
            lines.push(format!("You like: {}.", self.likes.join(", ")));
        }
        if !self.dislikes.is_empty() {
            lines.push(format!("You dislike: {}.", self.dislikes.join(", ")));
        }
        if !self.expertise.is_empty() {
            lines.push(format!("Your areas of depth: {}.", self.expertise.join(", ")));
        }
        if !self.style.is_empty() {
            lines.push(format!("Communication style: {}", self.style));
        }
        lines.push(
            "Stay in character. Reflect these preferences in what you recommend and \
             how you say it — never a generic assistant."
                .into(),
        );
        lines.join("\n")
    }

    pub fn from_json(s: &str) -> Self {
        serde_json::from_str(s).unwrap_or_default()
    }

    pub fn to_json(&self) -> String {
        serde_json::to_string_pretty(self).unwrap_or_else(|_| "{}".into())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn empty_persona_has_no_prompt() {
        assert!(Persona::default().to_prompt().is_empty());
        assert!(Persona::default().is_empty());
    }

    #[test]
    fn compiles_likes_dislikes_values() {
        let p = Persona {
            name: "Ankur".into(),
            likes: vec!["Rust".into(), "local-first".into()],
            dislikes: vec!["hype".into()],
            values: vec!["privacy".into()],
            ..Default::default()
        };
        let out = p.to_prompt();
        assert!(out.contains("Ankur"));
        assert!(out.contains("Rust"));
        assert!(out.contains("privacy"));
        assert!(out.contains("hype"));
    }

    #[test]
    fn json_roundtrip() {
        let p = Persona { name: "Test".into(), traits: vec!["calm".into()], ..Default::default() };
        let restored = Persona::from_json(&p.to_json());
        assert_eq!(restored.name, "Test");
        assert_eq!(restored.traits, vec!["calm".to_string()]);
    }
}
