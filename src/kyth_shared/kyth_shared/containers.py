"""Container helper utilities for host-to-container wrapper generation."""
from __future__ import annotations

import textwrap
from pathlib import Path


def render_distrobox_wrapper(tool: str, description: str, box: str = "kyth-ai-dev") -> str:
    """Return bash wrapper script content for executing a tool in a Distrobox container."""
    return textwrap.dedent(
        f"""\
        #!/usr/bin/env bash
        set -euo pipefail

        tool="{tool}"
        desc="{description}"
        box="${{KYTH_AI_DEV_BOX:-{box}}}"

        if [[ -x "${{HOME}}/.local/bin/${{tool}}" ]]; then
        \texec "${{HOME}}/.local/bin/${{tool}}" "$@"
        fi

        if command -v distrobox >/dev/null 2>&1 && distrobox list --no-color 2>/dev/null | awk '{{print $3}}' | grep -qx "${{box}}"; then
        \texec distrobox enter "${{box}}" -- "${{tool}}" "$@"
        fi

        echo "${{desc}} is managed in the KythOS AI Developer container (${{box}})."
        echo "Initializing ${{box}} environment..."
        kyth-ai-dev setup
        exec distrobox enter "${{box}}" -- "${{tool}}" "$@"
        """,
    )


def write_distrobox_wrapper(
    target_path: Path,
    tool: str,
    description: str,
    box: str = "kyth-ai-dev",
) -> Path:
    """Write an executable wrapper script for a containerized tool."""
    target_path.parent.mkdir(parents=True, exist_ok=True)
    content = render_distrobox_wrapper(tool, description, box)
    tmp = target_path.with_suffix(".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.chmod(0o755)
    tmp.replace(target_path)
    return target_path
