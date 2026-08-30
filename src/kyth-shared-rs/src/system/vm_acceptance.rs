//! Pure VM-acceptance policy and output decoders.
//!
//! The guest state machine still owns power, bootc, and smoke-check commands.
//! These functions only validate references and interpret command output.

use serde_json::Value;

pub fn valid_update_ref(value: &str) -> bool {
    value.is_empty() || value.chars().all(|character| character.is_ascii_alphanumeric() || matches!(character, '.' | '_' | '/' | '@' | ':' | '+' | '-'))
}

pub fn booted_digest_from_json(output: &str) -> Option<String> {
    let value = serde_json::from_str::<Value>(output).ok()?;
    let image = value.get("status")?.get("booted")?.get("image")?;
    image.get("imageDigest").and_then(Value::as_str)
        .or_else(|| image.get("image").and_then(|nested| nested.get("imageDigest")).and_then(Value::as_str))
        .filter(|digest| !digest.is_empty())
        .map(str::to_string)
}

pub fn deployment_count_from_json(output: &str) -> usize {
    let Ok(value) = serde_json::from_str::<Value>(output) else { return 0; };
    match value {
        Value::Array(items) => items.len(),
        Value::Object(object) => object.get("deployments").and_then(Value::as_array).map_or(0, Vec::len),
        _ => 0,
    }
}

pub fn acceptance_state_from_text(value: Option<&str>) -> &str {
    match value.map(str::trim).filter(|value| !value.is_empty()) {
        Some("fresh") | None => "fresh",
        Some("update-staged") => "update-staged",
        Some("rollback-staged") => "rollback-staged",
        Some(_) => "unknown",
    }
}

pub fn acceptance_event(phase: &str, detail: &str) -> String {
    format!("KYTH_ACCEPTANCE:{phase}:{}", detail.replace('\n', " "))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn validates_restricted_update_refs() {
        assert!(valid_update_ref(""));
        assert!(valid_update_ref("ghcr.io/kyth-os/kyth:testing@sha256:abc"));
        assert!(!valid_update_ref("ghcr.io/kyth;poweroff"));
        assert!(!valid_update_ref("image with spaces"));
    }

    #[test]
    fn decodes_bootc_and_ostree_shapes() {
        assert_eq!(booted_digest_from_json(r#"{"status":{"booted":{"image":{"imageDigest":"sha256:abc"}}}}"#), Some("sha256:abc".into()));
        assert_eq!(booted_digest_from_json(r#"{"status":{"booted":{"image":{"image":{"imageDigest":"sha256:nested"}}}}}"#), Some("sha256:nested".into()));
        assert_eq!(deployment_count_from_json(r#"[{"id":1},{"id":2}]"#), 2);
        assert_eq!(deployment_count_from_json(r#"{"deployments":[{"id":1}]}"#), 1);
    }

    #[test]
    fn normalizes_state_and_events() {
        assert_eq!(acceptance_state_from_text(None), "fresh");
        assert_eq!(acceptance_state_from_text(Some("bad")), "unknown");
        assert_eq!(acceptance_event("LIVE_READY", "line one\nline two"), "KYTH_ACCEPTANCE:LIVE_READY:line one line two");
    }
}
