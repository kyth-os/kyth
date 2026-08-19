"""VA-API / video decode probes."""
from __future__ import annotations

import glob
import os
import re
import subprocess

from .types import HardwareProbe
from ..process import run_command


def _vaapi_failure_summary(output: str) -> tuple[str, str]:
    lowered = output.lower()

    if "permission denied" in lowered or "failed to open render node" in lowered:
        return (
            "VA-API cannot access the GPU render device.",
            "Confirm your user has render/video device access, then sign out and back in.",
        )

    if "radeonsi_drv_video.so" in lowered and (
        "resource allocation failed" in lowered
        or "init failed" in lowered
        or "va_openDriver() returns 2" in output
    ):
        return (
            "AMD VA-API driver was found but could not initialize.",
            "Reboot after Mesa/GPU driver updates; if it persists, verify mesa-dri-drivers provides mesa-va-drivers and check Graphics for amdgpu status.",
        )

    if "failed to open" in lowered or "driver_name" in lowered or "va_openDriver" in output:
        return (
            "VA-API driver could not be opened.",
            "Verify the matching VA-API driver package is installed for this GPU and no stale LIBVA_DRIVER_NAME override is set.",
        )

    return (
        "VA-API initialisation failed.",
        "Confirm your GPU driver is loaded (see Graphics).",
    )
 # _vaapi_failure_summary

def _mesa_vaapi_failure_context() -> tuple[str, str]:
    rpm = run_command([
        "rpm",
        "-q",
        "--queryformat",
        "%{NAME} %{VERSION}-%{RELEASE}.%{ARCH}\n%{VENDOR}\n%{PACKAGER}\n",
        "mesa-dri-drivers",
        "mesa-vulkan-drivers",
        "libva",
    ], timeout=5)
    if rpm is None or rpm.returncode != 0:
        return "", ""

    details = rpm.stdout.strip()
    lowered = details.lower()
    if "negativo17" in lowered or "fedora-multimedia" in lowered:
        return (
            details,
            "Mesa/libva is installed from negativo17's fedora-multimedia repo; distro-sync the Mesa stack back to Fedora/RPM Fusion packages, then reboot.",
        )

    if "xxmitsu" in lowered or "copr" in lowered:
        return (
            details,
            "Mesa is installed from the mesa-git COPR; switch back to stable Fedora Mesa or wait for a fixed mesa-git snapshot.",
        )

    return details, ""
 # _mesa_vaapi_failure_context

def _compact_vaapi_failure_details(primary_output: str, direct_probe_details: list[str]) -> str:
    attempts = [("$ vainfo", primary_output.strip())]
    for detail in direct_probe_details:
        command, _, probe_output = detail.partition("\n")
        attempts.append((command.strip(), probe_output.strip()))

    attempt_lines = []
    drivers = []
    errors = []
    for command, probe_output in attempts:
        if not probe_output:
            continue
        display_match = re.search(r"Trying display:\s*([^\n]+)", probe_output)
        display = display_match.group(1).strip() if display_match else "default display"
        attempt_lines.append(f"{command}: {display}")

        for driver in re.findall(r"Trying to open\s+([^\s]+)", probe_output):
            if driver not in drivers:
                drivers.append(driver)

        for line in probe_output.splitlines():
            normalized = line.strip()
            lowered = normalized.lower()
            if (
                "error:" in lowered
                or "failed with error code" in lowered
                or "va_opendriver()" in lowered
            ) and normalized not in errors:
                errors.append(normalized)

    lines = []
    if attempt_lines:
        lines.append("Probe attempts:")
        lines.extend(f"- {attempt}" for attempt in attempt_lines)
    if drivers:
        lines.extend(["", "VA-API driver:"])
        lines.extend(f"- {driver}" for driver in drivers)
    if errors:
        lines.extend(["", "Failure reported:"])
        lines.extend(f"- {error}" for error in errors[:5])

    if not lines:
        return primary_output.strip()
    return "\n".join(lines)
 # _compact_vaapi_failure_details

def _vaapi_profiles(output: str) -> list[str]:
    lowered = output.lower()
    profiles = []
    if "h264" in lowered or "avc" in lowered:
        profiles.append("H.264")
    if "h265" in lowered or "hevc" in lowered:
        profiles.append("H.265")
    if "av1" in lowered:
        profiles.append("AV1")
    if "vp9" in lowered:
        profiles.append("VP9")
    if "vp8" in lowered:
        profiles.append("VP8")
    return profiles
 # _vaapi_profiles

