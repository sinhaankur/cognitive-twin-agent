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

// A broad stopword set so "learned topics" surface real subjects, not filler.
// Kept in sync with the Python side (cognitive_twin/memory.py) so the twin's
// derived interests are identical across the desktop and native paths.
const STOP: &[&str] = &[
    "the", "a", "an", "and", "or", "but", "if", "so", "as", "of", "to", "in",
    "on", "at", "by", "for", "with", "from", "into", "about", "over", "under",
    "up", "down", "out", "off", "than", "then", "too", "very", "just",
    "i", "me", "my", "mine", "we", "us", "our", "you", "your", "yours", "he",
    "him", "his", "she", "her", "it", "its", "they", "them", "their", "this",
    "that", "these", "those", "who", "whom", "which", "what", "some", "any",
    "each", "every", "all", "both", "few", "more", "most", "other", "such",
    "no", "nor", "not", "only", "own", "same", "one", "ones", "someone",
    "something", "anything", "everything", "thing", "things", "stuff",
    "is", "are", "was", "were", "be", "been", "being", "am", "do", "does",
    "did", "have", "has", "had", "can", "could", "will", "would", "shall",
    "should", "may", "might", "must", "get", "got", "make", "made", "go",
    "goes", "went", "want", "need", "like", "know", "think", "see", "say",
    "said", "give", "tell", "show", "use", "used", "help", "let", "put",
    "take", "find", "come", "look", "feel", "keep", "kind", "sort", "way",
    "how", "why", "when", "where", "whats", "please", "tools", "tool",
    "okay", "yes", "yeah", "hey", "hello", "thanks", "thank",
    "now", "today", "here", "there", "again", "also", "really", "maybe",
    "warm", "line", "good", "nice", "much", "many", "lot", "bit", "little",
];

/// Derive the top recurring topics from a set of prompts.
///
/// Topics favour recurrence and distinctiveness: words are scored by
/// frequency × sqrt(length) so longer, multi-syllable subjects outrank short
/// filler, and when there's enough history we require a word to appear at least
/// twice. Small logs fall back to single occurrences so something honest shows
/// early. Mirrors the Python `patterns()` derivation.
pub fn top_topics(prompts: &[String], limit: usize) -> Vec<String> {
    let mut counts: BTreeMap<String, usize> = BTreeMap::new();
    for p in prompts {
        let lowered = p.to_lowercase().replace('?', " ").replace('/', " ");
        for raw in lowered.split_whitespace() {
            let w: String = raw.chars().filter(|c| c.is_alphanumeric()).collect();
            if w.len() > 3 && !w.chars().all(|c| c.is_ascii_digit()) && !STOP.contains(&w.as_str()) {
                *counts.entry(w).or_insert(0) += 1;
            }
        }
    }
    // Prefer words seen at least twice when there are enough of them.
    let recurring: BTreeMap<String, usize> =
        counts.iter().filter(|(_, &c)| c >= 2).map(|(w, &c)| (w.clone(), c)).collect();
    let pool = if recurring.len() >= 3 { recurring } else { counts };

    let mut v: Vec<(String, usize)> = pool.into_iter().collect();
    // score = frequency × sqrt(length); ties broken alphabetically for stability
    v.sort_by(|a, b| {
        let sa = a.1 as f64 * (a.0.len() as f64).sqrt();
        let sb = b.1 as f64 * (b.0.len() as f64).sqrt();
        sb.partial_cmp(&sa).unwrap_or(std::cmp::Ordering::Equal).then(a.0.cmp(&b.0))
    });
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
