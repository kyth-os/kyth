//! Pure command projection for the VPN SAML sleep-survival helper.

pub const SLEEP_SURVIVE: bool = true;

pub const VPN_PROTOCOLS: &[&str] = &["gp", "anyconnect", "pulse", "nc", "f5", "fortinet", "array"];
pub const VPN_OS_OPTIONS: &[&str] = &["win", "linux", "mac"];
const MAX_SAML_FORM_BYTES: usize = 2 * 1024 * 1024;
const MAX_SAML_RESPONSE_BYTES: usize = 2 * 1024 * 1024;
const MAX_VPN_SECRET_BYTES: usize = 4096;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct OpenconnectCommand {
    pub argv: Vec<String>,
    pub stdin: Option<String>,
}

pub fn validate_profile(
    gateway: &str,
    protocol: &str,
    os_emulation: &str,
    username: &str,
) -> Result<(), String> {
    if gateway.is_empty()
        || gateway.len() > 2048
        || gateway.starts_with('-')
        || !gateway.bytes().all(|byte| {
            byte.is_ascii_alphanumeric()
                || matches!(
                    byte,
                    b'.' | b'_'
                        | b':'
                        | b'/'
                        | b'?'
                        | b'&'
                        | b'='
                        | b'%'
                        | b'+'
                        | b'@'
                        | b'['
                        | b']'
                        | b'-'
                )
        })
    {
        return Err("VPN gateway contains unsupported characters".into());
    }
    // Require a bare hostname or an https:// URL shape so a gateway that
    // smuggles flags or a foreign scheme never reaches the argv builder.
    // `origin(..., true)` accepts both forms and rejects credentials,
    // fragments, and non-HTTPS schemes.
    match origin(gateway, true) {
        Ok((host, _)) if !host.is_empty() && !host.starts_with('-') => {}
        _ => return Err("VPN gateway contains unsupported characters".into()),
    }
    if !VPN_PROTOCOLS.contains(&protocol) {
        return Err("unsupported VPN protocol".into());
    }
    if !VPN_OS_OPTIONS.contains(&os_emulation) {
        return Err("unsupported VPN OS emulation".into());
    }
    if username.len() > 256 || username.chars().any(char::is_control) {
        return Err("VPN username contains control characters".into());
    }
    Ok(())
}

fn validate_secret(field: &str, value: &str) -> Result<(), String> {
    let maximum = if field == "password" {
        MAX_VPN_SECRET_BYTES
    } else {
        MAX_SAML_RESPONSE_BYTES
    };
    if value.len() > maximum || value.chars().any(char::is_control) {
        return Err(format!("VPN {field} contains invalid characters"));
    }
    Ok(())
}

pub fn build_initial_command(
    gateway: &str,
    protocol: &str,
    os_emulation: &str,
    username: &str,
    password: &str,
) -> Result<OpenconnectCommand, String> {
    validate_profile(gateway, protocol, os_emulation, username)?;
    validate_secret("password", password)?;
    let mut argv = vec![
        "sudo".into(),
        "-A".into(),
        "/usr/bin/openconnect".into(),
        "--protocol".into(),
        protocol.into(),
        "--os".into(),
        os_emulation.into(),
        "--script".into(),
        "/etc/vpnc/vpnc-script".into(),
    ];
    if protocol == "gp" {
        // GlobalProtect deployments with a single portal+gateway host require
        // separate portal- and gateway-stage credentials; going straight to
        // the gateway skips the portal round-trip and its second prompt.
        argv.extend(["--usergroup".into(), "gateway".into()]);
    }
    if !password.is_empty() {
        argv.push("--passwd-on-stdin".into());
    }
    if !username.is_empty() {
        argv.extend(["--user".into(), username.into()]);
    }
    // Double-dash separator: the gateway is positional, so a validated but
    // dash-adjacent value must never parse as an openconnect flag.
    argv.extend(["--".into(), gateway.into()]);
    Ok(OpenconnectCommand {
        argv,
        stdin: (!password.is_empty()).then(|| format!("{password}\n")),
    })
}

