//! First-boot application setup markers.

use std::path::{Path, PathBuf};

pub fn default_flatpaks_sentinel(root: impl AsRef<Path>) -> Option<PathBuf> {
    let mut best: Option<(i64, PathBuf)> = None;
    let Ok(entries) = root.as_ref().read_dir() else { return None; };
    for entry in entries.flatten() {
        let path = entry.path();
        let name = path.file_name().and_then(|name| name.to_str()).unwrap_or_default();
        let Some(version) = name.strip_prefix("default-flatpaks-v").and_then(|name| name.strip_suffix("-done")).and_then(|version| version.parse::<i64>().ok()) else { continue; };
        if best.as_ref().is_none_or(|(current, _)| version >= *current) { best = Some((version, path)); }
    }
    best.map(|(_, path)| path)
}

pub fn default_flatpaks_done(root: impl AsRef<Path>) -> bool {
    default_flatpaks_sentinel(root).is_some()
}

pub fn is_live_session(cmdline: impl AsRef<Path>) -> bool {
    std::fs::read_to_string(cmdline).ok().is_some_and(|text| text.split_whitespace().any(|token| token == "kyth.live"))
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    use tempfile::tempdir;

    #[test]
    fn selects_newest_valid_flatpak_marker() {
        let directory = tempdir().unwrap();
        fs::write(directory.path().join("default-flatpaks-v2-done"), "").unwrap();
        fs::write(directory.path().join("default-flatpaks-v12-done"), "").unwrap();
        fs::write(directory.path().join("default-flatpaks-vbad-done"), "").unwrap();
        assert_eq!(default_flatpaks_sentinel(directory.path()).unwrap().file_name().unwrap(), "default-flatpaks-v12-done");
        assert!(default_flatpaks_done(directory.path()));
    }
}
