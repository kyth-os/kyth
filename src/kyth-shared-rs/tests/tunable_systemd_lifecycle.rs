use std::{
    fs,
    os::unix::fs::PermissionsExt,
    process::{Command, Output},
};

use tempfile::tempdir;

fn install_systemctl_stub(
    directory: &std::path::Path,
    fail_on: Option<&str>,
) -> (std::path::PathBuf, std::path::PathBuf) {
    let bin_dir = directory.join("bin");
    fs::create_dir_all(&bin_dir).unwrap();
    let log = directory.join("systemctl.log");
    let fail_case = fail_on.unwrap_or("");
    let script = format!(
        "#!/bin/sh\nprintf '%s\\n' \"$*\" >> \"$SYSTEMCTL_LOG\"\nif [ \"$*\" = \"{fail_case}\" ]; then printf '%s\\n' 'stub systemctl failure' >&2; exit 1; fi\n"
    );
    let systemctl = bin_dir.join("systemctl");
    fs::write(&systemctl, script).unwrap();
    let mut permissions = fs::metadata(&systemctl).unwrap().permissions();
    permissions.set_mode(0o755);
    fs::set_permissions(&systemctl, permissions).unwrap();
    (bin_dir, log)
}

fn run_tunable(
    directory: &std::path::Path,
    feature: &str,
    action: &str,
    fail_on: Option<&str>,
) -> Output {
    let (bin_dir, log) = install_systemctl_stub(directory, fail_on);
    Command::new(env!("CARGO_BIN_EXE_kyth-tunable-rs"))
        .args([feature, action])
        .env("KYTH_TEST_MODE", "1")
        .env("XDG_CONFIG_HOME", directory.join("config"))
        .env("SYSTEMCTL_LOG", log)
        .env("PATH", format!("{}:/usr/bin:/bin", bin_dir.display()))
        .output()
        .unwrap()
}

#[test]
fn systemd_generated_unit_lifecycle_is_applied_by_every_tunable() {
    let directory = tempdir().unwrap();
    let features = [
        ("work-cache", "kyth-work-cache.service"),
        ("distrobox-cache", "kyth-distrobox-cache.service"),
        ("shader-tmpfs", "kyth-shader-tmpfs.service"),
        ("flatpak-prefetch", "flatpak-prefetch.timer"),
    ];

    // A default, disabled apply must not invoke systemd. Enabled apply must
    // activate the regenerated unit, and off must stop/disable it before the
    // generated files are removed and reload the manager afterward.
    for (feature, _) in features {
        let output = run_tunable(directory.path(), feature, "apply", None);
        assert!(
            output.status.success(),
            "{feature} disabled apply failed: {}",
            String::from_utf8_lossy(&output.stderr)
        );
    }
    for (feature, _) in features {
        let output = run_tunable(directory.path(), feature, "on", None);
        assert!(
            output.status.success(),
            "{feature} on failed: {}",
            String::from_utf8_lossy(&output.stderr)
        );
    }
    for (feature, _) in features {
        let output = run_tunable(directory.path(), feature, "apply", None);
        assert!(
            output.status.success(),
            "{feature} enabled apply failed: {}",
            String::from_utf8_lossy(&output.stderr)
        );
    }
    for (feature, _) in features {
        let output = run_tunable(directory.path(), feature, "off", None);
        assert!(
            output.status.success(),
            "{feature} off failed: {}",
            String::from_utf8_lossy(&output.stderr)
        );
    }
    for (feature, _) in features {
        let output = run_tunable(directory.path(), feature, "apply", None);
        assert!(
            output.status.success(),
            "{feature} disabled apply failed: {}",
            String::from_utf8_lossy(&output.stderr)
        );
    }

    let log = fs::read_to_string(directory.path().join("systemctl.log")).unwrap();
    let calls: Vec<_> = log.lines().collect();
    let mut expected = Vec::new();
    for (_, unit) in features {
        expected.extend([
            "daemon-reload".to_string(),
            format!("enable {unit}"),
            format!("restart {unit}"),
        ]);
    }
    for (_, unit) in features {
        expected.extend([
            "daemon-reload".to_string(),
            format!("enable {unit}"),
            format!("restart {unit}"),
        ]);
    }
    expected.extend([
        "disable --now kyth-work-cache.service".to_string(),
        "daemon-reload".to_string(),
        "disable --now kyth-distrobox-cache.service".to_string(),
        "daemon-reload".to_string(),
        "disable --now kyth-shader-tmpfs.service".to_string(),
        "daemon-reload".to_string(),
        "disable --now flatpak-prefetch.timer".to_string(),
        "stop flatpak-prefetch.service".to_string(),
        "daemon-reload".to_string(),
    ]);
    assert_eq!(
        calls,
        expected.iter().map(String::as_str).collect::<Vec<_>>()
    );
}

#[test]
fn systemd_activation_failure_is_returned_to_the_caller() {
    let directory = tempdir().unwrap();
    let output = run_tunable(
        directory.path(),
        "work-cache",
        "on",
        Some("restart kyth-work-cache.service"),
    );
    assert!(
        !output.status.success(),
        "failed systemctl restart must not report success"
    );
    assert!(
        String::from_utf8_lossy(&output.stderr).contains("stub systemctl failure"),
        "failed activation should preserve safe systemctl diagnostics"
    );
}
