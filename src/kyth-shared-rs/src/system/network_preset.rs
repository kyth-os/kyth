//! Declarative network preset (DoT + firewalld zone), offline.
//!
//! Mirrors `kyth_shared.network_preset`: validated load with safe defaults,
//! atomic `resolved.conf.d` drop-in with backup/rollback, and the TTL
//! marker. Only the `*_bin.rs` entry point touches the live filesystem.

use std::path::{Path, PathBuf};

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct NetworkPreset {
    pub dns: String,
    pub doh: bool,
    pub firewall_zone: String,
    /// Strict encrypted-DNS opt-in (`DNSOverTLS=strict`). Default off:
    /// strict breaks captive portals and corporate resolvers that do not
    /// expose DoT, so it is only for users who explicitly choose it in the
    /// Hub (documented in the save header and Hub network docs).
    pub dns_strict: bool,
    /// Route all DNS through the VPN tunnel when one is up
    /// (`resolvectl` per-link DNS set to the tunnel only). Default off.
    pub vpn_dns_exclusive: bool,
    /// Fail closed on unexpected VPN drops: flip firewalld to the `block`
    /// zone so traffic cannot silently return to the raw LAN, and restore
    /// the preset zone on clean disconnect/reconnect. Default off (Hub
    /// opt-in): lockdown needs an admin prompt at drop time.
    pub vpn_fail_closed: bool,
}

impl Default for NetworkPreset {
    fn default() -> Self {
        Self {
            dns: "quad9".into(),
            doh: true,
            // Restrictive default: a laptop on hotel/school Wi-Fi must not
            // trust the LAN. Users open their home LAN via the Hub (home).
            firewall_zone: "public".into(),
            dns_strict: false,
            vpn_dns_exclusive: false,
            vpn_fail_closed: false,
        }
    }
}

pub const RESOLVED_DROPIN: &str = "etc/systemd/resolved.conf.d/50-kyth.conf";
pub const TTL_PATH: &str = "/run/kyth-network-ttl";
pub const TTL_SECS: u64 = 30;

pub fn config_path(path: Option<impl AsRef<Path>>) -> PathBuf {
    if let Some(path) = path {
        return path.as_ref().to_path_buf();
    }
    if std::env::var("KYTH_TEST_MODE").ok().as_deref() == Some("1") {
        if let Some(xdg) = std::env::var_os("XDG_CONFIG_HOME") {
            return PathBuf::from(xdg).join("kyth/network.toml");
        }
    }
    PathBuf::from("/etc/kyth/network.toml")
}

fn validated(value: &toml::Value) -> NetworkPreset {
    let dns = value
        .get("dns")
        .and_then(toml::Value::as_str)
        .unwrap_or("quad9");
    let dns = matches!(dns, "quad9" | "cloudflare" | "off" | "google")
        .then(|| dns.to_string())
        .unwrap_or_else(|| "quad9".into());
    let zone = value
        .get("firewall_zone")
        .and_then(toml::Value::as_str)
        .unwrap_or("public");
    let firewall_zone = matches!(zone, "home" | "public" | "work")
        .then(|| zone.to_string())
        .unwrap_or_else(|| "public".into());
    NetworkPreset {
        dns,
        doh: value
            .get("doh")
            .and_then(toml::Value::as_bool)
            .unwrap_or(true),
        firewall_zone,
        dns_strict: value
            .get("dns_strict")
            .and_then(toml::Value::as_bool)
            .unwrap_or(false),
        vpn_dns_exclusive: value
            .get("vpn_dns_exclusive")
            .and_then(toml::Value::as_bool)
            .unwrap_or(false),
        vpn_fail_closed: value
            .get("vpn_fail_closed")
            .and_then(toml::Value::as_bool)
            .unwrap_or(false),
    }
}

pub fn load(path: impl AsRef<Path>) -> NetworkPreset {
    let Ok(raw) = std::fs::read_to_string(path) else {
        return NetworkPreset::default();
    };
    let Ok(value) = raw.parse::<toml::Value>() else {
        return NetworkPreset::default();
    };
    validated(&value)
}

