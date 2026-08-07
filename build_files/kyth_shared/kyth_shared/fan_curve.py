"""Adaptive fan/power curve — hwmon + powerd offline.

Hash-gated, 30s TTL like ai_perf_daemon. Drives fan pwm via hwmon + power cap via
ryzenadj/nvidia-smi under hardware_policy caps.
"""
from __future__ import annotations

import os
from pathlib import Path
import tomllib
from typing import Any

DEFAULT_FAN_PATH = Path("/etc/kyth/fan-curve.toml")


def fan_config_path(path: Path | None = None) -> Path:
    if path is not None:
        return Path(path)
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg and path is None and os.environ.get("KYTH_TEST_MODE") == "1":
        return Path(xdg) / "kyth" / "fan-curve.toml"
    return DEFAULT_FAN_PATH


def load_fan_curve(path: Path | None = None) -> dict[str, Any]:
    cfg_path = fan_config_path(path)
    try:
        data = tomllib.load(cfg_path.open("rb"))
    except (OSError, tomllib.TOMLDecodeError):
        return {"points": [[40, 30], [70, 80], [85, 100]], "power_cap_w": 0}
    pts = data.get("points", [[40, 30], [70, 80], [85, 100]])
    # normalize
    out_pts = []
    for p in pts:
        if isinstance(p, (list, tuple)) and len(p) == 2:
            try:
                out_pts.append([int(p[0]), int(p[1])])
            except Exception:
                continue
    if not out_pts:
        out_pts = [[40, 30], [70, 80], [85, 100]]
    cap = int(data.get("power_cap_w", 0) or 0)
    cap = max(0, min(300, cap))
    return {"points": out_pts, "power_cap_w": cap}


def save_fan_curve(curve: dict[str, Any], path: Path | None = None) -> Path:
    cfg_path = fan_config_path(path)
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    points = curve.get("points", [[40, 30], [70, 80], [85, 100]])
    cap = int(curve.get("power_cap_w", 0) or 0)
    lines = ["# Kyth fan curve — temp C -> pwm %, offline\n", "points = ["]
    for t, pwm in points:
        lines.append(f"  [{t}, {pwm}],")
    lines.append("]")
    lines.append(f"power_cap_w = {cap}")
    cfg_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return cfg_path


def pwm_for_temp(temp_c: float, points: list[list[int]] | None = None) -> int:
    if points is None:
        points = load_fan_curve()["points"]
    points = sorted(points, key=lambda x: x[0])
    if temp_c <= points[0][0]:
        return int(points[0][1])
    if temp_c >= points[-1][0]:
        return int(points[-1][1])
    for i in range(len(points) - 1):
        t0, p0 = points[i]
        t1, p1 = points[i + 1]
        if t0 <= temp_c <= t1:
            # linear
            frac = (temp_c - t0) / max(1, t1 - t0)
            return int(p0 + frac * (p1 - p0))
    return int(points[-1][1])
