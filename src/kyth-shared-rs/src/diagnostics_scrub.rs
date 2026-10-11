//! Port of `kyth_shared.diagnostics_scrub`.
//!
//! This is intentionally a pure text transform. It does not collect
//! diagnostics or upload anything; it is the final safety boundary before a
//! report is handed to a browser or another public destination.

use regex::Regex;
use std::net::IpAddr;
use std::sync::OnceLock;

/// Compiled scrub patterns, initialized once. The dynamic hostname/username
/// patterns stay per-call (env-dependent); everything else is static.
struct ScrubPatterns {
    private_key: Regex,
    auth_value: Regex,
    sensitive_header: Regex,
    secret_value: Regex,
    secret_flag: Regex,
    secret_query: Regex,
    url_credentials: Regex,
    github_token: Regex,
    aws_key: Regex,
    slack_token: Regex,
    age_key: Regex,
    mac: Regex,
    ipv4: Regex,
    ipv6_candidate: Regex,
    email: Regex,
    uuid: Regex,
    home_path: Regex,
}

fn patterns() -> &'static ScrubPatterns {
    static PATTERNS: OnceLock<ScrubPatterns> = OnceLock::new();
    PATTERNS.get_or_init(|| ScrubPatterns {
        private_key: Regex::new(
            r"(?s)-----BEGIN [^-\r\n]*PRIVATE KEY-----.*?-----END [^-\r\n]*PRIVATE KEY-----",
        )
        .expect("private-key regex is valid"),
        auth_value: Regex::new(
            r"(?i)(\b(?:authorization|proxy-authorization)\s*[:=]\s*)(?:bearer|basic|token)\s+\S+",
        )
        .expect("auth regex is valid"),
        sensitive_header: Regex::new(
            r"(?im)(\b(?:authorization|proxy-authorization|cookie|set-cookie|x-auth-token)\s*[:=]\s*)[^\r\n]+",
        )
        .expect("header regex is valid"),
        secret_value: Regex::new(
            r#"(?i)(["']?(?:access[_-]?token|refresh[_-]?token|id[_-]?token|bearer|password|passwd|passphrase|client[_-]?secret|api[_-]?key|private[_-]?key|auth[_-]?cookie|session[_-]?cookie|cookie|secret)["']?\s*[:=]\s*)("[^"\r\n]*"|'[^'\r\n]*'|[^\s,;&]+)"#,
        )
        .expect("secret-value regex is valid"),
        secret_flag: Regex::new(
            r"(?i)(--(?:cookie|password|passwd|token|client-secret|api-key)(?:=|\s+))\S+",
        )
        .expect("secret-flag regex is valid"),
        secret_query: Regex::new(
            r"(?i)([?&](?:access_token|refresh_token|id_token|token|password|passwd|secret|cookie|api_key|client_secret)=)[^&#\s]+",
        )
        .expect("secret-query regex is valid"),
        url_credentials: Regex::new(r"(?i)(\b[a-z][a-z0-9+.-]*://)[^/@\s:]+:[^/@\s]+@")
            .expect("URL regex is valid"),
        // Bare high-entropy tokens with no key= prefix (H1): common in command
        // output, URLs, and error dumps. Format-based, not name-based.
        github_token: Regex::new(
            r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9_]{36,}\b|\bgithub_pat_[A-Za-z0-9_]{80,}\b",
        )
        .expect("github-token regex is valid"),
        aws_key: Regex::new(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")
            .expect("aws-key regex is valid"),
        slack_token: Regex::new(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b")
            .expect("slack-token regex is valid"),
        age_key: Regex::new(r"\bAGE-SECRET-KEY-1[0-9A-Z]{58}\b")
            .expect("age-key regex is valid"),
        mac: Regex::new(r"[0-9a-fA-F]{2}(:[0-9a-fA-F]{2}){5}")
            .expect("MAC regex is valid"),
        ipv4: Regex::new(r"\b\d{1,3}(?:\.\d{1,3}){3}\b")
            .expect("IPv4 regex is valid"),
        ipv6_candidate: Regex::new(r"(?:[0-9A-Fa-f]*:){2,}[0-9A-Fa-f]*")
            .expect("IPv6 regex is valid"),
        email: Regex::new(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
            .expect("email regex is valid"),
        uuid: Regex::new(
            r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b",
        )
        .expect("UUID regex is valid"),
        home_path: Regex::new(r"/(var/home|home)/[^/\s:]+")
            .expect("home-path regex is valid"),
    })
}

fn replace_with<F>(regex: &Regex, text: String, replacement: F) -> String
where
    F: Fn(&regex::Captures<'_>) -> String,
{
    regex.replace_all(&text, replacement).into_owned()
}

/// Hostname candidates to redact. Python uses `socket.gethostname()`
/// unconditionally; $HOSTNAME is additionally honored when set because a
/// container override can carry a sensitive name the kernel does not know.
/// Redacting both is fail-safe: at worst an extra token is masked.
fn hostnames_to_redact() -> Vec<String> {
    let mut names = Vec::new();
    if let Ok(value) = std::env::var("HOSTNAME") {
        if value.len() > 2 {
            names.push(value);
        }
    }
    let mut buffer = vec![0 as libc::c_char; 256];
    let ok = unsafe { libc::gethostname(buffer.as_mut_ptr(), buffer.len()) } == 0;
    if ok {
        let length = buffer
            .iter()
            .position(|byte| *byte == 0)
            .unwrap_or(buffer.len());
        if let Ok(host) =
            String::from_utf8(buffer[..length].iter().map(|byte| *byte as u8).collect())
        {
            if !names.contains(&host) {
                names.push(host);
            }
        }
    }
    names
}

pub fn scrub_logs(text: &str) -> String {
    let p = patterns();

    let mut text = p
        .private_key
        .replace_all(text, "[private key redacted]")
        .into_owned();
    text = p.auth_value.replace_all(&text, "$1[redacted]").into_owned();
    text = p
        .sensitive_header
        .replace_all(&text, "$1[redacted]")
        .into_owned();
    text = replace_with(&p.secret_value, text, |captures| {
        let value = captures.get(2).map_or("", |match_| match_.as_str());
        let replacement = if value.starts_with('"') {
            "\"[redacted]\""
        } else if value.starts_with('\'') {
            "'[redacted]'"
        } else {
            "[redacted]"
        };
        format!("{}{}", &captures[1], replacement)
    });
    text = p
        .secret_flag
        .replace_all(&text, "$1[redacted]")
        .into_owned();
    text = p
        .secret_query
        .replace_all(&text, "$1[redacted]")
        .into_owned();
    text = p
        .url_credentials
        .replace_all(&text, "$1[credentials-redacted]@")
        .into_owned();
    // Bare format-based tokens (H1): redact even with no key= prefix.
    text = p
        .github_token
        .replace_all(&text, "[github token redacted]")
        .into_owned();
    text = p
        .aws_key
        .replace_all(&text, "[aws key redacted]")
        .into_owned();
    text = p
        .slack_token
        .replace_all(&text, "[slack token redacted]")
        .into_owned();
    text = p
        .age_key
        .replace_all(&text, "[age key redacted]")
        .into_owned();

    for (pattern, replacement) in [
        (r"(?i)hostname[:=]\s*\S+", "hostname=redacted"),
        (r"(?i)serial[:=]\s*\S+", "serial=redacted"),
        (r"(?i)Serial\s*[:=]\s*\S+", "Serial: [scrubbed]"),
        (r"(?i)SSID[:=]\s*\S+", "SSID=redacted"),
        (r"(?i)SSID\s*[:=]\s*\S+", "SSID: [scrubbed]"),
    ] {
        text = Regex::new(pattern)
            .expect("identity regex is valid")
            .replace_all(&text, replacement)
            .into_owned();
    }

    text = p.mac.replace_all(&text, "xx:xx:xx:xx:xx:xx").into_owned();
    text = p.ipv4.replace_all(&text, "xxx.xxx.xxx.xxx").into_owned();

    // Rust's regex crate deliberately has no look-around. The broad match
    // still mirrors the Python candidate for normal IPv6 literals, and the
    // parser prevents ordinary colon-separated text from being redacted.
    text = replace_with(&p.ipv6_candidate, text, |captures| {
        let candidate = captures.get(0).map_or("", |match_| match_.as_str());
        if candidate
            .parse::<IpAddr>()
            .is_ok_and(|address| address.is_ipv6())
        {
            "xxxx:xxxx:xxxx:xxxx::xxxx".to_string()
        } else {
            candidate.to_string()
        }
    });
    text = p
        .email
        .replace_all(&text, "redacted@example.com")
        .into_owned();
    text = p
        .uuid
        .replace_all(&text, "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx")
        .into_owned();
    text = p.home_path.replace_all(&text, "/$1/redacted").into_owned();

    // The Python implementation uses the current hostname and USER as final
    // fallbacks. Python resolves the hostname via gethostname(2), which
    // always works; reading only $HOSTNAME would silently skip hostname
    // redaction under systemd units where that variable is unset.
    for host in hostnames_to_redact() {
        let escaped = regex::escape(&host);
        if let Ok(pattern) = Regex::new(&format!(r"\b{escaped}\b")) {
            text = pattern.replace_all(&text, "[hostname]").into_owned();
        }
    }
    for key in ["USER", "USERNAME"] {
        if let Ok(value) = std::env::var(key) {
            if value.len() > 1 {
                let escaped = regex::escape(&value);
                if let Ok(pattern) = Regex::new(&format!(r"\b{escaped}\b")) {
                    text = pattern.replace_all(&text, "redacted").into_owned();
                }
            }
        }
    }
    text
}

#[cfg(test)]
mod tests {
    use super::scrub_logs;

    /// Serializes the tests that mutate process-global environment variables.
    /// Rust runs `#[test]` functions on threads in one process, so one test's
    /// `set_var("HOSTNAME", …)` races with another's `remove_var("HOSTNAME")`
    /// and `scrub_logs` can observe the wrong value (CI failure 34830418072:
    /// `hostname_env_is_redacted` saw HOSTNAME removed mid-test).
    static ENV_LOCK: std::sync::Mutex<()> = std::sync::Mutex::new(());

    fn lock_env() -> std::sync::MutexGuard<'static, ()> {
        ENV_LOCK
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner())
    }

    #[test]
    fn redacts_credentials_and_structured_secrets() {
        let report = concat!(
            "Authorization: Bearer bearer-secret\n",
            "Cookie: session=browser-secret; theme=dark\n",
            "oauth={\"access_token\":\"access-secret\",\"refresh_token\":\"refresh-secret\"}\n",
            "password=hunter2 api_key=api-secret\n",
            "command --cookie cli-secret --token=flag-secret\n",
        );
        let scrubbed = scrub_logs(&report);
        for secret in [
            "bearer-secret",
            "browser-secret",
            "access-secret",
            "refresh-secret",
            "hunter2",
            "api-secret",
            "cli-secret",
            "flag-secret",
        ] {
            assert!(!scrubbed.contains(secret), "secret leaked: {secret}");
        }
    }

    #[test]
    fn redacts_keys_urls_network_ids_and_paths() {
        let key_begin = "-----BEGIN ".to_owned() + "PRIVATE KEY-----";
        let key_end = "-----END ".to_owned() + "PRIVATE KEY-----";
        let report = format!(
            "{key_begin}\nprivate-material\n{key_end}\n{}{}{}",
            "https://alice:password@example.test/path?access_token=query-secret&safe=yes\n",
            "IPv6 2001:db8:85a3::8a2e:370:7334 IPv4 192.0.2.10\n",
            "home=/var/home/alice/project\n",
        );
        let scrubbed = scrub_logs(&report);
        for secret in [
            "private-material",
            "alice:password",
            "query-secret",
            "2001:db8:85a3::8a2e:370:7334",
            "192.0.2.10",
            "/var/home/alice",
        ] {
            assert!(!scrubbed.contains(secret), "secret leaked: {secret}");
        }
    }

    #[test]
    fn preserves_non_sensitive_text() {
        let scrubbed = scrub_logs("plain status: ok\nvalue=42");
        assert_eq!(scrubbed, "plain status: ok\nvalue=42");
    }

    #[test]
    fn redacts_bare_format_based_tokens() {
        // H1: bare high-entropy tokens with no key= prefix must be redacted.
        // Test tokens are built via concat! to avoid tripping secret scanners
        // on literal credential-shaped strings.
        let ghp = concat!("ghp_", "abcdefghijklmnopqrstuvwxyz0123456789ABCD");
        let akia = concat!("AKIA", "IOSFODNN7EXAMPLE");
        let xoxb = concat!("xoxb-", "123456789012-1234567890123-AbCdEfGhIjKlMnOpQrStUv");
        let age = concat!(
            "AGE-SECRET-KEY-1",
            "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789ABCDEFGHIJKLMNOPQRSTUV"
        );
        let report = format!(
            "error: {ghp}\nkey: {akia}\ntoken {xoxb}\n{age}\nX-Auth-Token: header-secret-value\n",
        );
        let scrubbed = scrub_logs(&report);
        for secret in [ghp, akia, xoxb, age, "header-secret-value"] {
            assert!(!scrubbed.contains(secret), "secret leaked: {secret}");
        }
    }

    /// Byte-parity with the Python scrubber over the shared corpus in
    /// tests/fixtures/scrub_corpus.json (asserted identically from
    /// tests/test_diagnostics_scrub_parity.py). A redaction rule changed on
    /// one side without the other fails here.
    #[test]
    fn matches_shared_parity_corpus() {
        let path = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("../../tests/fixtures/scrub_corpus.json");
        let raw = std::fs::read_to_string(&path).expect("scrub corpus fixture exists");
        let document: serde_json::Value =
            serde_json::from_str(&raw).expect("fixture is valid JSON");
        for case in document["cases"].as_array().expect("cases is an array") {
            let name = case["name"].as_str().unwrap_or("?");
            let input = case["input"].as_str().expect("input is text");
            let expected = case["expected"].as_str().expect("expected is text");
            let scrubbed = scrub_logs(input);
            assert_eq!(scrubbed, expected, "parity case diverged: {name}");
            for token in case["must_not_contain"]
                .as_array()
                .expect("tokens is an array")
            {
                let token = token.as_str().expect("token is text");
                assert!(
                    !scrubbed.contains(token),
                    "secret leaked in {name}: {token}"
                );
            }
        }
    }

    #[test]
    fn hostname_env_is_redacted() {
        let _guard = lock_env();
        let prior = std::env::var("HOSTNAME").ok();
        std::env::set_var("HOSTNAME", "parity-host-xyz");
        let scrubbed = scrub_logs("serving parity-host-xyz today");
        match prior {
            Some(value) => std::env::set_var("HOSTNAME", value),
            None => std::env::remove_var("HOSTNAME"),
        }
        assert!(!scrubbed.contains("parity-host-xyz"));
    }

    #[test]
    fn kernel_hostname_is_redacted_without_env() {
        let _guard = lock_env();
        let prior = std::env::var("HOSTNAME").ok();
        std::env::remove_var("HOSTNAME");
        let names = super::hostnames_to_redact();
        let scrubbed = scrub_logs(&format!("serving {} today", names.join(" ")));
        match prior {
            Some(value) => std::env::set_var("HOSTNAME", value),
            None => std::env::remove_var("HOSTNAME"),
        }
        assert!(!names.is_empty(), "test machine has no hostname");
        for name in &names {
            assert!(!scrubbed.contains(name), "hostname leaked: {name}");
        }
    }

    #[test]
    fn username_env_is_redacted() {
        let _guard = lock_env();
        let prior_user = std::env::var("USER").ok();
        let prior_username = std::env::var("USERNAME").ok();
        std::env::set_var("USER", "parity-user");
        std::env::remove_var("USERNAME");
        let scrubbed = scrub_logs("ran as parity-user today");
        match prior_user {
            Some(value) => std::env::set_var("USER", value),
            None => std::env::remove_var("USER"),
        }
        if let Some(value) = prior_username {
            std::env::set_var("USERNAME", value);
        }
        assert!(!scrubbed.contains("parity-user"));
    }
}