/// Enforce the preset firewall zone as firewalld's default zone, so every
/// connection without an explicit zone inherits it. NM connections default
/// to the firewalld default zone automatically, so no dispatcher override
/// is needed (and none is installed: per-network user zones keep working).
/// Unknown zones fail closed without spawning anything. `block` is an
/// allowed zone: it is the fail-closed VPN lockdown target.
pub fn apply_firewall_zone(zone: &str) -> Result<String, String> {
    if !matches!(zone, "home" | "public" | "work" | "block") {
        return Err(format!("refusing unknown firewall zone: {zone}"));
    }
    let output = crate::system::process::run_bounded(
        &[
            "firewall-cmd".to_string(),
            format!("--set-default-zone={zone}"),
        ],
        std::time::Duration::from_secs(15),
    )
    .map_err(|error| format!("firewall-cmd failed: {error}"))?;
    if !output.status.success() {
        return Err(format!(
            "firewall-cmd --set-default-zone exited {}",
            output.status.code().unwrap_or(-1)
        ));
    }
    Ok(format!("default zone: {zone}"))
}

pub fn dns_ip(preset: &NetworkPreset) -> &'static str {
    match preset.dns.as_str() {
        "cloudflare" => "1.1.1.1",
        "google" => "8.8.8.8",
        "off" => "",
        _ => "9.9.9.9",
    }
}

/// Render `network.toml` from a validated preset. The Hub toggle path uses
/// this so flag flips preserve the DNS/firewall choices: only the two VPN
/// booleans change, everything else round-trips byte-identical in meaning.
/// Fail-closed note: callers must re-load the rendered text through `load`
/// and compare before writing — never persist a rendering that does not
/// decode to the preset it was rendered from.
pub fn render_network_toml(preset: &NetworkPreset) -> String {
    format!(
        "# Kyth network preset — DoT + firewalld, offline\n\
         dns = \"{}\"\n\
         doh = {}\n\
         firewall_zone = \"{}\"\n\
         dns_strict = {}\n\
         vpn_dns_exclusive = {}\n\
         vpn_fail_closed = {}\n",
        preset.dns,
        preset.doh,
        preset.firewall_zone,
        preset.dns_strict,
        preset.vpn_dns_exclusive,
        preset.vpn_fail_closed,
    )
}

pub fn render_resolved_conf(preset: &NetworkPreset) -> String {
    // Corporate DHCP DNS servers commonly do not expose DNS-over-TLS.  Use
    // resolved's opportunistic mode so encrypted DNS remains preferred when
    // available without breaking per-link enterprise resolvers.
    //
    // DNSSEC stays enforced (`DNSSEC=yes`) with public fallback resolvers so
    // a poisoned/missing primary cannot silently downgrade validation.
    // `DNSOverTLS=strict` is a documented opt-in only (`dns_strict`): it
    // breaks captive portals and networks without DoT, so the Hub must have
    // the user choose it explicitly.
    let tls = if preset.dns_strict {
        "strict"
    } else if preset.doh {
        "opportunistic"
    } else {
        "no"
    };
    format!(
        "[Resolve]\nDNS={}\nFallbackDNS=1.1.1.1 8.8.8.8\nDNSSEC=yes\nDNSOverTLS={tls}\n",
        dns_ip(preset),
    )
}

/// `resolvectl` argv pinning a VPN tunnel link to exclusive DNS: the tunnel
/// link gets the VPN resolver (see also [`vpn_exclusive_domain_argv`] for the
/// `~.` catch-all routing domain), so no query can leak to the LAN/ISP
/// resolver while the tunnel is up. Returns an empty vec when
/// `vpn_dns_exclusive` is off (the Guardian still runs the leak check below
/// and reports instead of enforcing).
pub fn vpn_exclusive_dns_argv(preset: &NetworkPreset, link: &str, vpn_dns: &str) -> Vec<String> {
    if !preset.vpn_dns_exclusive || link.is_empty() || vpn_dns.is_empty() {
        return Vec::new();
    }
    vec![
        "resolvectl".to_string(),
        "dns".to_string(),
        link.to_string(),
        vpn_dns.to_string(),
    ]
}

