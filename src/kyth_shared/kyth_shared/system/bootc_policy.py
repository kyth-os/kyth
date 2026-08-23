"""Pure bootc branch, update, cancellation, and presentation policy."""
from __future__ import annotations

import re
from dataclasses import dataclass

REGISTRY = "ghcr.io/kyth-os/kyth"


def default_phase(mode: str) -> str:
    return {
        "update": "Pulling OS image from container registry…",
        "full-update": "Running full system update…",
        "rollback": "Staging rollback deployment…",
    }.get(mode, "Operation in progress…")


def parse_update_phase(line: str, mode: str) -> str | None:
    lo = line.lower()
    rules = (
        (("layers already present", "layers needed"), "Checking for new image layers…"),
        (("unpacking", "extracting"), "Unpacking image layers…"),
        (("checking out", "checkout", "importing"), "Importing image into system storage…"),
        (("writing manifest", "manifest to image destination"), "Storing image manifest…"),
        (("rpmdb",), "Updating package database in the new image…"),
        (("initramfs", "kernel"), "Preparing boot files for the new image…"),
        (("deploying",), "Deploying new OS image…"),
        (("no update available", "already booted"), "Already on the latest image — nothing to download."),
    )
    if "resolved" in lo and ("image" in lo or REGISTRY in lo):
        return "Resolving OS image version…"
    if "fetching" in lo and ("manifest" in lo or "sha256" in lo):
        return "Fetching image manifest…"
    if any(k in lo for k in ("pulling", "copying", "fetching")) and any(
        k in lo for k in ("sha256", "blob", "layer", "ghcr.io", "registry")
    ):
        return "Downloading image layers…"
    for needles, message in rules:
        if any(needle in lo for needle in needles):
            return message
    if "writing" in lo or "composing" in lo or "committing" in lo:
        return "Writing new OS image to disk…"
    if "staging" in lo or "staged" in lo or "transaction complete" in lo:
        return "Staging new image for next reboot…"
    if "queued" in lo and "boot" in lo:
        return "Staged — new image ready for next reboot."
    if mode == "full-update" and line.startswith("――"):
        match = re.match(r"――\s*[\d:]+\s*-\s*(.+?)\s*――", line)
        if match and match.group(1).strip():
            return f"Updating {match.group(1).strip()}…"
    return None


def cancel_block_reason(mode: str, phase: str) -> str:
    if mode == "rollback":
        return "Rollback is already staging the previous deployment. Let it finish, then reboot or update again."
    unsafe = {
        "Unpacking image layers…", "Download complete — processing image layers…",
        "Processing image layers…", "Importing image into system storage…",
        "Storing image manifest…", "Writing new OS image to disk…",
        "Updating package database in the new image…",
        "Preparing boot files for the new image…", "Deploying new OS image…",
        "Staging new image for next reboot…", "Staged — new image ready for next reboot.",
    }
    if phase in unsafe:
        return "The operation is past the safe cancel point and is writing or staging the new image. Let it finish."
    if "writing image to disk" in phase.lower() or "committing image" in phase.lower():
        return "The operation is writing the new image. Let it finish."
    return ""


def branch_from_ref(ref: str | None) -> str | None:
    if not ref or not ref.strip():
        return None
    base = ref.strip().split("@", 1)[0]
    return base.rsplit(":", 1)[-1] if ":" in base else None


def branch_display_name(tag: str | None) -> str:
    return {
        "latest": "Stable (latest)", "testing": "Testing",
        "latest-cachy": "Stable + CachyOS kernel",
        "testing-cachy": "Testing + CachyOS kernel",
    }.get(tag, tag or "unknown")


def image_tag_for_channel(channel: str, flavor: str) -> str:
    base = "testing" if channel == "testing" else "latest"
    return f"{base}{'-cachy' if flavor == 'cachy' else ''}"