pub fn build_reconnect_command(
    gateway: &str,
    protocol: &str,
    os_emulation: &str,
    interface: &str,
    cookie: &str,
    configured_username: &str,
) -> Result<OpenconnectCommand, String> {
    validate_profile(gateway, protocol, os_emulation, configured_username)?;
    validate_secret("cookie", cookie)?;
    if !matches!(interface, "portal" | "gateway") {
        return Err("invalid VPN authentication interface".into());
    }
    let (field, value, saml_username) = parse_gp_saml_cookie(cookie);
    let password_mode = protocol == "gp" && !field.is_empty() && !value.is_empty();
    let username = if saml_username.is_empty() {
        configured_username
    } else {
        &saml_username
    };
    let mut argv = vec![
        "sudo".into(),
        "-A".into(),
        "/usr/bin/openconnect".into(),
        "--protocol".into(),
        protocol.into(),
        "--os".into(),
        os_emulation.into(),
        "--script".into(),
        "/etc/vpnc/vpnc-script".into(),
    ];
    if password_mode {
        argv.extend([
            "--usergroup".into(),
            format!("{interface}:{field}"),
            "--passwd-on-stdin".into(),
        ]);
    } else {
        argv.push("--cookie-on-stdin".into());
    }
    if !username.is_empty() {
        argv.extend(["--user".into(), username.into()]);
    }
    // Double-dash separator before the positional gateway (see initial).
    argv.extend(["--".into(), gateway.into()]);
    Ok(OpenconnectCommand {
        argv,
        stdin: Some(format!(
            "{}\n",
            if password_mode {
                value.as_str()
            } else {
                cookie
            }
        )),
    })
}

pub fn saml_url_from_log_line(line: &str) -> Option<String> {
    let start = line.find("SAML REDIRECT")?;
    let rest = &line[start..];
    let marker = rest.find("via https://")?;
    let url = rest[marker + 4..]
        .split_whitespace()
        .next()?
        .trim_end_matches([')', ',', ';']);
    validate_saml_redirect_url(url)
        .ok()
        .map(|_| url.to_string())
}

pub fn gp_interface_from_log_line(line: &str) -> Option<&'static str> {
    if line.contains("/global-protect/prelogin.esp") {
        Some("portal")
    } else if line.contains("/ssl-vpn/prelogin.esp") {
        Some("gateway")
    } else {
        None
    }
}

pub fn line_is_connected(line: &str) -> bool {
    let line = line.to_ascii_lowercase();
    [
        "connected as",
        "established dtls",
        "established cstp",
        "esp session established",
        "esp tunnel connected",
        "configured as",
    ]
    .iter()
    .any(|marker| line.contains(marker))
}

/// Validate a browser destination discovered in openconnect output. The
/// redirect is untrusted child-process output, so only a conventional HTTPS
/// URL with a public-style host and no credentials or fragment is accepted.
pub fn validate_saml_redirect_url(value: &str) -> Result<(), String> {
    if value.is_empty() || value.len() > 8192 || value.chars().any(char::is_control) {
        return Err("SAML redirect URL is invalid or too large".into());
    }
    if value.contains('#') || value.contains('@') || !value.starts_with("https://") {
        return Err("SAML redirect URL must be HTTPS without credentials or fragments".into());
    }
    let (_, port) = origin(value, false)?;
    if port != 443 {
        return Err("SAML redirect URL must use HTTPS port 443".into());
    }
    Ok(())
}

pub fn redact_log_line(line: &str) -> String {
    let lower = line.to_ascii_lowercase();
    for marker in [
        "portal-userauthcookie=",
        "portal-prelogonuserauthcookie=",
        "prelogin-cookie=",
        "preloginuserauthcookie=",
        "cas=",
    ] {
        if let Some(index) = lower.find(marker) {
            let end = index + marker.len();
            return format!("{}<redacted>", &line[..end]);
        }
    }
    line.chars().take(400).collect()
}

fn percent_decode(value: &str) -> String {
    let bytes = value.as_bytes();
    let mut out = Vec::with_capacity(bytes.len());
    let mut index = 0;
    while index < bytes.len() {
        if bytes[index] == b'%' && index + 2 < bytes.len() {
            if let (Some(high), Some(low)) = (hex(bytes[index + 1]), hex(bytes[index + 2])) {
                out.push(high * 16 + low);
                index += 3;
                continue;
            }
        }
        out.push(if bytes[index] == b'+' {
            b' '
        } else {
            bytes[index]
        });
        index += 1;
    }
    String::from_utf8_lossy(&out).into_owned()
}

