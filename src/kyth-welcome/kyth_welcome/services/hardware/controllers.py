"""Controller-page status decision tree (pure)."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ControllerStatusView:
    """What page_controllers.py should show after a probe, driven purely by
    _detect_controllers()'s result dict — no Qt, so the decision tree is
    testable without a display."""
    status_text: str
    xone_status_text: str
    xone_status_object_name: str
    xone_button_visible: bool
    dualsense_status_text: str
    dualsense_status_visible: bool
    secure_boot_warning_visible: bool


def controller_status_view(info: dict) -> ControllerStatusView:
    lines: list[str] = [f"  ✓  {name}" for name, _ in info["usb_controllers"]]
    for node in info["input_nodes"]:
        label = node.replace("usb-", "").replace("_", " ")
        lines.append(f"  ✓  {label}  (input node)")
    if not lines:
        status_text = "No controllers detected. Connect a controller and press Refresh."
    else:
        mods = []
        if info["xpadneo_loaded"]:
            mods.append("xpadneo")
        if info["xone_loaded"]:
            mods.append("xone_hid")
        if info["hid_ps_loaded"]:
            mods.append("hid_playstation")
        mod_line = f"\n  Active drivers: {', '.join(mods)}" if mods else ""
        status_text = "\n".join(lines) + mod_line

    if info["xone_dongle"] and not info["xone_loaded"]:
        xone_status_text = (
            "Xbox Wireless Adapter detected — firmware not yet flashed. "
            "Click the button below to complete setup (requires password)."
        )
        xone_status_object_name = "text-warn"
        xone_button_visible = True
    elif info["xone_dongle"] and info["xone_loaded"]:
        xone_status_text = (
            "✓  Xbox Wireless Adapter is ready. Press the sync button on the "
            "adapter and controller together to pair."
        )
        xone_status_object_name = "text-blue"
        xone_button_visible = False
    else:
        xone_status_text = "No Xbox Wireless Adapter detected. If you have one, plug it in and press Refresh."
        xone_status_object_name = "card-copy"
        xone_button_visible = False

    if info["dualsense_found"] and info["dualsensectl_out"]:
        dualsense_status_text = "DualSense connected — " + info["dualsensectl_out"].strip().splitlines()[0]
        dualsense_status_visible = True
    elif info["dualsense_found"]:
        dualsense_status_text = "✓  DualSense connected."
        dualsense_status_visible = True
    else:
        dualsense_status_text = ""
        dualsense_status_visible = False

    secure_boot_warning_visible = bool(
        info["secure_boot"] and (info["xone_dongle"] or not info["xpadneo_loaded"])
    )

    return ControllerStatusView(
        status_text=status_text,
        xone_status_text=xone_status_text,
        xone_status_object_name=xone_status_object_name,
        xone_button_visible=xone_button_visible,
        dualsense_status_text=dualsense_status_text,
        dualsense_status_visible=dualsense_status_visible,
        secure_boot_warning_visible=secure_boot_warning_visible,
    )
