//! Declarative AI/developer Distrobox configuration and argv projection.
//!
//! This ports the safe planning portion of `kyth_shared.ai_dev`. It never
//! creates a container, enters one, installs packages, or starts Ollama.

use std::collections::BTreeMap;
use std::path::{Path, PathBuf};

pub const DEFAULT_BOX: &str = "kyth-ai-dev";
pub const DEFAULT_IMAGE: &str = "registry.fedoraproject.org/fedora-toolbox:44";
pub const DEFAULT_MODEL: &str = "qwen2.5-coder";
pub const DEFAULT_MODEL_DIR_SUFFIX: &str = ".local/share/kyth-ai/models";

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Config { pub box_name: String, pub image: String, pub model_dir: PathBuf }

impl Config {
    pub fn from_environment(environment: &BTreeMap<String, String>) -> Self {
        let home = environment.get("HOME").map(PathBuf::from).unwrap_or_else(|| PathBuf::from("."));
        Self {
            box_name: environment.get("KYTH_AI_DEV_BOX").cloned().unwrap_or_else(|| DEFAULT_BOX.into()),
            image: environment.get("KYTH_AI_DEV_IMAGE").cloned().unwrap_or_else(|| DEFAULT_IMAGE.into()),
            model_dir: environment.get("KYTH_AI_MODEL_DIR").map(PathBuf::from).unwrap_or_else(|| home.join(DEFAULT_MODEL_DIR_SUFFIX)),
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum GpuKind { Nvidia, Amd, Dri, Cpu }

pub fn enter_command(config: &Config, args: &[String]) -> Vec<String> {
    let mut command = vec!["distrobox".into(), "enter".into(), config.box_name.clone(), "--".into()];
    command.extend_from_slice(args);
    command
}

pub fn create_command(config: &Config, git_paths: &[PathBuf], gpu: GpuKind) -> Vec<String> {
    let mut command = vec![
        "distrobox".into(), "create".into(), "--yes".into(), "--name".into(), config.box_name.clone(),
        "--image".into(), config.image.clone(), "--volume".into(), volume(&config.model_dir),
    ];
    for git in git_paths {
        command.extend(["--volume".into(), volume_with_mode(git, "rw")]);
        command.extend(["--volume".into(), volume_with_mode(&git.parent().unwrap_or_else(|| Path::new(".")).join(".agents"), "rw")]);
    }
    match gpu {
        GpuKind::Nvidia => command.push("--nvidia".into()),
        GpuKind::Amd => command.extend(["--additional-flags".into(), "--device=/dev/kfd --device=/dev/dri --group-add=video --group-add=render".into()]),
        GpuKind::Dri => command.extend(["--additional-flags".into(), "--device=/dev/dri --group-add=video --group-add=render".into()]),
        GpuKind::Cpu => {}
    }
    command
}

fn volume(path: &Path) -> String { volume_with_mode(path, "rw") }
fn volume_with_mode(path: &Path, mode: &str) -> String { format!("{}:{}:{mode}", path.display(), path.display()) }

pub fn gpu_description(gpu: GpuKind) -> &'static str {
    match gpu {
        GpuKind::Nvidia => "NVIDIA CUDA detected",
        GpuKind::Amd => "AMD ROCm / HIP detected (/dev/kfd)",
        GpuKind::Dri => "Vulkan / VA-API device detected",
        GpuKind::Cpu => "CPU inference fallback",
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn derives_config_from_explicit_environment() {
        let environment = BTreeMap::from([
            ("HOME".into(), "/home/test".into()),
            ("KYTH_AI_DEV_BOX".into(), "work-ai".into()),
            ("KYTH_AI_DEV_IMAGE".into(), "quay.io/example/dev:latest".into()),
        ]);
        assert_eq!(Config::from_environment(&environment), Config { box_name: "work-ai".into(), image: "quay.io/example/dev:latest".into(), model_dir: PathBuf::from("/home/test/.local/share/kyth-ai/models") });
    }

    #[test]
    fn projects_explicit_enter_and_gpu_commands() {
        let config = Config { box_name: "kyth-ai-dev".into(), image: DEFAULT_IMAGE.into(), model_dir: "/home/test/models".into() };
        assert_eq!(enter_command(&config, &["node".into(), "--version".into()]), vec!["distrobox", "enter", "kyth-ai-dev", "--", "node", "--version"]);
        let create = create_command(&config, &[PathBuf::from("/home/test/git/kyth/.git")], GpuKind::Nvidia);
        assert!(create.contains(&"--nvidia".into()));
        assert!(create.windows(2).any(|pair| pair[0] == "--image" && pair[1] == DEFAULT_IMAGE));
        assert_eq!(gpu_description(GpuKind::Cpu), "CPU inference fallback");
    }
}