def _successful_vaapi_probe(vainfo: subprocess.CompletedProcess[str] | None) -> tuple[list[str], str] | None:
    if vainfo is None:
        return None
    output = (vainfo.stdout + vainfo.stderr).strip()
    if vainfo.returncode != 0:
        return None
    profiles = _vaapi_profiles(output)
    if not profiles:
        return None
    return profiles, output
 # _successful_vaapi_probe

def _codec_probe() -> HardwareProbe:
    sw_driver = (
        os.environ.get("MESA_LOADER_DRIVER_OVERRIDE", "")
        or os.environ.get("GALLIUM_DRIVER", "")
    )
    if "llvmpipe" in sw_driver.lower():
        env_lines = "\n".join(
            f"{k}={os.environ[k]}"
            for k in ("MESA_LOADER_DRIVER_OVERRIDE", "GALLIUM_DRIVER", "LIBGL_ALWAYS_SOFTWARE")
            if k in os.environ
        )
        skel_file = os.path.expanduser("~/.config/plasma-workspace/env/10-kyth-qemu-safe.sh")
        source = skel_file if os.path.exists(skel_file) else "~/.config/plasma-workspace/env/"
        return HardwareProbe(
            "Video Decode", "warn",
            "Software rendering is active in this session — VA-API requires hardware GPU access.",
            f"{env_lines}\n\nSet by {source} (QEMU compatibility fallback active on bare metal).",
            f"Delete {skel_file} and log out/in to restore hardware rendering.",
        )

    vainfo = run_command(["vainfo"], timeout=10)
    if vainfo is None:
        return HardwareProbe(
            "Video Decode", "dim",
            "vainfo not available — cannot check VA-API support.",
            "Install libva-utils to inspect hardware video decode capabilities.",
        )

    direct_probe_details = []
    successful = _successful_vaapi_probe(vainfo)
    if successful is None:
        render_nodes = sorted(glob.glob("/dev/dri/renderD*"))
        for node in render_nodes:
            drm_vainfo = run_command(["vainfo", "--display", "drm", "--device", node], timeout=10)
            if drm_vainfo is not None:
                direct_probe_details.append(
                    f"$ vainfo --display drm --device {node}\n"
                    f"{(drm_vainfo.stdout + drm_vainfo.stderr).strip()}"
                )
            successful = _successful_vaapi_probe(drm_vainfo)
            if successful is not None:
                profiles, drm_output = successful
                details = [
                    "$ vainfo",
                    (vainfo.stdout + vainfo.stderr).strip(),
                    f"$ vainfo --display drm --device {node}",
                    drm_output,
                ]
                return HardwareProbe(
                    "Video Decode", "ok",
                    f"VA-API hardware decode: {', '.join(profiles)}.",
                    "\n\n".join(part for part in details if part),
                )
    else:
        profiles, output = successful
        return HardwareProbe(
            "Video Decode", "ok",
            f"VA-API hardware decode: {', '.join(profiles)}.",
            output,
        )

    output = (vainfo.stdout + vainfo.stderr)
    if vainfo.returncode != 0 and "failed" in output.lower():
        summary, recommendation = _vaapi_failure_summary(output)
        details = _compact_vaapi_failure_details(output, direct_probe_details)
        mesa_details, mesa_recommendation = _mesa_vaapi_failure_context()
        if mesa_details:
            details = f"{details}\n\nMesa package:\n{mesa_details}"
        if mesa_recommendation:
            recommendation = mesa_recommendation
        return HardwareProbe(
            "Video Decode", "warn",
            summary,
            details,
            recommendation,
        )

    profiles = _vaapi_profiles(output)
    if not profiles:
        return HardwareProbe(
            "Video Decode", "warn",
            "VA-API is available but no recognised decode profiles were found.",
            (vainfo.stdout + vainfo.stderr).strip(),
        )

    return HardwareProbe(
        "Video Decode", "ok",
        f"VA-API hardware decode: {', '.join(profiles)}.",
        (vainfo.stdout + vainfo.stderr).strip(),
    )
 # _codec_probe

