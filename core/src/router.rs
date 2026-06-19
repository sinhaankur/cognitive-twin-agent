//! Policy-driven model routing — pure logic, no I/O. Mirrors the Python router:
//! classify a prompt into (complexity, risk) with a transparent heuristic, then
//! pick a local model from the first matching policy rule.

use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Level {
    Low,
    Medium,
    High,
}

impl Level {
    fn as_str(self) -> &'static str {
        match self {
            Level::Low => "low",
            Level::Medium => "medium",
            Level::High => "high",
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ModelEntry {
    pub name: String,
    #[serde(default)]
    pub provider: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct When {
    #[serde(default, rename = "taskComplexity")]
    pub task_complexity: Vec<String>,
    #[serde(default, rename = "riskLevel")]
    pub risk_level: Vec<String>,
    #[serde(default, rename = "deviceState")]
    pub device_state: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Rule {
    pub id: String,
    #[serde(default)]
    pub when: When,
    #[serde(rename = "useModel")]
    pub use_model: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Policy {
    #[serde(default)]
    pub models: std::collections::BTreeMap<String, ModelEntry>,
    #[serde(default, rename = "routingRules")]
    pub routing_rules: Vec<Rule>,
}

impl Default for Policy {
    fn default() -> Self {
        let mut models = std::collections::BTreeMap::new();
        models.insert(
            "primary".into(),
            ModelEntry { name: "llama3.2".into(), provider: "ollama".into() },
        );
        Policy {
            models,
            routing_rules: vec![Rule {
                id: "rule_default".into(),
                when: When::default(),
                use_model: "primary".into(),
            }],
        }
    }
}

#[derive(Debug, Clone)]
pub struct RouteDecision {
    pub model: String,
    pub model_key: String,
    pub rule_id: String,
    pub complexity: Level,
    pub risk: Level,
}

const HIGH_RISK: &[&str] = &[
    "delete", "remove", "drop", "deploy", "migrat", "overwrit", "rm ", "sudo",
    "push", "force", "production", "prod", "credential", "password", "secret",
    "payment", "transfer", "wipe", "reset",
];
const HIGH_COMPLEXITY: &[&str] = &[
    "plan", "architect", "design", "analyze", "analyse", "compare", "trade-off",
    "tradeoff", "strateg", "why", "debug", "root cause", "refactor", "step by step",
    "reason",
];

/// Heuristic classification: length + keyword cues. Honest, inspectable.
pub fn classify(prompt: &str) -> (Level, Level) {
    let text = prompt.to_lowercase();
    let words = text.split_whitespace().count();

    let risk = if HIGH_RISK.iter().any(|k| text.contains(k)) {
        Level::High
    } else {
        Level::Low
    };

    let complexity = if words >= 60 || HIGH_COMPLEXITY.iter().any(|k| text.contains(k)) {
        Level::High
    } else if words >= 18 {
        Level::Medium
    } else {
        Level::Low
    };

    (complexity, risk)
}

pub struct Router {
    policy: Policy,
}

impl Router {
    pub fn new(policy: Policy) -> Self {
        Router { policy }
    }

    pub fn from_json(s: &str) -> Self {
        Router::new(serde_json::from_str(s).unwrap_or_default())
    }

    fn rule_matches(when: &When, c: Level, r: Level, device: Option<&str>) -> bool {
        if !when.task_complexity.is_empty()
            && !when.task_complexity.iter().any(|x| x == c.as_str())
        {
            return false;
        }
        if !when.risk_level.is_empty() && !when.risk_level.iter().any(|x| x == r.as_str()) {
            return false;
        }
        if !when.device_state.is_empty() {
            match device {
                Some(d) if when.device_state.iter().any(|x| x == d) => {}
                _ => return false,
            }
        }
        true
    }

    fn resolve(&self, key: &str) -> (String, String) {
        if let Some(e) = self.policy.models.get(key) {
            return (key.to_string(), e.name.clone());
        }
        if let Some((k, e)) = self.policy.models.iter().next() {
            return (k.clone(), e.name.clone());
        }
        ("default".into(), "llama3.2".into())
    }

    pub fn route(&self, prompt: &str, device_state: Option<&str>) -> RouteDecision {
        let (complexity, risk) = classify(prompt);
        let mut key: Option<String> = None;
        let mut rule_id = "none".to_string();
        for rule in &self.policy.routing_rules {
            if Self::rule_matches(&rule.when, complexity, risk, device_state) {
                key = Some(rule.use_model.clone());
                rule_id = rule.id.clone();
                break;
            }
        }
        let key = key.unwrap_or_else(|| {
            self.policy.models.keys().next().cloned().unwrap_or_else(|| "primary".into())
        });
        let (model_key, model) = self.resolve(&key);
        RouteDecision { model, model_key, rule_id, complexity, risk }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn test_policy() -> Policy {
        serde_json::from_str(
            r#"{
              "models": {
                "primary": {"name": "qwen3:14b", "provider": "ollama"},
                "fastFallback": {"name": "qwen3:8b", "provider": "ollama"},
                "deepPlanner": {"name": "deepseek-r1", "provider": "ollama"}
              },
              "routingRules": [
                {"id": "rule_low_power", "when": {"deviceState": ["battery_saver"]}, "useModel": "fastFallback"},
                {"id": "rule_high_risk", "when": {"riskLevel": ["high"]}, "useModel": "deepPlanner"},
                {"id": "rule_deep_path", "when": {"taskComplexity": ["high"]}, "useModel": "deepPlanner"},
                {"id": "rule_fast_path", "when": {"taskComplexity": ["low","medium"], "riskLevel": ["low","medium"]}, "useModel": "primary"},
                {"id": "rule_default", "when": {}, "useModel": "primary"}
              ]
            }"#,
        )
        .unwrap()
    }

    #[test]
    fn simple_goes_fast_path() {
        let r = Router::new(test_policy());
        let d = r.route("what's the date?", None);
        assert_eq!(d.rule_id, "rule_fast_path");
        assert_eq!(d.model, "qwen3:14b");
    }

    #[test]
    fn short_destructive_escalates() {
        let r = Router::new(test_policy());
        let d = r.route("delete the production database", None);
        assert_eq!(d.risk, Level::High);
        assert_eq!(d.rule_id, "rule_high_risk");
        assert_eq!(d.model, "deepseek-r1");
    }

    #[test]
    fn battery_overrides() {
        let r = Router::new(test_policy());
        let d = r.route("what's the date?", Some("battery_saver"));
        assert_eq!(d.rule_id, "rule_low_power");
        assert_eq!(d.model, "qwen3:8b");
    }

    #[test]
    fn never_falls_through() {
        let r = Router::new(test_policy());
        for p in ["hi", "explain why in detail", "rm -rf the server", "summarize my day"] {
            let d = r.route(p, None);
            assert_ne!(d.rule_id, "none");
        }
    }
}
