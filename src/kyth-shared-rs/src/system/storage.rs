//! Disk free/total space — mirrors the "home, falling back to root, skip
//! tiny partitions" precedence `kyth_shared.guardian`'s own
//! `_probe_storage()` check uses (see guardian.py), and the
//! `shutil.disk_usage()` call the retired Python `storage_bridge.py` made.

use std::path::{Path, PathBuf};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct DiskUsage {
    pub free_bytes: u64,
    pub total_bytes: u64,
}

fn disk_usage(path: &Path) -> Option<DiskUsage> {
    let stat = rustix::fs::statvfs(path).ok()?;
    let frsize = stat.f_frsize as u64;
    Some(DiskUsage {
        free_bytes: stat.f_bavail.saturating_mul(frsize),
        total_bytes: stat.f_blocks.saturating_mul(frsize),
    })
}

const TWO_GIB: u64 = 2 * 1024 * 1024 * 1024;

/// Same home-then-root precedence and "skip tiny partitions" guard as
/// `guardian.py`'s `_probe_storage()`.
pub fn primary_disk_usage() -> Option<DiskUsage> {
    let mut candidates: Vec<PathBuf> = Vec::new();
    if let Ok(home) = std::env::var("HOME") {
        candidates.push(PathBuf::from(home));
    }
    candidates.push(PathBuf::from("/"));
    for candidate in candidates {
        if let Some(usage) = disk_usage(&candidate) {
            if usage.total_bytes >= TWO_GIB {
                return Some(usage);
            }
        }
    }
    None
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn root_filesystem_reports_plausible_usage() {
        // "/" always exists and is (barring a very unusual container) well
        // over 2GiB, so this exercises the real statvfs path end to end
        // without needing a fixture.
        let usage = disk_usage(Path::new("/")).expect("statvfs(/) should succeed in CI/dev");
        assert!(usage.total_bytes > 0);
        assert!(usage.free_bytes <= usage.total_bytes);
    }

    #[test]
    fn nonexistent_path_returns_none() {
        assert_eq!(disk_usage(Path::new("/no/such/path/kyth-test")), None);
    }
}
