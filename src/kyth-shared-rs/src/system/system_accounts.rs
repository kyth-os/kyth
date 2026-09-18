//! Native port of `build_files/scripts/sysconfig/kyth-fix-system-accounts`.
//!
//! Boot oneshot (runs before udev parses peripheral rules): merge
//! `/usr/lib/{group,passwd}` entries missing from `/etc`, ensure the
//! `plugdev` system group and the `plasmalogin` greeter account exist, fix
//! database modes, and prepare `/var/lib/plasmalogin`.

use std::os::unix::fs::PermissionsExt;
use std::path::Path;
use std::time::Duration;

pub const PLASMALOGIN_GROUP: &str = "plasmalogin:x:967:";
pub const PLASMALOGIN_PASSWD: &str =
    "plasmalogin:x:967:967:PLASMALOGIN Greeter Account:/var/lib/plasmalogin:/usr/sbin/nologin";

fn run(argv: &[String]) -> Option<String> {
    crate::system::process::run_bounded(argv, Duration::from_secs(60))
        .ok()
        .and_then(|output| {
            output
                .status
                .success()
                .then(|| String::from_utf8_lossy(&output.stdout).into_owned())
        })
}

/// Append lines from `src` whose leading `name:` field is missing in `dest`.
/// Returns the number of lines appended. Mirrors `append_missing_name`.
pub fn append_missing_names(src: &Path, dest: &Path) -> std::io::Result<usize> {
    if !src.is_file() {
        return Ok(0);
    }
    let content = std::fs::read_to_string(src)?;
    if !dest.exists() {
        std::fs::write(dest, "")?;
    }
    let existing = std::fs::read_to_string(dest).unwrap_or_default();
    let mut appended = 0;
    let mut out = std::fs::OpenOptions::new().append(true).open(dest)?;
    use std::io::Write;
    for line in content.lines() {
        if line.is_empty() {
            continue;
        }
        let name = line.split(':').next().unwrap_or("");
        if name.is_empty() {
            continue;
        }
        let present = existing
            .lines()
            .any(|known| known.split(':').next() == Some(name));
        if !present {
            writeln!(out, "{line}")?;
            appended += 1;
        }
    }
    Ok(appended)
}

fn has_entry(file: &Path, name: &str) -> bool {
    std::fs::read_to_string(file)
        .map(|content| {
            content
                .lines()
                .any(|line| line.split(':').next() == Some(name))
        })
        .unwrap_or(false)
}

fn append_line(file: &Path, line: &str) {
    use std::io::Write;
    if let Ok(mut out) = std::fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(file)
    {
        let _ = writeln!(out, "{line}");
    }
}

pub fn ensure_group_line(etc: &Path, name: &str, line: &str) {
    let group = etc.join("group");
    if !has_entry(&group, name) {
        append_line(&group, line);
    }
}

pub fn ensure_passwd_line(etc: &Path, name: &str, line: &str) {
    let passwd = etc.join("passwd");
    if !has_entry(&passwd, name) {
        append_line(&passwd, line);
    }
    let shadow = etc.join("shadow");
    if shadow.exists() && !has_entry(&shadow, name) {
        append_line(&shadow, &format!("{name}:!*:19700:0:99999:7:::"));
    }
}

fn getent_group(name: &str) -> bool {
    run(&["getent".to_string(), "group".to_string(), name.to_string()]).is_some()
}

