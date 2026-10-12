//! Pure container-wrapper generation.
//!
//! The generated wrapper still performs the existing caller-owned Distrobox
//! checks and launch.  This module only owns deterministic text generation;
//! it never creates a container or executes a command.

/// Validate a value for safe interpolation into the generated bash wrapper.
/// M3: shell metacharacters would allow script injection via --tool etc.
/// Fail-closed rejection: legitimate tool/box names never need these.
fn validate_shell_token(name: &str, value: &str) -> Result<(), String> {
    if value.is_empty() {
        return Err(format!("{name} must not be empty"));
    }
    for ch in value.chars() {
        if matches!(
            ch,
            '"' | '\''
                | '`'
                | '$'
                | '\\'
                | ';'
                | '|'
                | '&'
                | '<'
                | '>'
                | '('
                | ')'
                | '{'
                | '}'
                | '!'
                | '*'
                | '?'
                | '#'
                | '~'
                | '\n'
                | '\r'
        ) || ch.is_control()
        {
            return Err(format!("{name} contains forbidden character: {ch:?}"));
        }
    }
    Ok(())
}

/// Render the wrapper used for tools managed in the Kyth AI developer box.
pub fn render_distrobox_wrapper(
    tool: &str,
    description: &str,
    box_name: &str,
) -> Result<String, String> {
    validate_shell_token("tool", tool)?;
    validate_shell_token("description", description)?;
    validate_shell_token("box_name", box_name)?;
    Ok(format!(
        "#!/usr/bin/env bash\nset -euo pipefail\n\ntool=\"{tool}\"\ndesc=\"{description}\"\nbox=\"${{KYTH_AI_DEV_BOX:-{box_name}}}\"\n\nif [[ -x \"${{HOME}}/.local/bin/${{tool}}\" ]]; then\n\texec \"${{HOME}}/.local/bin/${{tool}}\" \"$@\"\nfi\n\nif command -v distrobox >/dev/null 2>&1 && distrobox list --no-color 2>/dev/null | awk '{{print $3}}' | grep -qx \"${{box}}\"; then\n\texec distrobox enter \"${{box}}\" -- \"${{tool}}\" \"$@\"\nfi\n\necho \"${{desc}} is managed in the KythOS AI Developer container (${{box}}).\"\necho \"Initializing ${{box}} environment...\"\nkyth-ai-dev setup\nexec distrobox enter \"${{box}}\" -- \"${{tool}}\" \"$@\"\n",
        tool = tool,
        description = description,
        box_name = box_name,
    ))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn wrapper_is_deterministic_and_uses_runtime_box_override() {
        let wrapper = render_distrobox_wrapper("ollama", "Ollama", "kyth-ai-dev").unwrap();
        assert!(wrapper.starts_with("#!/usr/bin/env bash\nset -euo pipefail\n"));
        assert!(wrapper.contains("box=\"${KYTH_AI_DEV_BOX:-kyth-ai-dev}\""));
        assert!(wrapper.contains("distrobox enter \"${box}\" -- \"${tool}\" \"$@\""));
        assert_eq!(
            wrapper,
            render_distrobox_wrapper("ollama", "Ollama", "kyth-ai-dev").unwrap()
        );
    }

    #[test]
    fn rejects_shell_metacharacters_in_every_field() {
        // M3: shell metacharacters in any field would allow script injection.
        let payloads = [
            "tool\"; evil #",
            "tool$(evil)",
            "tool`evil`",
            "tool;evil",
            "tool|evil",
            "tool&evil",
            "tool\nevil",
            "tool\revil",
            "tool*",
            "tool?",
        ];
        for payload in payloads {
            assert!(
                render_distrobox_wrapper(payload, "Desc", "box").is_err(),
                "tool accepted: {payload:?}"
            );
            assert!(
                render_distrobox_wrapper("tool", payload, "box").is_err(),
                "description accepted: {payload:?}"
            );
            assert!(
                render_distrobox_wrapper("tool", "Desc", payload).is_err(),
                "box_name accepted: {payload:?}"
            );
        }
    }

    #[test]
    fn rejects_empty_fields() {
        assert!(render_distrobox_wrapper("", "Desc", "box").is_err());
        assert!(render_distrobox_wrapper("tool", "", "box").is_err());
        assert!(render_distrobox_wrapper("tool", "Desc", "").is_err());
    }

    #[test]
    fn accepts_realistic_values() {
        assert!(render_distrobox_wrapper("ollama", "Ollama LLM", "kyth-ai-dev").is_ok());
        assert!(render_distrobox_wrapper("code-1.2.3", "VS Code 1.2.3", "dev-box_2").is_ok());
    }
}