fn hex(value: u8) -> Option<u8> {
    match value {
        b'0'..=b'9' => Some(value - b'0'),
        b'a'..=b'f' => Some(value - b'a' + 10),
        b'A'..=b'F' => Some(value - b'A' + 10),
        _ => None,
    }
}

/// Which handoff the SAML sign-in window produced. The loopback callback
/// carries either a ready `cookie` (connect immediately) or the captured
/// ACS `url`+`body` form (replay once, then connect). Anything else means
/// the page completed without yielding credentials — historically a silent
/// no-op that left the Hub stuck on "sign-in required" forever.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SamlCallbackKind {
    Cookie,
    FormPost,
    Empty,
}

pub fn classify_saml_callback(has_cookie: bool, has_form_post: bool) -> SamlCallbackKind {
    if has_cookie {
        SamlCallbackKind::Cookie
    } else if has_form_post {
        SamlCallbackKind::FormPost
    } else {
        SamlCallbackKind::Empty
    }
}

pub fn parse_gp_saml_cookie(cookie: &str) -> (String, String, String) {
    let raw = cookie.trim();
    if raw.is_empty() {
        return (String::new(), String::new(), String::new());
    }
    let names = [
        "preloginuserauthcookie",
        "portal-userauthcookie",
        "cas",
        "prelogin-cookie",
    ];
    let mut username = String::new();
    let mut values = Vec::new();
    for part in raw.split('&') {
        let (key, value) = part.split_once('=').unwrap_or((part, ""));
        let key = percent_decode(key).trim().to_ascii_lowercase();
        let value = percent_decode(value);
        if key == "saml-username" {
            username = value.clone();
        }
        values.push((key, value));
    }
    if let Some((key, value)) = values
        .iter()
        .find(|(key, value)| names.contains(&key.as_str()) && !value.is_empty())
    {
        return (key.clone(), value.clone(), username);
    }
    if let Some((key, value)) = values
        .into_iter()
        .last()
        .filter(|(key, value)| names.contains(&key.as_str()) && !value.is_empty())
    {
        return (key, value, username);
    }
    ("prelogin-cookie".into(), raw.into(), username)
}

fn origin(value: &str, bare_host: bool) -> Result<(String, u16), String> {
    let candidate = if bare_host && !value.contains("://") {
        format!("https://{value}")
    } else {
        value.to_string()
    };
    let rest = candidate
        .strip_prefix("https://")
        .ok_or_else(|| "SAML URL must use HTTPS".to_string())?;
    let authority = rest.split(['/', '?', '#']).next().unwrap_or("");
    if authority.is_empty() || authority.contains('@') {
        return Err("SAML URL has invalid authority".into());
    }
    if authority.starts_with('[') {
        let end = authority
            .find(']')
            .ok_or_else(|| "SAML URL has invalid IPv6 host".to_string())?;
        let host = authority[1..end].to_ascii_lowercase();
        let port = authority[end + 1..]
            .strip_prefix(':')
            .map_or(Ok(443), |raw| {
                raw.parse()
                    .map_err(|_| "SAML URL has invalid port".to_string())
            })?;
        return Ok((host, port));
    }
    let (host, port) = authority
        .rsplit_once(':')
        .map_or((authority, "443"), |(host, port)| (host, port));
    if host.is_empty()
        || !host
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'.' | b'-' | b'_'))
    {
        return Err("SAML URL has invalid hostname".into());
    }
    Ok((
        host.trim_end_matches('.').to_ascii_lowercase(),
        port.parse()
            .map_err(|_| "SAML URL has invalid port".to_string())?,
    ))
}

pub fn validate_saml_acs_url(action_url: &str, expected_gateway: &str) -> Result<(), String> {
    if action_url.contains('#') {
        return Err("SAML ACS destination must not contain a fragment".into());
    }
    let path = action_url
        .strip_prefix("https://")
        .and_then(|rest| {
            rest.split_once('/')
                .map(|(_, path)| path.split(['?', '#']).next().unwrap_or(""))
        })
        .unwrap_or("");
    if path.trim_end_matches('/') != "SAML20/SP/ACS" {
        return Err("SAML ACS destination has an unexpected path".into());
    }
    if origin(action_url, false)? != origin(expected_gateway, true)? {
        return Err("SAML ACS destination does not match the VPN gateway".into());
    }
    Ok(())
}

