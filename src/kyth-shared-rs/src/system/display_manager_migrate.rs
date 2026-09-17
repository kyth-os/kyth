//! Native port of `build_files/scripts/sysconfig/kyth-migrate-display-manager`.
//!
//! On ostree/bootc, /etc survives across deployments. An image that dropped
//! SDDM for PLM still boots SDDM on hosts whose
//! `/etc/systemd/system/display-manager.service` points at sddm.service.
//! Idempotent and safe every boot; a no-op once on PLM. Mirrors the wiring
//! done at build time in sysconfig.sh.

use std::path::{Path, PathBuf};
use std::time::Duration;

const PLM_UNIT_NAME: &str = "plasmalogin.service";
const PLM_TARGET: &str = "/usr/lib/systemd/system/plasmalogin.service";
const GRAPHICAL_TARGET: &str = "/usr/lib/systemd/system/graphical.target";
const DEV_NULL: &str = "/dev/null";

/// Execute `systemctl` (or any argv) and return trimmed stdout on success.
pub fn systemctl_output(argv: &[String]) -> Option<String> {
    let output = crate::system::process::run_bounded(argv, Duration::from_secs(30)).ok()?;
    if !output.status.success() {
        return None;
    }
    Some(String::from_utf8_lossy(&output.stdout).trim().to_string())
}

fn read_link(path: &Path) -> Option<String> {
    std::fs::read_link(path)
        .ok()
        .map(|target| target.to_string_lossy().into_owned())
}

fn place_symlink(link: &Path, target: &str) -> bool {
    if read_link(link).as_deref() == Some(target) {
        return false;
    }
    if let Some(parent) = link.parent() {
        let _ = std::fs::create_dir_all(parent);
    }
    let _ = std::fs::remove_file(link);
    std::os::unix::fs::symlink(target, link).is_ok()
}

/// Run the migration against `etc`/`lib` roots. The `run` closure executes
/// argv and returns stdout on success; production passes [`systemctl_output`]
/// while tests pass a stub so no live systemd state is touched.
pub fn migrate(etc: &Path, lib: &Path, run: &dyn Fn(&[String]) -> Option<String>) -> bool {
    let plm_unit = lib.join("systemd/system").join(PLM_UNIT_NAME);
    // Must have PLM in the new image; otherwise nothing to migrate to.
    if !plm_unit.is_file() {
        return false;
    }
    let mut changed = false;

    let plasmalogin_etc = etc.join("systemd/system").join(PLM_UNIT_NAME);
    if read_link(&plasmalogin_etc).as_deref() == Some(DEV_NULL) {
        if std::fs::remove_file(&plasmalogin_etc).is_ok() {
            changed = true;
        }
    }
    let enabled = run(&[
        "systemctl".to_string(),
        "is-enabled".to_string(),
        PLM_UNIT_NAME.to_string(),
    ])
    .unwrap_or_default();
    if enabled.contains("masked") {
        run(&[
            "systemctl".to_string(),
            "unmask".to_string(),
            PLM_UNIT_NAME.to_string(),
        ]);
        changed = true;
    }

    let dm_link = etc.join("systemd/system/display-manager.service");
    let graphical_wants = etc.join("systemd/system/graphical.target.wants/display-manager.service");
    if read_link(&dm_link).as_deref() != Some(PLM_TARGET) {
        if let Some(parent) = dm_link.parent() {
            let _ = std::fs::create_dir_all(parent);
        }
        if let Some(parent) = graphical_wants.parent() {
            let _ = std::fs::create_dir_all(parent);
        }
        let _ = std::fs::remove_file(&dm_link);
        if std::os::unix::fs::symlink(PLM_TARGET, &dm_link).is_ok() {
            changed = true;
        }
        let _ = std::fs::remove_file(&graphical_wants);
        if std::os::unix::fs::symlink(&dm_link, &graphical_wants).is_ok() {
            changed = true;
        }
    }

    let default_link = etc.join("systemd/system/default.target");
    if read_link(&default_link).as_deref() != Some(GRAPHICAL_TARGET) {
        let _ = std::fs::remove_file(&default_link);
        if std::os::unix::fs::symlink(GRAPHICAL_TARGET, &default_link).is_ok() {
            changed = true;
        }
    }

    let sddm_etc = etc.join("systemd/system/sddm.service");
    match read_link(&sddm_etc).as_deref() {
        // Stale enable: replace with a mask. Missing: mask to prevent
        // manual enables. Already masked: nothing to do.
        Some(DEV_NULL) => {}
        _ => {
            let _ = std::fs::remove_file(&sddm_etc);
            if std::os::unix::fs::symlink(DEV_NULL, &sddm_etc).is_ok() {
                changed = true;
            }
        }
    }
    if read_link(&graphical_wants)
        .as_deref()
        .is_some_and(|target| target.contains("sddm"))
    {
        let _ = std::fs::remove_file(&graphical_wants);
        if std::os::unix::fs::symlink(&dm_link, &graphical_wants).is_ok() {
            changed = true;
        }
    }
    let sddm_state = run(&[
        "systemctl".to_string(),
        "is-enabled".to_string(),
        "sddm.service".to_string(),
    ])
    .unwrap_or_default();
    if !sddm_state.contains("masked") {
        run(&[
            "systemctl".to_string(),
            "mask".to_string(),
            "sddm.service".to_string(),
        ]);
        changed = true;
    }

    if changed {
        run(&["systemctl".to_string(), "daemon-reload".to_string()]);
    }
    changed
}

