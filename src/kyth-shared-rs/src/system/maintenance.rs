//! Read-only maintenance discovery and command planning.
//!
//! This ports the bounded target scan and argv projection from
//! `kyth_shared.maintenance`. It never deletes files, creates a duperemove
//! database, or starts the deduplication process.

use std::path::{Path, PathBuf};

pub fn supports_dedupe_filesystem(filesystem: &str) -> bool {
    matches!(filesystem.trim().to_ascii_lowercase().as_str(), "btrfs" | "xfs")
}

pub fn find_dedupe_targets(root: impl AsRef<Path>) -> Vec<PathBuf> {
    fn walk(current: &Path, depth: usize, targets: &mut Vec<PathBuf>) {
        if depth > 7 { return; }
        let Ok(entries) = std::fs::read_dir(current) else { return; };
        for entry in entries.flatten() {
            let path = entry.path();
            let Ok(file_type) = entry.file_type() else { continue; };
            if !file_type.is_dir() || file_type.is_symlink() { continue; }
            let text = path.to_string_lossy();
            if depth >= 4 && (text.ends_with("/Steam/steamapps/compatdata") || text.ends_with("/Steam/steamapps/shadercache")) {
                targets.push(path);
                continue;
            }
            walk(&path, depth + 1, targets);
        }
    }
    let mut targets = Vec::new();
    let root = root.as_ref();
    if root.is_dir() { walk(root, 1, &mut targets); }
    targets.sort();
    targets.dedup();
    targets
}

pub fn dedupe_command(target: impl AsRef<Path>, hash_file: impl AsRef<Path>, ionice_available: bool) -> Vec<String> {
    let core = ["nice", "-n", "19", "duperemove", "-rdh", "--hashfile"];
    let mut command = if ionice_available { vec!["ionice".into(), "-c3".into()] } else { Vec::new() };
    command.extend(core.into_iter().map(String::from));
    command.push(hash_file.as_ref().display().to_string());
    command.push(target.as_ref().display().to_string());
    command
}

pub fn cleanup_flatpaks_command() -> Vec<String> {
    vec!["flatpak".into(), "uninstall".into(), "--unused".into(), "-y".into(), "--noninteractive".into()]
}

pub fn vacuum_user_journal_command(days: i64) -> Vec<String> {
    vec!["journalctl".into(), "--user".into(), format!("--vacuum-time={days}d")]
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    use tempfile::tempdir;

    #[test]
    fn scans_only_bounded_non_symlink_targets() {
        let directory = tempdir().unwrap();
        let target = directory.path().join("a/b/c/Steam/steamapps/compatdata");
        fs::create_dir_all(&target).unwrap();
        fs::create_dir_all(directory.path().join("a/b/c/Steam/steamapps/other")).unwrap();
        assert_eq!(find_dedupe_targets(directory.path()), vec![target]);
        assert!(supports_dedupe_filesystem(" BTRFS\n"));
        assert!(!supports_dedupe_filesystem("ext4"));
    }

    #[test]
    fn projects_nice_ionice_dedupe_argv_without_running_it() {
        let command = dedupe_command("/var/home/user/Steam/steamapps/shadercache", "/var/lib/kyth/abc.hash", true);
        assert_eq!(command, vec!["ionice", "-c3", "nice", "-n", "19", "duperemove", "-rdh", "--hashfile", "/var/lib/kyth/abc.hash", "/var/home/user/Steam/steamapps/shadercache"]);
    }

    #[test]
    fn projects_noninteractive_cleanup_commands() {
        assert_eq!(cleanup_flatpaks_command(), vec!["flatpak", "uninstall", "--unused", "-y", "--noninteractive"]);
        assert_eq!(vacuum_user_journal_command(30), vec!["journalctl", "--user", "--vacuum-time=30d"]);
    }
}
