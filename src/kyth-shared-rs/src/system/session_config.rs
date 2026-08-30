//! Pure user-session configuration transforms.

/// Set VS Code's password store without preserving malformed/non-object JSON.
pub fn update_code_argv(raw: Option<&str>) -> String {
    let mut value = raw.and_then(|raw| serde_json::from_str::<serde_json::Value>(raw).ok()).filter(serde_json::Value::is_object).unwrap_or_else(|| serde_json::json!({}));
    value.as_object_mut().unwrap().insert("password-store".into(), serde_json::Value::String("kwallet5".into()));
    format!("{}\n", serde_json::to_string_pretty(&value).expect("JSON object serializes"))
}

/// Replace an existing Chromium/Brave password-store flag, or append one.
pub fn update_chromium_flags(raw: Option<&str>) -> String {
    let mut updated = Vec::new();
    let mut wrote = false;
    for line in raw.unwrap_or_default().lines() {
        let stripped = line.trim();
        if stripped.starts_with("--password-store=") || stripped.starts_with("password-store=") {
            if !wrote { updated.push("--password-store=kwallet5".to_string()); wrote = true; }
        } else {
            updated.push(line.to_string());
        }
    }
    if !wrote { updated.push("--password-store=kwallet5".into()); }
    format!("{}\n", updated.join("\n").trim_end())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn updates_code_json_and_recovers_from_malformed_input() {
        assert!(update_code_argv(Some(r#"{"theme":"dark"}"#)).contains("\"password-store\": \"kwallet5\""));
        assert_eq!(update_code_argv(Some("bad json")), "{\n  \"password-store\": \"kwallet5\"\n}\n");
    }

    #[test]
    fn de_duplicates_chromium_password_store_flags() {
        let output = update_chromium_flags(Some("--foo\n--password-store=basic\npassword-store=old\n"));
        assert_eq!(output.matches("password-store=").count(), 1);
        assert!(output.contains("--password-store=kwallet5"));
    }
}
