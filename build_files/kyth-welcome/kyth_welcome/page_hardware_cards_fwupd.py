"""Driver & Firmware card for HardwarePage — MOK and fwupd."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .page_hardware import HardwarePage


def make_driver_fwupd_card(page: "HardwarePage"):
    from .qt import QLabel, QPushButton, QHBoxLayout
    from .widgets import _make_card
    from .core_base import restyle
    from .services.process import run_command
    import pathlib

    card, layout = _make_card("card-accent-ok")
    title = QLabel("Driver & Firmware — MOK and fwupd")
    title.setObjectName("card-title")
    layout.addWidget(title)
    desc = QLabel(
        "Secure Boot MOK enrollment checked via mokutil --sb-state; firmware via fwupdmgr get-devices/get-updates (UpdateCoordinator transaction)."
    )
    desc.setObjectName("card-copy")
    desc.setWordWrap(True)
    layout.addWidget(desc)
    page._fwupd_status = QLabel("fwupd: not checked")
    page._fwupd_status.setObjectName("card-copy")
    page._fwupd_status.setWordWrap(True)
    layout.addWidget(page._fwupd_status)
    row = QHBoxLayout()
    row.setSpacing(8)
    check_btn = QPushButton("Check Firmware Updates")

    def _check():
        try:
            page._fwupd_status.setText("Checking fwupd...")
            restyle(page._fwupd_status)
            sb = run_command(["mokutil", "--sb-state"], timeout=5)
            mok = sb.stdout.strip().splitlines()[0] if sb and sb.returncode == 0 and sb.stdout else "mokutil unavailable"
            upd = run_command(["fwupdmgr", "get-updates"], timeout=15)
            upd_ok = upd is not None and upd.returncode == 0
            upd_stdout = upd.stdout if upd and upd.stdout else ""
            msg = f"{mok} — fwupd: {'updates available' if 'Updates' in upd_stdout else 'up to date' if upd_ok else 'fwupd unavailable'}"
            page._fwupd_status.setText(msg)
            page._fwupd_status.setObjectName("status-ok")
        except Exception as exc:
            page._fwupd_status.setText(f"Check failed: {exc}")
            page._fwupd_status.setObjectName("status-err")
        restyle(page._fwupd_status)

    check_btn.clicked.connect(lambda _=False: _check())
    row.addWidget(check_btn)
    enroll_btn = QPushButton("Enroll MOK (ujust)")
    enroll_btn.clicked.connect(
        lambda _=False: __import__("kyth_welcome.services.launch", fromlist=["popen"]).popen(["ujust", "enroll-mok"])
        if pathlib.Path("/usr/bin/ujust").exists()
        else page._fwupd_status.setText("ujust not found")
    )
    row.addWidget(enroll_btn)
    row.addStretch()
    layout.addLayout(row)
    return card
