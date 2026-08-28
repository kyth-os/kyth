//! Port of `kyth_shared.system.bootc` — thin cache wrappers around bootc_query/policy.

use std::collections::HashSet;

pub fn branch_from_ref(r: Option<&str>) -> Option<String> {
    crate::system::bootc_policy::branch_from_ref(r)
}

pub fn current_branch() -> Option<String> {
    // probe_cached bootc-branch — read from probe cache
    crate::system::probe::read_section("bootc-branch").and_then(|v| v.as_str().map(|s| s.to_string()))
}

pub fn current_kernel_flavor() -> String {
    if let Ok(s) = std::fs::read_to_string("/usr/share/kyth/kernel-flavor") {
        let f = s.trim().to_lowercase();
        if f == "cachy" || f == "fedora" { return f; }
    }
    // fallback uname -r check
    if let Some((_, stdout)) = run_with_timeout(&["uname".to_string(), "-r".to_string()], std::time::Duration::from_secs(2)) {
        if stdout.to_lowercase().contains("cachy") { return "cachy".to_string(); }
    }
    "fedora".to_string()
}

fn run_with_timeout(cmd: &[String], timeout: std::time::Duration) -> Option<(i32, String)> {
    use std::process::{Command, Stdio};
    let mut child = Command::new(&cmd[0]).args(&cmd[1..]).stdout(Stdio::piped()).stderr(Stdio::piped()).spawn().ok()?;
    let start = std::time::Instant::now();
    loop {
        match child.try_wait() {
            Ok(Some(s)) => {
                let out = child.wait_with_output().ok()?;
                return Some((s.code().unwrap_or(-1), String::from_utf8_lossy(&out.stdout).to_string()));
            }
            Ok(None) => {
                if start.elapsed() > timeout { let _ = child.kill(); let _ = child.wait(); return None; }
                std::thread::sleep(std::time::Duration::from_millis(50));
            }
            Err(_) => return None,
        }
    }
}

pub fn has_staged_update() -> bool {
    if let Some(v) = crate::system::probe::read_section("bootc-status-data") {
        return v.get("status").and_then(|s| s.get("staged")).is_some();
    }
    false
}

pub fn has_rollback_deployment() -> bool {
    if let Some(v) = crate::system::probe::read_section("bootc-status-data") {
        return v.get("status").and_then(|s| s.get("rollback")).is_some();
    }
    false
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn branch() {
        assert_eq!(branch_from_ref(Some("ghcr.io/kyth-os/kyth:latest")), Some("latest".to_string()));
    }
    #[test]
    fn staged_bool() {
        let _ = has_staged_update();
    }
}