def image_tag_for_kernel(flavor: str, current_branch: str | None) -> str:
    channel = "testing" if (current_branch or "").startswith("testing") else "latest"
    return f"{channel}{'-cachy' if flavor == 'cachy' else ''}"


@dataclass(frozen=True)
class BranchCardView:
    object_name: str
    button_text: str
    build_label_text: str
    build_label_visible: bool


@dataclass(frozen=True)
class BranchesView:
    stable: BranchCardView
    testing: BranchCardView


def branches_view(tag: str | None, booted_ts: str | None) -> BranchesView:
    build_text = f"Running: built {booted_ts}" if booted_ts else ""
    stable = BranchCardView("branch-inactive", "Switch to Stable", "", False)
    testing = BranchCardView("branch-inactive", "Switch to Testing", "", False)
    if tag in ("latest", "latest-cachy"):
        stable = BranchCardView("branch-active", "On Stable  (current)", build_text, bool(booted_ts))
    elif tag in ("testing", "testing-cachy"):
        testing = BranchCardView("branch-active", "On Testing  (current)", build_text, bool(booted_ts))
    return BranchesView(stable, testing)


@dataclass(frozen=True)
class UpdateAvailabilityView:
    card_style: str
    icon_text: str
    icon_style: str
    title: str
    body: str
    update_btn_visible: bool
    restart_btn_visible: bool


def update_availability_view(
    *, staged: bool, check_state: str, flatpak_count: int,
    check_ts: str, check_ts_details: str, staged_ts: str | None,
) -> UpdateAvailabilityView:
    ts_hint = f"  ·  Checked at {check_ts}"
    built = f"  ·  built {check_ts_details}" if check_ts_details else ""
    if staged:
        built_staged = f"  ·  built {staged_ts}" if staged_ts else ""
        apps = ""
        if flatpak_count > 0:
            noun = "update" if flatpak_count == 1 else "updates"
            apps = f" Additionally, {flatpak_count} Flatpak {noun} can be installed."
        return UpdateAvailabilityView(
            "card-accent-ok", "↻", "avail-icon-blue", "Restart required",
            f"A new image is staged and waiting{built_staged}.{apps} Restart now or later — your current system stays available as a fallback.{ts_hint}",
            False, True,
        )
    if check_state == "available":
        apps = ""
        if flatpak_count > 0:
            noun = "update" if flatpak_count == 1 else "updates"
            apps = f" and {flatpak_count} Flatpak {noun} are pending"
        return UpdateAvailabilityView(
            "card-accent-warn", "↓", "avail-icon-warn", "Update available",
            f"A new system image is ready{built}{apps}. Run a full update to download and install them.{ts_hint}",
            True, False,
        )
    if flatpak_count > 0:
        noun = "update is" if flatpak_count == 1 else "updates are"
        return UpdateAvailabilityView(
            "card-accent-warn", "↓", "avail-icon-warn", "App updates available",
            f"Your system OS is up to date, but {flatpak_count} Flatpak app {noun} available. Run a full update to install them.{ts_hint}",
            True, False,
        )
    if check_state == "uptodate":
        return UpdateAvailabilityView(
            "card-accent-ok", "✓", "avail-icon-ok", "Up to date",
            f"Running the latest image{built}.{ts_hint}", False, False,
        )
    detail = (check_ts_details or "").strip()
    if "retryable" in detail.lower():
        body = f"{detail}{ts_hint}"
        return UpdateAvailabilityView(
            "card-accent-warn", "↻", "avail-icon-warn", "Update failed — Retry available",
            f"{body} Click Update Now to retry the download.",
            True, False,
        )
    if detail and detail.lower() not in {"checking timed out after 15 s. click check now to retry (skopeo/flatpak may be slow offline).".lower()}:
        body = f"{detail}{ts_hint}"
    else:
        body = f"Could not reach the update server — check your network connection.{ts_hint}"
    return UpdateAvailabilityView(
        "card", "⚠", "avail-icon-dim", "Check unavailable",
        body,
        False, False,
    )