fn xml_tag(text: &str, tag: &str) -> Option<String> {
    let lower = text.to_ascii_lowercase();
    let open = format!("<{tag}>");
    let close = format!("</{tag}>");
    let start = lower.find(&open)? + open.len();
    let end = lower[start..].find(&close)? + start;
    let value = text[start..end].trim();
    (!value.is_empty()).then(|| value.to_string())
}

fn form_encode(value: &str) -> String {
    value
        .bytes()
        .flat_map(|byte| match byte {
            b'A'..=b'Z' | b'a'..=b'z' | b'0'..=b'9' | b'-' | b'_' | b'.' | b'~' => {
                vec![byte as char]
            }
            _ => format!("%{byte:02X}").chars().collect(),
        })
        .collect()
}

/// Split a `curl --include` response into (headers, body) on the first blank
/// line. The GlobalProtect ACS cookie arrives as a response header, not in
/// the body, so this must find the header/body boundary itself rather than
/// the last blank line in the text — a body that happens to contain a blank
/// line later on must not be mistaken for part of the headers.
pub fn split_http_response(raw: &str) -> (&str, &str) {
    match raw
        .find("\r\n\r\n")
        .map(|index| (index, 4))
        .or_else(|| raw.find("\n\n").map(|index| (index, 2)))
    {
        Some((index, split)) => (&raw[..index], &raw[index + split..]),
        None => (raw, ""),
    }
}

pub fn parse_saml_acs_response(headers: &str, body: &str) -> Option<String> {
    let names = [
        "prelogin-cookie",
        "portal-userauthcookie",
        "cas",
        "preloginuserauthcookie",
    ];
    for name in names {
        for line in headers.lines() {
            if let Some((key, value)) = line.split_once(':') {
                if key.trim().eq_ignore_ascii_case(name) && !value.trim().is_empty() {
                    let username = headers
                        .lines()
                        .find_map(|line| {
                            line.split_once(':').and_then(|(key, value)| {
                                key.trim()
                                    .eq_ignore_ascii_case("saml-username")
                                    .then(|| value.trim())
                            })
                        })
                        .unwrap_or("");
                    return Some(format!(
                        "{name}={}&saml-username={}",
                        form_encode(value.trim()),
                        form_encode(username)
                    ));
                }
            }
        }
        if let Some(value) = xml_tag(body, name) {
            let username = xml_tag(body, "saml-username").unwrap_or_default();
            return Some(format!(
                "{name}={}&saml-username={}",
                form_encode(&value),
                form_encode(&username)
            ));
        }
    }
    None
}

pub fn replay_saml_command(
    action_url: &str,
    body: &str,
    expected_gateway: &str,
) -> Result<(Vec<String>, Vec<u8>), String> {
    validate_saml_acs_url(action_url, expected_gateway)?;
    if body.len() > MAX_SAML_FORM_BYTES
        || !body.split('&').any(|part| {
            part.split_once('=')
                .is_some_and(|(key, _)| key == "SAMLResponse")
        })
    {
        return Err("SAML ACS form is invalid or too large".into());
    }
    Ok((
        vec![
            "curl".into(),
            "--silent".into(),
            "--show-error".into(),
            "--fail-with-body".into(),
            "--include".into(),
            "--max-time".into(),
            "30".into(),
            "--connect-timeout".into(),
            "10".into(),
            "--max-redirs".into(),
            "0".into(),
            "--max-filesize".into(),
            "8388608".into(),
            "--proto".into(),
            "=https".into(),
            "--request".into(),
            "POST".into(),
            "--header".into(),
            "Content-Type: application/x-www-form-urlencoded".into(),
            "--header".into(),
            "User-Agent: PAN GlobalProtect".into(),
            "--data-binary".into(),
            "@-".into(),
            action_url.into(),
        ],
        body.as_bytes().to_vec(),
    ))
}

