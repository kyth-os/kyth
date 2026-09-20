//! Offline Mesa shader-cache tmpfs preference and unit rendering.

use std::path::{Path, PathBuf};

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ShaderTmpfsConfig {
    pub enabled: bool,
    pub size: String,
}

impl Default for ShaderTmpfsConfig {
    fn default() -> Self {
        Self {
            enabled: false,
            size: "2G".into(),
        }
    }
}

fn normalize(config: ShaderTmpfsConfig) -> ShaderTmpfsConfig {
    ShaderTmpfsConfig {
        size: matches!(config.size.as_str(), "1G" | "2G" | "4G")
            .then_some(config.size)
            .unwrap_or_else(|| "2G".into()),
        ..config
    }
}

pub fn config_path(path: Option<impl AsRef<Path>>) -> PathBuf {
    if let Some(path) = path {
        return path.as_ref().to_path_buf();
    }
    if std::env::var("KYTH_TEST_MODE").ok().as_deref() == Some("1") {
        if let Some(config) = std::env::var_os("XDG_CONFIG_HOME") {
            return PathBuf::from(config).join("kyth/shader-tmpfs.toml");
        }
    }
    PathBuf::from("/etc/kyth/shader-tmpfs.toml")
}

pub fn load(path: impl AsRef<Path>) -> ShaderTmpfsConfig {
    let Ok(raw) = std::fs::read_to_string(path) else {
        return ShaderTmpfsConfig::default();
    };
    let Ok(value) = raw.parse::<toml::Value>() else {
        return ShaderTmpfsConfig::default();
    };
    normalize(ShaderTmpfsConfig {
        enabled: value
            .get("enabled")
            .and_then(toml::Value::as_bool)
            .unwrap_or(false),
        size: value
            .get("size")
            .and_then(toml::Value::as_str)
            .unwrap_or("2G")
            .into(),
    })
}

pub fn save(path: impl AsRef<Path>, config: &ShaderTmpfsConfig) -> std::io::Result<()> {
    let config = normalize(config.clone());
    crate::atomic_io::atomic_write_text(
        path,
        &format!(
            "# Kyth shader tmpfs — offline\nenabled = {}\nsize = {:?}\n",
            config.enabled, config.size
        ),
        Some(0o600),
    )
}

/// Path Mesa must be pointed at for the tmpfs to do anything. Written as
/// an environment.d drop-in alongside the mount; removed when disabled.
pub const SHADER_TMPFS_DIR: &str = "/run/kyth-shader";

pub fn generate(
    config: &ShaderTmpfsConfig,
    tmpfiles: impl AsRef<Path>,
    service: impl AsRef<Path>,
    env_dropin: impl AsRef<Path>,
) -> std::io::Result<Option<PathBuf>> {
    let config = normalize(config.clone());
    let tmpfiles = tmpfiles.as_ref();
    let service = service.as_ref();
    let env_dropin = env_dropin.as_ref();
    if !config.enabled {
        for path in [tmpfiles, service, env_dropin] {
            match std::fs::remove_file(path) {
                Ok(()) | Err(_) => {}
            }
        }
        return Ok(None);
    }
    // 1777 sticky: every local user must be able to write their own cache
    // subdirectories. 0755 here silently locked non-root Mesa out, so the
    // mounted tmpfs sat empty while shaders compiled to disk.
    crate::atomic_io::atomic_write_text(
        tmpfiles,
        "# Kyth shader tmpfs — generated\nd /run/kyth-shader 1777 - - -\n",
        Some(0o644),
    )?;
    let content = format!("[Unit]\nDescription=Kyth shader tmpfs — Mesa cache on tmpfs\nAfter=local-fs.target\n[Service]\nType=oneshot\nRemainAfterExit=yes\nExecStart=/bin/sh -c 'mkdir -p /run/kyth-shader && mount -t tmpfs -o size={},mode=1777 tmpfs /run/kyth-shader'\nExecStop=/bin/sh -c 'umount /run/kyth-shader 2>/dev/null || true'\n[Install]\nWantedBy=multi-user.target\n", config.size);
    crate::atomic_io::atomic_write_text(service, &content, Some(0o644))?;
    // Without this, Mesa never finds the mount: point the cache path at it.
    crate::atomic_io::atomic_write_text(
        env_dropin,
        "# Kyth shader tmpfs — generated\nMESA_SHADER_CACHE_PATH=/run/kyth-shader\n",
        Some(0o644),
    )?;
    Ok(Some(service.to_path_buf()))
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::tempdir;

    #[test]
    fn clamps_size_and_reversibly_renders_units() {
        let directory = tempdir().unwrap();
        let config_path = directory.path().join("shader.toml");
        let tmpfiles = directory.path().join("shader.conf");
        let service = directory.path().join("shader.service");
        save(
            &config_path,
            &ShaderTmpfsConfig {
                enabled: true,
                size: "8G".into(),
            },
        )
        .unwrap();
        let config = load(&config_path);
        assert_eq!(config.size, "2G");
        let env = directory.path().join("shader.env");
        generate(&config, &tmpfiles, &service, &env).unwrap();
        assert!(service.exists());
        let rendered = std::fs::read_to_string(&env).unwrap();
        assert!(
            rendered.contains("MESA_SHADER_CACHE_PATH=/run/kyth-shader"),
            "mount without the env pointer leaves the tmpfs empty"
        );
        let unit = std::fs::read_to_string(&service).unwrap();
        assert!(
            unit.contains("mode=1777"),
            "non-sticky mount locks non-root Mesa out"
        );
        generate(&ShaderTmpfsConfig::default(), &tmpfiles, &service, &env).unwrap();
        assert!(!service.exists());
        assert!(!env.exists(), "disabling must remove the Mesa pointer too");
    }
}