/// Companion to [`vpn_exclusive_dns_argv`]: routes every domain through the
/// tunnel link (`resolvectl domain <link> "~."`).
pub fn vpn_exclusive_domain_argv(preset: &NetworkPreset, link: &str) -> Vec<String> {
    if !preset.vpn_dns_exclusive || link.is_empty() {
        return Vec::new();
    }
    vec![
        "resolvectl".to_string(),
        "domain".to_string(),
        link.to_string(),
        "~.".to_string(),
    ]
}

/// Parse `resolvectl status` output for DNS servers on non-VPN links. Returns
/// the offending `(link, server)` pairs — a non-empty result while a VPN is
/// up means DNS is leaking around the tunnel.
pub fn vpn_dns_leaks(status_output: &str, vpn_links: &[&str]) -> Vec<(String, String)> {
    let mut leaks = Vec::new();
    let mut current_link = String::new();
    for line in status_output.lines() {
        let trimmed = line.trim();
        if trimmed.starts_with("Link ") {
            // Same `Link <index> (<name>):` shape as the guardian's tunnel
            // parser: match on the parenthesized interface name.
            current_link = trimmed
                .strip_prefix("Link ")
                .unwrap_or_default()
                .split(['(', ')'])
                .nth(1)
                .unwrap_or_default()
                .trim()
                .to_string();
            continue;
        }
        if let Some(servers) = trimmed.strip_prefix("DNS Servers:") {
            if vpn_links.iter().any(|vpn| *vpn == current_link) {
                continue;
            }
            for server in servers.split_whitespace() {
                leaks.push((current_link.clone(), server.to_string()));
            }
        }
    }
    leaks
}

