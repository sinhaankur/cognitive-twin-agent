//! Local memory — recurring-topic patterns from past prompts. Pure logic; the
//! host (each platform) owns where the JSONL actually lives. Mirrors the Python
//! memory's pattern derivation so the twin reasons with awareness of habits.

use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Entry {
    pub ts: String,
    pub prompt: String,
    #[serde(default)]
    pub gist: String,
    #[serde(default)]
    pub model: Option<String>,
}

const STOP: &[&str] = &[
    "the", "a", "an", "to", "of", "and", "or", "is", "are", "was", "in", "on",
    "for", "my", "me", "i", "you", "it", "this", "that", "what", "how", "do",
    "can", "with", "your", "please", "give", "tell", "show", "use", "tools",
];

/// Derive the top recurring topics from a set of prompts (most frequent first).
pub fn top_topics(prompts: &[String], limit: usize) -> Vec<String> {
    let mut counts: BTreeMap<String, usize> = BTreeMap::new();
    for p in prompts {
        for raw in p.to_lowercase().replace('?', " ").split_whitespace() {
            let w: String = raw.chars().filter(|c| c.is_alphanumeric()).collect();
            if w.len() > 2 && !STOP.contains(&w.as_str()) {
                *counts.entry(w).or_insert(0) += 1;
            }
        }
    }
    let mut v: Vec<(String, usize)> = counts.into_iter().collect();
    v.sort_by(|a, b| b.1.cmp(&a.1).then(a.0.cmp(&b.0)));
    v.into_iter().take(limit).map(|(w, _)| w).collect()
}

/// A short, private summary line to fold into the system prompt.
pub fn summary_for_prompt(prompts: &[String]) -> String {
    if prompts.is_empty() {
        return String::new();
    }
    let topics = top_topics(prompts, 6);
    let mut bits = Vec::new();
    if !topics.is_empty() {
        bits.push(format!("recurring interests: {}", topics.join(", ")));
    }
    let recent: Vec<String> = prompts.iter().rev().take(3).cloned().collect();
    if !recent.is_empty() {
        bits.push(format!("recently asked: {}", recent.join(" / ")));
    }
    format!(
        "Context about this user (from local history, private): {}.",
        bits.join("; ")
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn topics_rank_by_frequency() {
        let prompts = vec![
            "how do I use rust traits".to_string(),
            "rust borrow checker help".to_string(),
            "what about rust async".to_string(),
        ];
        let topics = top_topics(&prompts, 5);
        assert_eq!(topics.first().map(String::as_str), Some("rust"));
    }

    #[test]
    fn summary_mentions_topics() {
        let prompts = vec!["tell me about ollama".to_string(), "ollama models".to_string()];
        assert!(summary_for_prompt(&prompts).to_lowercase().contains("ollama"));
    }

    #[test]
    fn empty_is_empty() {
        assert!(summary_for_prompt(&[]).is_empty());
    }
}