/// Return the TERM-then-KILL cascade used by the bounded VPN worker.
pub fn kill_cascade(pid: u32) -> Vec<Vec<String>> {
    ["TERM", "KILL"]
        .into_iter()
        .map(|signal| vec!["kill".into(), format!("-{signal}"), pid.to_string()])
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn cascade_is_ordered_and_sleep_survival_is_enabled() {
        assert!(SLEEP_SURVIVE);
        assert_eq!(
            kill_cascade(42),
            vec![vec!["kill", "-TERM", "42"], vec!["kill", "-KILL", "42"],]
        );
    }

    #[test]
    fn openconnect_command_keeps_password_out_of_argv() {
        let command =
            build_initial_command("https://vpn.example/gp", "gp", "win", "pat", "secret").unwrap();
        assert!(command.argv.iter().all(|arg| arg != "secret"));
        assert_eq!(command.stdin.as_deref(), Some("secret\n"));
        assert!(command.argv.contains(&"--passwd-on-stdin".into()));
    }

    #[test]
    fn gp_initial_command_targets_the_gateway_directly() {
        // Single-host GlobalProtect deployments require a separate
        // credential for each of the portal and gateway prelogin stages;
        // starting at the gateway avoids the portal round-trip entirely.
        let command =
            build_initial_command("https://vpn.example/gp", "gp", "win", "pat", "secret").unwrap();
        let usergroup_index = command
            .argv
            .iter()
            .position(|arg| arg == "--usergroup")
            .expect("gp initial command should set --usergroup");
        assert_eq!(command.argv[usergroup_index + 1], "gateway");
    }

    #[test]
    fn non_gp_initial_command_has_no_usergroup() {
        let command = build_initial_command(
            "https://vpn.example/ac",
            "anyconnect",
            "win",
            "pat",
            "secret",
        )
        .unwrap();
        assert!(!command.argv.iter().any(|arg| arg == "--usergroup"));
    }

    #[test]
    fn tunnel_setup_uses_the_upstream_vpnc_script() {
        // Regression pin for the GlobalProtect fix: the kyth-vpnc-script
        // stub never configured the tunnel interface, routes, or DNS, so a
        // "connected" openconnect left the machine offline. Both builders
        // must point at the real upstream script openconnect ships with.
        let initial =
            build_initial_command("https://vpn.example/gp", "gp", "win", "pat", "secret").unwrap();
        let script_index = initial
            .argv
            .iter()
            .position(|arg| arg == "--script")
            .expect("initial command should set --script");
        assert_eq!(initial.argv[script_index + 1], "/etc/vpnc/vpnc-script");
        assert!(
            !initial
                .argv
                .iter()
                .any(|arg| arg.contains("kyth-vpnc-script")),
            "must not use the stub script: {:?}",
            initial.argv
        );
        let reconnect = build_reconnect_command(
            "https://vpn.example/gp",
            "gp",
            "win",
            "gateway",
            "portal-userauthcookie=abc&saml-username=pat",
            "pat",
        )
        .unwrap();
        let script_index = reconnect
            .argv
            .iter()
            .position(|arg| arg == "--script")
            .expect("reconnect command should set --script");
        assert_eq!(reconnect.argv[script_index + 1], "/etc/vpnc/vpnc-script");
        assert!(
            !reconnect
                .argv
                .iter()
                .any(|arg| arg.contains("kyth-vpnc-script")),
            "must not use the stub script: {:?}",
            reconnect.argv
        );
    }

    #[test]
    fn saml_callback_routing_covers_all_three_cases() {
        use super::classify_saml_callback;
        use super::SamlCallbackKind::*;
        // Cookie wins even when a form is also present.
        assert_eq!(classify_saml_callback(true, true), Cookie);
        assert_eq!(classify_saml_callback(true, false), Cookie);
        assert_eq!(classify_saml_callback(false, true), FormPost);
        // Neither: the page finished without credentials. This used to be a
        // silent return that left the Hub stuck forever.
        assert_eq!(classify_saml_callback(false, false), Empty);
    }

    #[test]
    fn saml_cookie_and_acs_response_are_parsed() {
        assert_eq!(
            parse_gp_saml_cookie("portal-userauthcookie=abc&saml-username=pat"),
            ("portal-userauthcookie".into(), "abc".into(), "pat".into())
        );
        assert_eq!(
            parse_saml_acs_response("prelogin-cookie: abc\nsaml-username: pat", ""),
            Some("prelogin-cookie=abc&saml-username=pat".into())
        );
        assert!(validate_saml_acs_url("https://vpn.example/SAML20/SP/ACS", "vpn.example").is_ok());
        assert!(
            validate_saml_acs_url("https://evil.example/SAML20/SP/ACS", "vpn.example").is_err()
        );
    }

    #[test]
    fn saml_redirects_are_limited_to_safe_https_destinations() {
        assert!(validate_saml_redirect_url("https://idp.example/login?request=abc").is_ok());
        assert_eq!(
            saml_url_from_log_line("SAML REDIRECT via https://idp.example/login?request=abc"),
            Some("https://idp.example/login?request=abc".into())
        );
        assert!(validate_saml_redirect_url("http://idp.example/login").is_err());
        assert!(validate_saml_redirect_url("https://user:password@idp.example/login").is_err());
        assert!(validate_saml_redirect_url("https://idp.example/login#fragment").is_err());
        assert!(
            saml_url_from_log_line("SAML REDIRECT via https://idp.example:bad/login").is_none()
        );
    }

    #[test]
    fn replay_uses_stdin_for_the_saml_form() {
        let (argv, input) = replay_saml_command(
            "https://vpn.example/SAML20/SP/ACS",
            "SAMLResponse=token",
            "vpn.example",
        )
        .unwrap();
        assert!(argv.contains(&"@-".into()));
        assert!(
            argv.contains(&"--include".into()),
            "the GlobalProtect cookie arrives as a response header, so curl must be told to print them: {argv:?}"
        );
        assert_eq!(input, b"SAMLResponse=token");
    }

    #[test]
    fn split_http_response_separates_headers_from_a_body_that_reuses_the_same_boundary() {
        let raw = "HTTP/1.1 200 OK\r\nprelogin-cookie: abc\r\n\r\n<html>ok</html>\r\n\r\nmore";
        let (headers, body) = split_http_response(raw);
        assert_eq!(headers, "HTTP/1.1 200 OK\r\nprelogin-cookie: abc");
        assert_eq!(body, "<html>ok</html>\r\n\r\nmore");
        assert_eq!(
            parse_saml_acs_response(headers, body),
            Some("prelogin-cookie=abc&saml-username=".into())
        );
    }

    #[test]
    fn gateway_rejects_leading_dash_and_non_https_shapes() {
        assert!(validate_profile("-evil", "gp", "win", "pat").is_err());
        assert!(validate_profile("--help", "gp", "win", "pat").is_err());
        assert!(validate_profile("https://-evil.example/gp", "gp", "win", "pat").is_err());
        assert!(validate_profile("http://vpn.example/gp", "gp", "win", "pat").is_err());
        assert!(validate_profile("vpn.example; rm -rf /", "gp", "win", "pat").is_err());
        assert!(validate_profile("vpn.example", "gp", "win", "pat").is_ok());
        assert!(validate_profile("https://vpn.example/gp", "gp", "win", "pat").is_ok());
    }

    #[test]
    fn openconnect_argv_separates_positional_gateway_and_drops_env_passthrough() {
        for command in [
            build_initial_command("https://vpn.example/gp", "gp", "win", "pat", "secret").unwrap(),
            build_reconnect_command(
                "https://vpn.example/gp",
                "gp",
                "win",
                "gateway",
                "portal-userauthcookie=abc&saml-username=pat",
                "pat",
            )
            .unwrap(),
        ] {
            assert!(
                !command.argv.iter().any(|arg| arg == "-E"),
                "sudo must not pass the caller environment through: {:?}",
                command.argv
            );
            let dash = command
                .argv
                .iter()
                .position(|arg| arg == "--")
                .expect("positional gateway needs a -- separator");
            assert_eq!(command.argv[dash + 1], "https://vpn.example/gp");
            assert_eq!(command.argv[0], "sudo");
            assert_eq!(command.argv[1], "-A");
        }
    }

    #[test]
    fn replay_caps_server_response_size() {
        let (argv, _) = replay_saml_command(
            "https://vpn.example/SAML20/SP/ACS",
            "SAMLResponse=token",
            "vpn.example",
        )
        .unwrap();
        let index = argv
            .iter()
            .position(|arg| arg == "--max-filesize")
            .expect("curl replay must bound the response body");
        assert_eq!(argv[index + 1], "8388608");
    }
}
