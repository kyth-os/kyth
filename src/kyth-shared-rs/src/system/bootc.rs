//! Port of `kyth_shared.system.bootc` — thin cache wrappers around bootc_query/policy.

pub fn branch_from_ref(r: Option<&str>) -> Option<String> {
    crate::system::bootc_policy::branch_from_ref(r)
}

pub fn current_branch() -> Option<String> {
    // Prefer the probe cache, then mirror Python's cache-miss behavior by
    // deriving the branch from the current bootc status response.
    if let Some(branch) = crate::system::probe::read_section("bootc-branch")
        .and_then(|v| v.as_str().map(str::to_string))
    {
        return Some(branch);
    }
    let status = crate::system::probe::read_section("bootc-status-data")
        .or_else(crate::system::bootc_query::fetch_status_data)?;
    crate::system::bootc_query::image_reference_from_status(&status)
        .as_deref()
        .and_then(|reference| branch_from_ref(Some(reference)))
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
    if cmd.is_empty() { return None; }
    let output = super::process::run_bounded(cmd, timeout).ok()?;
    Some((output.status.code().unwrap_or(-1), String::from_utf8_lossy(&output.stdout).to_string()))
}

pub fn has_staged_update() -> bool {
    crate::system::probe::read_section("bootc-status-data")
        .or_else(crate::system::bootc_query::fetch_status_data)
        .and_then(|v| v.get("status").and_then(|s| s.get("staged")).cloned())
        .is_some()
}

pub fn has_rollback_deployment() -> bool {
    crate::system::probe::read_section("bootc-status-data")
        .or_else(crate::system::bootc_query::fetch_status_data)
        .and_then(|v| v.get("status").and_then(|s| s.get("rollback")).cloned())
        .is_some()
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