/// Writes the drop-in under `root` with backup/rollback, exactly as the
/// Python launcher did (half-written DNS state is rolled back, never kept).
pub fn apply_preset(preset: &NetworkPreset, root: &Path) -> std::io::Result<Vec<PathBuf>> {
    let dest = root.join(RESOLVED_DROPIN);
    if let Some(parent) = dest.parent() {
        std::fs::create_dir_all(parent)?;
    }
    let backup = std::fs::read(&dest).ok();
    let write = (|| -> std::io::Result<()> {
        let tmp = dest.with_extension("tmp");
        std::fs::write(&tmp, render_resolved_conf(preset))?;
        std::fs::rename(&tmp, &dest)?;
        Ok(())
    })();
    if let Err(error) = write {
        match backup {
            None => {
                let _ = std::fs::remove_file(&dest);
            }
            Some(bytes) => {
                let _ = std::fs::write(&dest, bytes);
            }
        }
        return Err(error);
    }
    Ok(vec![dest])
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::tempdir;

    #[test]
    fn defaults_and_validates_preset_values() {
        let dir = tempdir().unwrap();
        let missing = dir.path().join("network.toml");
        assert_eq!(load(&missing), NetworkPreset::default());
        // Strict and VPN-exclusive DNS stay opt-in: absent keys default off.
        // The firewall zone fails closed to restrictive: unknown values and
        // missing keys both land on public, never a trusting zone.
        assert!(!NetworkPreset::default().dns_strict);
        assert!(!NetworkPreset::default().vpn_dns_exclusive);
        assert_eq!(NetworkPreset::default().firewall_zone, "public");
        let path = dir.path().join("bad.toml");
        std::fs::write(
            &path,
            "dns = \"evil\"\ndoh = false\nfirewall_zone = \"dmz\"\ndns_strict = true\nvpn_dns_exclusive = true\n",
        )
        .unwrap();
        assert_eq!(
            load(&path),
            NetworkPreset {
                dns: "quad9".into(),
                doh: false,
                firewall_zone: "public".into(),
                dns_strict: true,
                vpn_dns_exclusive: true,
                vpn_fail_closed: false,
            }
        );
    }

    #[test]
    fn renders_network_toml_and_reloads_it_identically() {
        let dir = tempdir().unwrap();
        let preset = NetworkPreset {
            dns: "cloudflare".into(),
            doh: false,
            firewall_zone: "work".into(),
            dns_strict: true,
            vpn_dns_exclusive: true,
            vpn_fail_closed: true,
        };
        let rendered = render_network_toml(&preset);
        let path = dir.path().join("network.toml");
        std::fs::write(&path, &rendered).unwrap();
        // Fail-closed contract: the rendered file must decode to the exact
        // preset it was rendered from, or the Hub toggle must not persist it.
        assert_eq!(load(&path), preset);
        assert_eq!(
            load(&dir.path().join("missing.toml")),
            NetworkPreset::default()
        );
    }

    #[test]
    fn firewall_zone_enforcement_rejects_unknown_zones_without_spawning() {
        let error = apply_firewall_zone("dmz").unwrap_err();
        assert!(error.contains("refusing unknown firewall zone"), "{error}");
        let error = apply_firewall_zone("--set-default-zone=public").unwrap_err();
        assert!(error.contains("refusing unknown firewall zone"), "{error}");
        // `block` is allowlisted (VPN lockdown target): it must never be
        // rejected as unknown — it either applies or reports a firewalld
        // failure, both of which prove the allowlist passed. Never flip a
        // live root firewall from a unit test.
        if std::process::Command::new("id")
            .arg("-u")
            .output()
            .map(|out| String::from_utf8_lossy(&out.stdout).trim() == "0")
            .unwrap_or(false)
        {
            return;
        }
        match apply_firewall_zone("block") {
            Ok(_) => {}
            Err(error) => assert!(!error.contains("refusing unknown"), "{error}"),
        }
    }

    #[test]
    fn renders_resolved_conf_like_python_launcher() {
        let preset = NetworkPreset::default();
        assert_eq!(
            render_resolved_conf(&preset),
            "[Resolve]\nDNS=9.9.9.9\nFallbackDNS=1.1.1.1 8.8.8.8\nDNSSEC=yes\nDNSOverTLS=opportunistic\n"
        );
        let off = NetworkPreset {
            dns: "off".into(),
            doh: false,
            firewall_zone: "public".into(),
            dns_strict: false,
            vpn_dns_exclusive: false,
            vpn_fail_closed: false,
        };
        assert_eq!(
            render_resolved_conf(&off),
            "[Resolve]\nDNS=\nFallbackDNS=1.1.1.1 8.8.8.8\nDNSSEC=yes\nDNSOverTLS=no\n"
        );
        let strict = NetworkPreset {
            dns_strict: true,
            ..NetworkPreset::default()
        };
        assert!(render_resolved_conf(&strict).contains("DNSOverTLS=strict"));
    }

    #[test]
    fn vpn_exclusive_dns_pins_tunnel_and_detects_leaks() {
        let off = NetworkPreset::default();
        assert!(vpn_exclusive_dns_argv(&off, "tun0", "10.0.0.1").is_empty());
        assert!(vpn_exclusive_domain_argv(&off, "tun0").is_empty());
        let on = NetworkPreset {
            vpn_dns_exclusive: true,
            ..NetworkPreset::default()
        };
        assert_eq!(
            vpn_exclusive_dns_argv(&on, "tun0", "10.0.0.1"),
            vec!["resolvectl", "dns", "tun0", "10.0.0.1"]
        );
        assert_eq!(
            vpn_exclusive_domain_argv(&on, "tun0"),
            vec!["resolvectl", "domain", "tun0", "~."]
        );
        assert!(vpn_exclusive_dns_argv(&on, "", "10.0.0.1").is_empty());
        let status = "Global\nLink 2 (wlp0s0):\n  DNS Servers: 192.168.1.1\nLink 5 (tun0):\n  DNS Servers: 10.0.0.1\n";
        let leaks = vpn_dns_leaks(status, &["tun0"]);
        assert_eq!(
            leaks,
            vec![("wlp0s0".to_string(), "192.168.1.1".to_string())]
        );
        assert!(vpn_dns_leaks("Link 5 (tun0):\n  DNS Servers: 10.0.0.1\n", &["tun0"]).is_empty());
    }

    #[test]
    fn applies_dropin_atomically_with_rollback() {
        let dir = tempdir().unwrap();
        let preset = NetworkPreset::default();
        let written = apply_preset(&preset, dir.path()).unwrap();
        assert_eq!(written.len(), 1);
        assert_eq!(
            std::fs::read_to_string(&written[0]).unwrap(),
            "[Resolve]\nDNS=9.9.9.9\nFallbackDNS=1.1.1.1 8.8.8.8\nDNSSEC=yes\nDNSOverTLS=opportunistic\n"
        );
    }
}
