//! Port of `kyth_shared.system.desktop_stack` — display stack checks.

use std::path::Path;

pub fn desktop_stack_checks() -> Vec<String> {
    let mut out = Vec::new();
    // Check kwin, plasmashell, sddm etc. via systemctl is-active
    for unit in ["plasmashell","kwin_wayland","sddm","plasmalogin.service"] {
        let ok = std::process::Command::new("systemctl").args(["is-active", unit]).output().ok().map(|o| String::from_utf8_lossy(&o.stdout).trim()=="active").unwrap_or(false);
        if ok { out.push(unit.to_string()); }
    }
    if Path::new("/usr/bin/kwin_wayland").exists() { out.push("kwin_wayland binary exists".to_string()); }
    out
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn checks() { let _ = desktop_stack_checks(); }
}
