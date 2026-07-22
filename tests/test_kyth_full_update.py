"""Contract tests for the KythOS-owned full updater."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "build_files" / "kyth-full-update"


def test_full_updater_is_executable_shell_script():
    assert SCRIPT.stat().st_mode & 0o111
    assert SCRIPT.read_text(encoding="utf-8").startswith("#!/usr/bin/env bash\n")


def test_full_updater_limits_scope_to_owned_surfaces():
    source = SCRIPT.read_text(encoding="utf-8")
    for expected in ("fwupdmgr", "flatpak update", "bootc upgrade", "kyth-rclone-update"):
        assert expected in source
    for excluded in ("pipx", "pip3", "npm ", "code --", "gh extension", "topgrade"):
        assert excluded not in source


def test_only_core_update_failures_are_fatal():
    source = SCRIPT.read_text(encoding="utf-8")
    assert 'run_step critical "Flatpak user packages"' in source
    assert 'run_step critical "Flatpak system packages"' in source
    assert 'run_step critical "KythOS system image"' in source
    assert 'run_step optional "Firmware upgrades"' in source
    assert 'run_step optional "KythOS rclone"' in source