/// Run the full fixup against `/`, `/usr/lib`, and `/var/lib` roots.
/// `sys` (default `/`) scopes /etc and /var/lib for tests.
pub fn fix(sys: &Path, usr_lib: &Path) {
    let etc = sys.join("etc");
    let var_lib = sys.join("var/lib");
    let _ = append_missing_names(&usr_lib.join("group"), &etc.join("group"));
    let _ = append_missing_names(&usr_lib.join("passwd"), &etc.join("passwd"));

    // Third-party peripheral rules use Debian's plugdev group, which Fedora
    // does not normally ship. No fixed GID: /etc may already use any number.
    if !getent_group("plugdev") {
        run(&[
            "groupadd".to_string(),
            "--system".to_string(),
            "plugdev".to_string(),
        ]);
    }

    ensure_group_line(&etc, "plasmalogin", PLASMALOGIN_GROUP);
    ensure_passwd_line(&etc, "plasmalogin", PLASMALOGIN_PASSWD);

    let _ = std::fs::set_permissions(etc.join("passwd"), std::fs::Permissions::from_mode(0o644));
    let _ = std::fs::set_permissions(etc.join("group"), std::fs::Permissions::from_mode(0o644));
    let shadow = etc.join("shadow");
    if shadow.exists() {
        if std::fs::set_permissions(&shadow, std::fs::Permissions::from_mode(0o000)).is_err() {
            let _ = std::fs::set_permissions(&shadow, std::fs::Permissions::from_mode(0o600));
        }
    }
    let greeter_home = var_lib.join("plasmalogin");
    let _ = std::fs::create_dir_all(&greeter_home);
    // chown plasmalogin:plasmalogin — resolve via getent to stay portable.
    if let Some(entry) = run(&[
        "getent".to_string(),
        "passwd".to_string(),
        "plasmalogin".to_string(),
    ]) {
        let fields: Vec<&str> = entry.trim().split(':').collect();
        if fields.len() >= 4 {
            if let (Ok(uid), Ok(gid)) = (fields[2].parse::<u32>(), fields[3].parse::<u32>()) {
                let _ = std::os::unix::fs::chown(&greeter_home, Some(uid), Some(gid));
            }
        }
    }
    run(&[
        "restorecon".to_string(),
        etc.join("passwd").to_string_lossy().into_owned(),
        etc.join("group").to_string_lossy().into_owned(),
        shadow.to_string_lossy().into_owned(),
        greeter_home.to_string_lossy().into_owned(),
    ]);
}

#[cfg(test)]
mod tests {
    use super::*;

    fn fixture(dir: &Path) {
        std::fs::write(dir.join("lib-group"), "root:x:0:\nwheel:x:10:alice\n").unwrap();
        std::fs::write(dir.join("lib-passwd"), "root:x:0:0:root:/root:/bin/bash\n").unwrap();
        std::fs::write(dir.join("etc-group"), "root:x:0:\n").unwrap();
        std::fs::write(dir.join("etc-passwd"), "root:x:0:0:root:/root:/bin/bash\n").unwrap();
    }

    #[test]
    fn merges_only_missing_names() {
        let dir = tempfile::tempdir().unwrap();
        fixture(dir.path());
        let appended =
            append_missing_names(&dir.path().join("lib-group"), &dir.path().join("etc-group"))
                .unwrap();
        assert_eq!(appended, 1);
        let merged = std::fs::read_to_string(dir.path().join("etc-group")).unwrap();
        assert!(merged.contains("wheel:x:10:alice"));
        // Second run is a no-op.
        assert_eq!(
            append_missing_names(&dir.path().join("lib-group"), &dir.path().join("etc-group"))
                .unwrap(),
            0
        );
    }

    #[test]
    fn missing_source_is_a_noop() {
        let dir = tempfile::tempdir().unwrap();
        assert_eq!(
            append_missing_names(&dir.path().join("absent"), &dir.path().join("dest")).unwrap(),
            0
        );
        assert!(!dir.path().join("dest").exists());
    }

    #[test]
    fn ensures_plasmalogin_lines() {
        let dir = tempfile::tempdir().unwrap();
        let etc = dir.path().join("etc");
        std::fs::create_dir_all(&etc).unwrap();
        std::fs::write(etc.join("group"), "root:x:0:\n").unwrap();
        std::fs::write(etc.join("passwd"), "root:x:0:0:root:/root:/bin/bash\n").unwrap();
        ensure_group_line(&etc, "plasmalogin", PLASMALOGIN_GROUP);
        ensure_passwd_line(&etc, "plasmalogin", PLASMALOGIN_PASSWD);
        ensure_group_line(&etc, "plasmalogin", PLASMALOGIN_GROUP);
        let group = std::fs::read_to_string(etc.join("group")).unwrap();
        assert_eq!(group.matches("plasmalogin:x:967:").count(), 1);
        let passwd = std::fs::read_to_string(etc.join("passwd")).unwrap();
        assert!(passwd.contains(PLASMALOGIN_PASSWD));
    }
}