/// Cache roots Mesa actually writes: the native cache plus every Flatpak
/// app's private cache (Steam included). Prune honors all of them.
pub fn cache_roots(home: &std::path::Path) -> Vec<std::path::PathBuf> {
    let mut roots = vec![home.join(".cache/mesa_shader_cache")];
    let flatpak_cache = home.join(".var/app");
    if let Ok(entries) = std::fs::read_dir(&flatpak_cache) {
        for entry in entries.flatten() {
            let candidate = entry.path().join("cache/mesa_shader_cache");
            if candidate.is_dir() {
                roots.push(candidate);
            }
        }
    }
    roots.into_iter().filter(|root| root.is_dir()).collect()
}

/// Size-capped prune: delete oldest files first until the root fits `cap`.
/// Returns bytes removed. Deleting the whole directory (the old behavior)
/// threw away every compiled shader and bought stutter on next launch.
pub fn prune_root(root: &std::path::Path, cap_bytes: u64) -> u64 {
    let mut files: Vec<(u64, u64, std::path::PathBuf)> = Vec::new();
    let mut stack = vec![root.to_path_buf()];
    while let Some(directory) = stack.pop() {
        let Ok(entries) = std::fs::read_dir(&directory) else {
            continue;
        };
        for entry in entries.flatten() {
            let path = entry.path();
            if path.is_dir() {
                stack.push(path);
                continue;
            }
            let Ok(meta) = entry.metadata() else { continue };
            // Nanosecond precision: whole seconds tie every file written
            // in the same second and silently invert the eviction order.
            let mtime = meta
                .modified()
                .ok()
                .and_then(|time| time.duration_since(std::time::UNIX_EPOCH).ok())
                .map(|age| age.as_nanos() as u64)
                .unwrap_or(0);
            files.push((mtime, meta.len(), path));
        }
    }
    let total: u64 = files.iter().map(|(_, size, _)| size).sum();
    if total <= cap_bytes {
        return 0;
    }
    files.sort();
    let mut removed = 0u64;
    for (_, size, path) in files {
        if total - removed <= cap_bytes {
            break;
        }
        if std::fs::remove_file(&path).is_ok() {
            removed += size;
        }
    }
    removed
}

#[cfg(test)]
mod prune_tests {
    use super::*;
    use std::fs;
    use tempfile::tempdir;

    #[test]
    fn prune_keeps_newest_under_cap() {
        let directory = tempdir().unwrap();
        let root = directory.path().join("mesa_shader_cache");
        fs::create_dir_all(&root).unwrap();
        fs::write(root.join("old.bin"), vec![0u8; 100]).unwrap();
        std::thread::sleep(std::time::Duration::from_millis(50));
        fs::write(root.join("new.bin"), vec![1u8; 100]).unwrap();
        let removed = prune_root(&root, 150);
        assert!(removed >= 100, "must evict the oldest file to fit the cap");
        assert!(!root.join("old.bin").exists());
        assert!(
            root.join("new.bin").exists(),
            "newest shaders survive a prune"
        );
    }

    #[test]
    fn prune_is_noop_under_cap() {
        let directory = tempdir().unwrap();
        let root = directory.path().join("mesa_shader_cache");
        fs::create_dir_all(&root).unwrap();
        fs::write(root.join("a.bin"), vec![0u8; 10]).unwrap();
        assert_eq!(prune_root(&root, 1024), 0);
        assert!(root.join("a.bin").exists());
    }
}
