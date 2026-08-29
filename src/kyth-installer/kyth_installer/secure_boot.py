"""Pure Secure Boot/MOK decision model shared by the privileged flow and tests."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class MokPlan:
    state: str
    action: str
    requires_password: bool
    requires_reboot_confirmation: bool
    message: str


def _skipped(message: str) -> MokPlan:
    return MokPlan("skipped", "none", False, False, message)


def plan_mok(
    *,
    kernel: str = "fedora",
    force_stage: bool = False,
    certificate_present: bool = False,
    mokutil_present: bool = False,
    secure_boot: str = "unknown",
    enrolled: str = "unknown",
    pending: str = "unknown",
) -> MokPlan:
    """Return the next MOK operation without touching firmware or secrets."""
    kernel = (kernel or "").strip().lower()
    secure_boot = (secure_boot or "unknown").strip().lower()
    enrolled = (enrolled or "unknown").strip().lower()
    pending = (pending or "unknown").strip().lower()
    if kernel not in {"fedora", "cachy"}:
        raise ValueError(f"unsupported kernel flavor: {kernel}")
    if kernel != "cachy" and not force_stage:
        return _skipped("standard KythOS kernel selected — custom-kernel MOK enrollment not staged")
    if not certificate_present:
        return _skipped("KythOS Secure Boot cert not found in live image — skipping enrollment staging")
    if not mokutil_present:
        return _skipped("mokutil not found — skipping enrollment staging")
    if secure_boot == "disabled":
        return _skipped("Secure Boot is not enabled — enrollment staging skipped")
    if secure_boot != "enabled":
        return MokPlan(
            "unknown", "probe", False, False,
            "Secure Boot state must be checked by the privileged service",
        )
    if enrolled == "yes":
        return MokPlan("enrolled", "none", False, False, "KythOS Secure Boot key already enrolled")
    if pending == "yes":
        return MokPlan(
            "pending", "none", False, True,
            "KythOS Secure Boot enrollment already staged — confirm it on next boot",
        )
    return MokPlan(
        "ready", "import-certificate", True, True,
        "KythOS Secure Boot enrollment can be staged",
    )


def classify_import(exit_code: int) -> str:
    return "staged" if exit_code == 0 else "failed"