pub fn etc_root() -> PathBuf {
    PathBuf::from("/etc")
}

pub fn lib_root() -> PathBuf {
    PathBuf::from("/usr/lib")
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::collections::HashMap;
    use std::sync::{Arc, Mutex};

    struct Stub {
        outputs: HashMap<String, String>,
        calls: Arc<Mutex<Vec<Vec<String>>>>,
    }

    impl Stub {
        fn masked() -> (Self, Arc<Mutex<Vec<Vec<String>>>>) {
            // Fresh host mid-migration: plasmalogin masked, sddm enabled.
            let mut outputs = HashMap::new();
            outputs.insert("is-enabled plasmalogin.service".into(), "masked".into());
            outputs.insert("is-enabled sddm.service".into(), "enabled".into());
            let calls = Arc::new(Mutex::new(Vec::new()));
            (
                Self {
                    outputs,
                    calls: calls.clone(),
                },
                calls,
            )
        }

        fn run(&self, argv: &[String]) -> Option<String> {
            self.calls.lock().unwrap().push(argv.to_vec());
            self.outputs.get(&argv[1..].join(" ")).cloned()
        }
    }

    fn layout(root: &Path) {
        // New image ships PLM; /etc overlay is stale SDDM.
        let lib_unit = root.join("lib/systemd/system");
        std::fs::create_dir_all(&lib_unit).unwrap();
        std::fs::write(lib_unit.join(PLM_UNIT_NAME), "[Unit]\n").unwrap();
        let etc_unit = root.join("etc/systemd/system");
        std::fs::create_dir_all(&etc_unit).unwrap();
        std::os::unix::fs::symlink(
            "/usr/lib/systemd/system/sddm.service",
            etc_unit.join("display-manager.service"),
        )
        .unwrap();
        std::os::unix::fs::symlink("/dev/null", etc_unit.join("plasmalogin.service")).unwrap();
    }

    #[test]
    fn migrates_stale_sddm_overlay_to_plm() {
        let dir = tempfile::tempdir().unwrap();
        layout(dir.path());
        let (stub, calls) = Stub::masked();
        let etc = dir.path().join("etc");
        let lib = dir.path().join("lib");
        assert!(migrate(&etc, &lib, &|argv| stub.run(argv)));
        assert_eq!(
            read_link(&etc.join("systemd/system/display-manager.service")).as_deref(),
            Some(PLM_TARGET)
        );
        assert_eq!(
            read_link(&etc.join("systemd/system/sddm.service")).as_deref(),
            Some(DEV_NULL)
        );
        assert!(!etc.join("systemd/system/plasmalogin.service").exists());
        let commands: Vec<String> = calls.lock().unwrap().iter().flatten().cloned().collect();
        assert!(commands.contains(&"unmask".to_string()));
        assert!(commands.contains(&"daemon-reload".to_string()));
    }

    #[test]
    fn steady_state_is_a_noop() {
        let dir = tempfile::tempdir().unwrap();
        layout(dir.path());
        let etc = dir.path().join("etc");
        let lib = dir.path().join("lib");
        // Converge once (stub reports masked/enabled), then report the
        // converged state back and expect no further changes.
        let (stub, _) = Stub::masked();
        migrate(&etc, &lib, &|argv| stub.run(argv));
        let mut outputs = HashMap::new();
        outputs.insert("is-enabled plasmalogin.service".into(), "enabled".into());
        outputs.insert("is-enabled sddm.service".into(), "masked".into());
        let calls = Arc::new(Mutex::new(Vec::new()));
        let stub = Stub {
            outputs,
            calls: calls.clone(),
        };
        assert!(!migrate(&etc, &lib, &|argv| stub.run(argv)));
        let commands: Vec<String> = calls.lock().unwrap().iter().flatten().cloned().collect();
        assert!(
            !commands.contains(&"daemon-reload".to_string()),
            "steady state must not reload: {commands:?}"
        );
    }

    #[test]
    fn does_nothing_without_plm_in_image() {
        let dir = tempfile::tempdir().unwrap();
        let etc = dir.path().join("etc");
        std::fs::create_dir_all(etc.join("systemd/system")).unwrap();
        let lib = dir.path().join("lib");
        std::fs::create_dir_all(&lib).unwrap();
        let (stub, calls) = Stub::masked();
        assert!(!migrate(&etc, &lib, &|argv| stub.run(argv)));
        assert!(calls.lock().unwrap().is_empty());
    }
}
