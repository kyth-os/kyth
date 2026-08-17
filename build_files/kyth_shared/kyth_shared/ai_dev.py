"""Manage KythOS's opt-in developer and local-AI Distrobox."""
from __future__ import annotations
import logging

import argparse
import os
import shlex
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

from .commands import run

logger = logging.getLogger(__name__)

DEFAULT_BOX = "kyth-ai-dev"
DEFAULT_IMAGE = "registry.fedoraproject.org/fedora-toolbox:44"
DEFAULT_MODEL = "qwen2.5-coder"

# Kept as one shell program because it runs *inside* the container and relies on
# shell arrays, pipelines, and distrobox-export. Host-side policy stays Python.
PROVISION_SCRIPT = r"""
set -euo pipefail
sudo rpm --import https://packages.microsoft.com/keys/microsoft.asc || true
printf "[code]\nname=Visual Studio Code\nbaseurl=https://packages.microsoft.com/yumrepos/vscode\nenabled=1\ngpgcheck=1\ngpgkey=https://packages.microsoft.com/keys/microsoft.asc\n" | sudo tee /etc/yum.repos.d/vscode.repo >/dev/null
printf "[azure-cli]\nname=Azure CLI\nbaseurl=https://packages.microsoft.com/yumrepos/azure-cli\nenabled=1\ngpgcheck=1\ngpgkey=https://packages.microsoft.com/keys/microsoft.asc\n" | sudo tee /etc/yum.repos.d/azure-cli.repo >/dev/null
packages=(
  git git-lfs curl wget jq yq make cmake gcc gcc-c++
  python3 python3-pip python3-virtualenv python3-devel
  nodejs npm rust cargo golang podman skopeo podman-compose
  vulkan-tools clinfo ollama llama.cpp helix zellij shellcheck shfmt
  ripgrep fd-find fzf code azure-cli gh
  flatpak-builder rclone duperemove trivy bat eza fastfetch zoxide
  evtest lm_sensors i2c-tools v4l-utils hyperfine tmux starship direnv git-delta gum p7zip p7zip-plugins cabextract libpst
)
if command -v dnf5 >/dev/null 2>&1; then
  sudo dnf5 install -y --skip-unavailable "${packages[@]}"
  sudo dnf5 install -y --skip-unavailable pipx uv zizmor || true
elif command -v dnf >/dev/null 2>&1; then
  sudo dnf install -y --skip-unavailable "${packages[@]}"
  sudo dnf install -y --skip-unavailable pipx uv zizmor || true
else
  echo "ERROR: unsupported container package manager." >&2
  exit 1
fi
sudo npm install -g @anthropic-ai/claude-code @openai/codex || true
if command -v uv >/dev/null 2>&1; then
  uv tool install --python 3.13 --upgrade "headroom-ai[all]" || echo "WARNING: Headroom installation failed; continuing without it."
else
  echo "WARNING: uv is unavailable; continuing without Headroom."
fi
echo "Exporting applications and CLI wrappers to host..."
distrobox-export --app code || true
for binary in code az node npm npx hx zellij shellcheck shfmt gh flatpak-builder rclone duperemove trivy zizmor bat eza fastfetch zoxide evtest sensors i2cget i2cset i2cdetect v4l2-ctl jq yq hyperfine tmux pipx uv starship direnv delta gum 7z 7za cabextract readpst; do
  path="$(command -v "$binary" 2>/dev/null || true)"
  [[ -n "$path" ]] && distrobox-export --bin "$path" --export-path ~/.local/bin || true
done
for binary in claude codex; do
  path="$(command -v "$binary" 2>/dev/null || true)"
  [[ -n "$path" ]] && distrobox-export --bin "$path" --export-path ~/.local/bin || true
done
"""


@dataclass(frozen=True)
class Config:
    box: str
    image: str
    model_dir: Path

    @classmethod
    def from_environment(cls, environ: Mapping[str, str] | None = None) -> "Config":
        env = os.environ if environ is None else environ
        home = Path(env.get("HOME", str(Path.home())))
        return cls(
            box=env.get("KYTH_AI_DEV_BOX", DEFAULT_BOX),
            image=env.get("KYTH_AI_DEV_IMAGE", DEFAULT_IMAGE),
            model_dir=Path(env.get("KYTH_AI_MODEL_DIR", home / ".local/share/kyth-ai/models")),
        )


