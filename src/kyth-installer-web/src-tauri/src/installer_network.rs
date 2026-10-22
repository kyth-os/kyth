use std::collections::BTreeMap;

use serde::Serialize;

pub(crate) const NMCLI_PATH: &str = "/usr/bin/nmcli";
pub(crate) const KONSOLE_PATH: &str = "/usr/bin/konsole";
pub(crate) const SCAN_ARGS: &[&str] = &[
    "--terse",
    "--escape",
    "yes",
    "--fields",
    "IN-USE,SSID,SECURITY,SIGNAL",
    "--wait",
    "20",
    "device",
    "wifi",
    "list",
    "--rescan",
    "yes",
];

#[derive(Debug, Clone, Serialize, PartialEq, Eq)]
pub(crate) struct WifiNetwork {
    pub(crate) ssid: String,
    pub(crate) security: String,
    pub(crate) signal: u8,
    pub(crate) in_use: bool,
}

/// Parse nmcli's terse, escaped `IN-USE,SSID,SECURITY,SIGNAL` output.
pub(crate) fn parse_nmcli_wifi_list(output: &str) -> Vec<WifiNetwork> {
    let mut by_ssid = BTreeMap::<String, WifiNetwork>::new();

    for line in output.lines() {
        let fields = split_nmcli_fields(line);
        if fields.len() != 4 {
            continue;
        }
        let (in_use, ssid, security, signal) = (&fields[0], &fields[1], &fields[2], &fields[3]);
        if !valid_ssid(ssid) || security.is_empty() {
            continue;
        }
        let Ok(signal) = signal.parse::<u8>() else {
            continue;
        };
        if signal > 100 {
            continue;
        }

        let network = WifiNetwork {
            ssid: ssid.clone(),
            security: security.clone(),
            signal,
            in_use: in_use == "*",
        };
        by_ssid
            .entry(network.ssid.clone())
            .and_modify(|existing| {
                let connected = existing.in_use || network.in_use;
                if network.signal > existing.signal {
                    *existing = network.clone();
                }
                existing.in_use = connected;
            })
            .or_insert(network);
    }

    let mut networks: Vec<_> = by_ssid.into_values().collect();
    networks.sort_by(|left, right| {
        right
            .in_use
            .cmp(&left.in_use)
            .then_with(|| right.signal.cmp(&left.signal))
            .then_with(|| left.ssid.cmp(&right.ssid))
    });
    networks
}

fn split_nmcli_fields(line: &str) -> Vec<String> {
    let mut fields = Vec::new();
    let mut field = String::new();
    let mut chars = line.chars();

    while let Some(ch) = chars.next() {
        match ch {
            ':' => fields.push(std::mem::take(&mut field)),
            '\\' => match chars.next() {
                Some('\\') => field.push('\\'),
                Some(':') => field.push(':'),
                Some(other) => {
                    field.push('\\');
                    field.push(other);
                }
                None => field.push('\\'),
            },
            other => field.push(other),
        }
    }
    fields.push(field);
    fields
}

pub(crate) fn valid_ssid(ssid: &str) -> bool {
    !ssid.is_empty() && ssid != "--" && ssid.len() <= 32 && !ssid.chars().any(char::is_control)
}

/// Arguments for a terminal-backed nmcli flow. No shell is involved and no
/// passphrase is placed in argv; nmcli prompts in Konsole when needed.
pub(crate) fn connection_terminal_args(ssid: &str) -> Result<Vec<String>, String> {
    if !valid_ssid(ssid) {
        return Err("The selected Wi-Fi network has an invalid SSID.".to_string());
    }

    Ok([
        "--hold", "-e", NMCLI_PATH, "--ask", "device", "wifi", "connect", ssid,
    ]
    .into_iter()
    .map(str::to_string)
    .collect())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_escaped_ssids_deduplicates_and_keeps_the_strongest_signal() {
        let output = concat!(
            "*:Open\\:Guest:--:42\n",
            ":Open\\:Guest:--:84\n",
            ":Secure\\\\Lab:WPA2:63\n",
            ":hidden:WPA2:--\n",
            ":invalid:WPA2:101\n",
            "malformed\n",
        );

        assert_eq!(
            parse_nmcli_wifi_list(output),
            vec![
                WifiNetwork {
                    ssid: "Open:Guest".to_string(),
                    security: "--".to_string(),
                    signal: 84,
                    in_use: true,
                },
                WifiNetwork {
                    ssid: "Secure\\Lab".to_string(),
                    security: "WPA2".to_string(),
                    signal: 63,
                    in_use: false,
                },
            ]
        );
    }

    #[test]
    fn scan_uses_nmcli_wifi_rescan_with_stable_fields() {
        assert!(SCAN_ARGS
            .windows(3)
            .any(|args| args == ["device", "wifi", "list"]));
        assert!(SCAN_ARGS.windows(2).any(|args| args == ["--rescan", "yes"]));
        assert!(SCAN_ARGS.windows(2).any(|args| args == ["--wait", "20"]));
    }

    #[test]
    fn connect_uses_the_working_ask_flow_without_a_shell_or_password_argument() {
        let args = connection_terminal_args("Guest Wi-Fi").unwrap();
        assert_eq!(
            args,
            [
                "--hold",
                "-e",
                NMCLI_PATH,
                "--ask",
                "device",
                "wifi",
                "connect",
                "Guest Wi-Fi",
            ]
        );
        assert!(!args
            .iter()
            .any(|arg| arg == "password" || arg == "sh" || arg == "-c"));
    }

    #[test]
    fn connection_arguments_preserve_ssids_as_single_literal_arguments() {
        let ssid = "Guest; printf not-a-shell";
        let args = connection_terminal_args(ssid).unwrap();
        assert_eq!(args.last().map(String::as_str), Some(ssid));
    }

    #[test]
    fn invalid_ssids_are_rejected_before_launch() {
        assert!(connection_terminal_args("").is_err());
        assert!(connection_terminal_args("--").is_err());
        assert!(connection_terminal_args("bad\nssid").is_err());
        assert!(connection_terminal_args(&"x".repeat(33)).is_err());
    }
}
