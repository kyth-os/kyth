"""Hub-side re-export for the offline AI control plane.

Pure logic lives in `kyth_shared.ai_assist` so tests and CLI tools can
import without Qt. System Hub imports this thin facade.
"""
from __future__ import annotations

from kyth_shared.ai_assist import (  # noqa: F401 — re-export for Hub
    AiAction,
    AiPlan,
    build_repair_plan,
    generate_plan,
    try_ollama_enhance,
)