class AiDev:
    """Command controller with injectable process and platform dependencies."""

    def __init__(self, config: Config, *, runner=run, which=shutil.which) -> None:
        self.config = config
        self.runner = runner
        self.which = which

    def _run(self, argv: Sequence[str], **kwargs):
        return self.runner(list(argv), **kwargs)

    def require_distrobox(self) -> None:
        if self.which("distrobox") is None:
            raise RuntimeError("distrobox is not installed.")

    def enter_command(self, *argv: str) -> list[str]:
        return ["distrobox", "enter", self.config.box, "--", *argv]

    def box_exists(self) -> bool:
        result = self._run(
            ["distrobox", "list", "--no-color"],
            check=False,
            capture_output=True,
            text=True,
        )
        return any(
            len(fields) >= 3 and fields[2] == self.config.box
            for fields in result.stdout.splitlines()
        )

    def inside(self, *argv: str, check: bool = True):
        return self._run(self.enter_command(*argv), check=check)

    def _inside_has(self, command: str) -> bool:
        result = self.inside(
            "bash", "-lc", f"command -v {shlex.quote(command)} >/dev/null 2>&1",
            check=False,
        )
        return result.returncode == 0

    def gpu_kind(self) -> str:
        if self.which("nvidia-smi"):
            result = self._run(
                ["nvidia-smi", "-L"],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            if result.returncode == 0:
                return "nvidia"
        if Path("/dev/kfd").is_char_device():
            return "amd"
        if Path("/dev/dri/renderD128").is_char_device():
            return "dri"
        return "cpu"

    def create_command(self) -> list[str]:
        # Always mount .git rw inside the toolbox — prevents pre-push
        # update_ref / credential-lock failures when .git inherits ro
        # from the parent /var/home bind (ostree/rslave propagation).
        home = Path.home()
        # Prefer the actual checkout's .git if we're inside a repo,
        # otherwise fall back to the canonical ~/git/kyth location.
        candidates: list[Path] = []
        try:
            # Use git to locate the enclosing repo (quiet, fast).
            import subprocess as _sp  # pylint: disable=reimported

            res = _sp.run(
                ["git", "rev-parse", "--show-toplevel"],
                capture_output=True, text=True, timeout=2,
            )
            if res.returncode == 0 and res.stdout.strip():
                candidates.append(Path(res.stdout.strip()) / ".git")
        except Exception:
            logger.debug("handled expected exception", exc_info=True)
            pass
        canonical = home / "git" / "kyth" / ".git"
        if canonical not in candidates:
            candidates.append(canonical)
        # Also ensure the repo's .agents (toolbox cache lock) stays rw
        # when it exists alongside .git.
        extra_volumes: list[str] = []
        for git_path in candidates:
            extra_volumes.append(f"{git_path}:{git_path}:rw")
            agents_path = git_path.parent / ".agents"
            extra_volumes.append(f"{agents_path}:{agents_path}:rw")

        command = [
            "distrobox", "create", "--yes", "--name", self.config.box,
            "--image", self.config.image,
            "--volume", f"{self.config.model_dir}:{self.config.model_dir}:rw",
        ]
        for vol in extra_volumes:
            command.extend(["--volume", vol])
        gpu = self.gpu_kind()
        if gpu == "nvidia":
            command.append("--nvidia")
        elif gpu == "amd":
            command.extend([
                "--additional-flags",
                "--device=/dev/kfd --device=/dev/dri --group-add=video --group-add=render",
            ])
        elif gpu == "dri":
            command.extend([
                "--additional-flags",
                "--device=/dev/dri --group-add=video --group-add=render",
            ])
        return command

    def setup(self) -> None:
        self.require_distrobox()
        self.config.model_dir.mkdir(parents=True, exist_ok=True)
        if not self.box_exists():
            print(f"Creating {self.config.box} from {self.config.image}...")
            self._run(self.create_command(), check=True)
        else:
            print(f"{self.config.box} already exists.")
        print(f"Installing developer & AI tools in {self.config.box}...")
        self.inside("bash", "-lc", PROVISION_SCRIPT)
        # Ensure .git is rw even for pre-existing boxes where create_command
        # has already been used — remount inherits ro from /var/home.
        self.inside(
            "bash", "-lc",
            "for p in /var/home/*/git/kyth/.git /var/home/*/git/kyth/.agents; do "
            "[ -e \"$p\" ] && mount -o remount,rw \"$p\" 2>/dev/null || "
            "sudo mount -o remount,rw \"$p\" 2>/dev/null || true; done; "
            "gitdir=$(git rev-parse --show-toplevel 2>/dev/null)/.git; "
            "[ -e \"$gitdir\" ] && mount -o remount,rw \"$gitdir\" 2>/dev/null || "
            "sudo mount -o remount,rw \"$gitdir\" 2>/dev/null || true; "
            "agentsdir=$(git rev-parse --show-toplevel 2>/dev/null)/.agents; "
            "[ -e \"$agentsdir\" ] && mount -o remount,rw \"$agentsdir\" 2>/dev/null || "
            "sudo mount -o remount,rw \"$agentsdir\" 2>/dev/null || true",
            check=False,
        )
        print(f"\nDeveloper & AI environment ({self.config.box}) is ready.")
        print("Exported to host: VS Code, Node.js, Azure CLI, GitHub CLI, "
              "Claude Code, Codex CLI, Helix, Zellij, ShellCheck, shfmt.")
        print("Optional Distrobox tools in the shared user PATH: Headroom and RTK.")
        print(f"Enter environment manually with: distrobox enter {self.config.box}")

    def status(self) -> None:
        self.require_distrobox()
        print("KythOS AI developer environment")
        print(f"Box: {self.config.box}\nImage: {self.config.image}\nModels: {self.config.model_dir}\n")
        if not self.box_exists():
            print("Box: missing")
            print("Run: ujust ai-dev-setup or kyth-ai-dev setup")
            return
        print("Box: present")
        labels = {
            "code": "VS Code", "node": "Node.js",
            "headroom": "Headroom CLI", "rtk": "RTK CLI",
            "hx": "Helix Editor",
            "zellij": "Zellij Multiplexer", "gh": "GitHub CLI",
            "flatpak-builder": "Flatpak Builder", "rclone": "RClone Cloud Sync",
            "duperemove": "Btrfs Deduplicator", "trivy": "Trivy Scanner",
            "zizmor": "Zizmor Workflow Scanner",
            "claude": "Claude Code", "codex": "Codex CLI", "ollama": "Ollama",
        }
        for command, label in labels.items():
            installed = self._inside_has(command)
            suffix = ""
            if command == "node" and installed:
                result = self._run(
                    self.enter_command("node", "--version"),
                    check=False, capture_output=True, text=True,
                )
                suffix = f" ({result.stdout.strip() or 'unknown'})"
            print(f"{label}: {'installed' if installed else 'not installed'}{suffix}")
        descriptions = {
            "nvidia": "NVIDIA CUDA detected",
            "amd": "AMD ROCm / HIP detected (/dev/kfd)",
            "dri": "Vulkan / VA-API device detected",
            "cpu": "CPU inference fallback",
        }
        print(f"GPU Acceleration: {descriptions[self.gpu_kind()]}")

    def _require_box(self) -> None:
        if not self.box_exists():
            raise RuntimeError(
                f"{self.config.box} does not exist. Run: ujust ai-dev-setup or kyth-ai-dev setup"
            )

    def start(self) -> None:
        self.require_distrobox()
        self._require_box()
        model_dir = shlex.quote(str(self.config.model_dir))
        script = (
            'command -v ollama >/dev/null 2>&1 || { echo "ERROR: ollama is not installed. '
            'Run: ujust ai-dev-setup" >&2; exit 1; }; '
            f"OLLAMA_MODELS={model_dir} nohup ollama serve >/tmp/kyth-ollama.log 2>&1 &"
        )
        self.inside("bash", "-lc", script)
        print(f"Started Ollama inside {self.config.box} (Models in {self.config.model_dir}).")

    def stop(self) -> None:
        self.require_distrobox()
        if self.box_exists():
            self.inside("bash", "-lc", "pkill -x ollama 2>/dev/null || true")
        print(f"Stopped Ollama in {self.config.box}.")

    def pull_model(self, model: str) -> None:
        self.require_distrobox()
        self._require_box()
        running = self.inside("pgrep", "-x", "ollama", check=False).returncode == 0
        if not running:
            print("Starting background Ollama server before pulling model...")
            self.start()
            time.sleep(2)
        print(f"Pulling AI model '{model}' into {self.config.box} ({self.config.model_dir})...")
        env = f"OLLAMA_MODELS={shlex.quote(str(self.config.model_dir))}"
        self.inside("bash", "-lc", f"{env} ollama pull {shlex.quote(model)}")

    def remove(self) -> None:
        self.require_distrobox()
        self._run(["distrobox", "rm", "--force", self.config.box], check=True)
        print(f"Removed {self.config.box}.")
        print(f"Models were left in: {self.config.model_dir}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="kyth-ai-dev",
        description="Create and manage the KythOS AI & Developer Distrobox container.",
    )
    subparsers = parser.add_subparsers(dest="command")
    for name in ("setup", "status", "enter", "remove", "start", "stop"):
        subparsers.add_parser(name)
    pull = subparsers.add_parser("pull-model")
    pull.add_argument("model", nargs="?", default=DEFAULT_MODEL)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command is None:
        build_parser().print_help()
        return 0
    app = AiDev(Config.from_environment())
    try:
        if args.command == "enter":
            app.require_distrobox()
            os.execvp("distrobox", ["distrobox", "enter", app.config.box])
        elif args.command == "pull-model":
            app.pull_model(args.model)
        else:
            getattr(app, args.command)()
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        print(f"ERROR: {exc}", file=os.sys.stderr)
        return 1
    return 0
