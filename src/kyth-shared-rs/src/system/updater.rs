//! Port of `kyth_shared.system.updater` — is an updater entry point installed?

pub fn updater_available() -> bool {
    // kyth-full-update is the only updater entry point this build ever
    // installs (build_files/scripts/branding/36-misc-utility-installs.sh);
    // it execs into kyth-runtime apply-update. There is no separate
    // kyth-updater binary — a prior "kyth-updater --check" fallback here
    // referenced a name nothing in the build ever installs and had no
    // caller anywhere in the tree; removed rather than left as a dead,
    // permanently-false path. See tests/test_hub_command_reachability.py.
    std::path::Path::new("/usr/bin/kyth-full-update").exists()
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn available_bool() {
        let _ = updater_available();
    }
}
