//! Tailscale mesh preset: tailnet + exit node from `tailscale.toml`, offline.

use std::path::{Path, PathBuf};

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct TailscalePreset {
    pub tailnet: String,
    pub exit_node: String,
    pub accept_routes: bool,
}

impl Default for TailscalePreset {
    fn default() -> Self {
        Self {
            tailnet: String::new(),
            exit_node: String::new(),
            accept_routes: false,
        }
    }
}

pub fn config_path(path: Option<impl AsRef<Path>>) -> PathBuf {
    if let Some(path) = path {
        return path.as_ref().to_path_buf();
    }
    if let Some(xdg) = std::env::var_os("XDG_CONFIG_HOME") {
        return PathBuf::from(xdg).join("kyth/tailscale.toml");
    }
    let home = std::env::var_os("HOME")
        .map(PathBuf::from)
        .unwrap_or_default();
    home.join(".config/kyth/tailscale.toml")
}

pub fn load(path: impl AsRef<Path>) -> TailscalePreset {
    let Ok(raw) = std::fs::read_to_string(path) else {
        return TailscalePreset::default();
    };
    let Ok(value) = raw.parse::<toml::Value>() else {
        return TailscalePreset::default();
    };
    TailscalePreset {
        tailnet: value
            .get("tailnet")
            .and_then(toml::Value::as_str)
            .unwrap_or_default()
            .to_string(),
        exit_node: value
            .get("exit_node")
            .and_then(toml::Value::as_str)
            .unwrap_or_default()
            .to_string(),
        accept_routes: value
            .get("accept_routes")
            .and_then(toml::Value::as_bool)
            .unwrap_or(false),
    }
}

/// Mirrors the launcher's `tailscale up` argv exactly (exit node and routes
/// only when configured).
pub fn up_argv(preset: &TailscalePreset) -> Vec<String> {
    let mut argv = vec!["tailscale".to_string(), "up".to_string()];
    if !preset.exit_node.is_empty() {
        argv.extend(["--exit-node".to_string(), preset.exit_node.clone()]);
    }
    if preset.accept_routes {
        argv.push("--accept-routes".to_string());
    }
    argv
}

/// Scoped firewalld zone for `tailscale0`: only the explicit ports below are
/// reachable from the tailnet — never the whole `trusted` zone. Port-opening
/// policy: anything beyond [`TAILSCALE_PORTS`] is temporary
/// (`firewall-cmd --zone=tailscale --add-port=… --timeout=…`) and must be
/// documented where it is opened.
pub const TAILSCALE_ZONE: &str = "tailscale";

/// Explicit tailnet-reachable ports: `(port, protocol)`. 41641/udp is
/// Tailscale's WireGuard transport; nothing else is permanently open.
pub const TAILSCALE_PORTS: &[(u16, &str)] = &[(41641, "udp")];

/// Render the scoped `tailscale` firewalld zone file.
pub fn render_firewall_zone() -> String {
    let mut ports = String::new();
    for (port, proto) in TAILSCALE_PORTS {
        ports.push_str(&format!("  <port port=\"{port}\" protocol=\"{proto}\"/>\n"));
    }
    format!(
        "<?xml version=\"1.0\" encoding=\"utf-8\"?>\n\
         <zone>\n\
         \x20 <short>tailscale</short>\n\
         \x20 <description>Scoped KythOS Tailscale mesh zone: WireGuard transport only. \
         Extra ports are temporary (--timeout) and documented at open time.</description>\n\
         {ports}\
         </zone>\n"
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::tempdir;

    #[test]
    fn defaults_and_projects_up_argv() {
        let dir = tempdir().unwrap();
        assert_eq!(
            load(dir.path().join("missing.toml")),
            TailscalePreset::default()
        );
        let path = dir.path().join("tailscale.toml");
        std::fs::write(
            &path,
            "tailnet = \"corp\"\nexit_node = \"node1\"\naccept_routes = true\n",
        )
        .unwrap();
        let preset = load(&path);
        assert_eq!(preset.tailnet, "corp");
        assert_eq!(
            up_argv(&preset),
            vec!["tailscale", "up", "--exit-node", "node1", "--accept-routes"]
        );
        assert_eq!(
            up_argv(&TailscalePreset::default()),
            vec!["tailscale", "up"]
        );
    }

    #[test]
    fn firewall_zone_is_scoped_to_explicit_ports() {
        assert_eq!(TAILSCALE_ZONE, "tailscale");
        assert_eq!(TAILSCALE_PORTS, &[(41641, "udp")]);
        let xml = render_firewall_zone();
        assert!(xml.contains("<short>tailscale</short>"));
        assert!(xml.contains("port=\"41641\" protocol=\"udp\""));
        assert!(!xml.contains("trusted"));
    }
}
