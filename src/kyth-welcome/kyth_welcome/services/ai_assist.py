"""Hub-side re-export for the offline AI control plane.

Pure logic lives in `kyth_shared.ai_assist` so tests and CLI tools can
import without Qt. System Hub imports this thin facade.
"""
from __future__ import annotations

from kyth_shared.ai_assist import (  # noqa: F401 — re-export for Hub  # pylint: disable=unused-import
    AiAction,  # pylint: disable=unused-import
    AiPlan,  # pylint: disable=unused-import
    build_repair_plan,  # pylint: disable=unused-import
    generate_plan,  # pylint: disable=unused-import
    try_ollama_enhance,  # pylint: disable=unused-import
)
