from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHECKER = ROOT / "build_files/scripts/check-runtime-migration-inventory.py"
INVENTORY = ROOT / "build_files/config/runtime-migration-inventory.json"


def load_checker():
    spec = importlib.util.spec_from_file_location("runtime_inventory_checker", CHECKER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_checked_in_inventory_is_source_complete():
    checker = load_checker()
    document = json.loads(INVENTORY.read_text(encoding="utf-8"))
    expected = {item["path"] for item in checker.discover()}
    assert not checker.validate(document, expected_paths=expected)
    assert {item["surface"] for item in document["entries"]} >= {
        "launcher", "systemd-unit", "python-runtime", "installer-runtime", "ujust-recipe", "rust-crate"
    }


def test_checker_cli_passes():
    result = subprocess.run(
        [sys.executable, str(CHECKER)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "valid" in result.stdout


def test_inventory_preserves_actual_unit_execstart():
    entries = json.loads(INVENTORY.read_text(encoding="utf-8"))["entries"]
    unit = next(item for item in entries if item["path"] == "build_files/kyth-browser-wallet-defaults.service")
    assert unit["exec_start"] == ["/usr/bin/kyth-vscode-wallet"]


def test_inventory_distinguishes_native_install_from_retained_tunable_fixture():
    entries = json.loads(INVENTORY.read_text(encoding="utf-8"))["entries"]
    tunable = next(item for item in entries if item["path"] == "build_files/kyth-swappiness")
    assert tunable["current_implementation"] == "alias"
    assert tunable["installed_implementation"] == "rust"
    assert tunable["status"] == "done-native"
    assert tunable["owner"] == "native::kyth-tunable-rs"

def test_uninstalled_legacy_hub_privilege_fixture_is_not_an_active_authority():
    entries = json.loads(INVENTORY.read_text(encoding="utf-8"))["entries"]
    privileged = next(item for item in entries if item["path"] == "src/kyth-welcome/kyth_welcome/services/privileged.py")
    assert privileged["status"] == "explicitly-not-ported"
    assert privileged["installed_implementation"] == "not-installed"
    assert privileged["owner"].startswith("fixture::")
