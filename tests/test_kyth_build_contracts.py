"""Static contracts for artifacts assembled by the container build."""
from __future__ import annotations

import configparser
import re
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
BUILD_FILES = ROOT / "build_files"


def _all_build_text() -> str:
    parts = []
    for path in BUILD_FILES.rglob("*"):
        if path.is_file() and path.suffix in {"", ".sh", ".py"}:
            try:
                parts.append(path.read_text(encoding="utf-8"))
            except UnicodeDecodeError:
                continue
    return "\n".join(parts)


class ShippedCommandContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.build_text = _all_build_text()
        cls.source_names = {path.name for path in BUILD_FILES.rglob("*") if path.is_file()}

    def _assert_kyth_target_is_staged(self, target: str, source: Path) -> None:
        name = Path(target).name
        self.assertIn(name, self.source_names, f"{source.relative_to(ROOT)} references missing {name}")
        self.assertIn(target, self.build_text, f"{target} is never installed into the image")

    def test_systemd_kyth_exec_targets_are_staged(self):
        units = list(BUILD_FILES.glob("*.service"))
        units.extend((BUILD_FILES / "kyth-scripts").glob("*.service"))
        for unit in units:
            for target in re.findall(r"^ExecStart(?:Pre|Post)?=(/usr/(?:bin|libexec)/kyth-[^\s'\"]+)", unit.read_text(), re.M):
                with self.subTest(unit=unit.name, target=target):
                    self._assert_kyth_target_is_staged(target, unit)

    def test_desktop_kyth_exec_targets_are_staged(self):
        for desktop in BUILD_FILES.rglob("*.desktop"):
            parser = configparser.ConfigParser(interpolation=None, strict=False)
            parser.read(desktop, encoding="utf-8")
            if not parser.has_section("Desktop Entry"):
                continue
            command = parser["Desktop Entry"].get("Exec", "")
            match = re.search(r"(/usr/bin/kyth-[^\s]+)", command)
            if match:
                with self.subTest(desktop=desktop.relative_to(ROOT)):
                    self._assert_kyth_target_is_staged(match.group(1), desktop)

    def test_custom_desktop_icons_are_installed(self):
        custom_icons = {"kyth"}
        icon_installer = (BUILD_FILES / "scripts/branding/14-icons.sh").read_text()
        for desktop in BUILD_FILES.rglob("*.desktop"):
            parser = configparser.ConfigParser(interpolation=None, strict=False)
            parser.read(desktop, encoding="utf-8")
            icon = parser.get("Desktop Entry", "Icon", fallback="")
            if icon in custom_icons:
                with self.subTest(desktop=desktop.relative_to(ROOT), icon=icon):
                    self.assertIn(f"{icon}.svg", icon_installer)


class BuildAssemblyContracts(unittest.TestCase):
    def test_installer_web_assets_referenced_by_html_and_server_exist(self):
        webui = BUILD_FILES / "kyth-installer/kyth_installer/webui"
        html = (webui / "index.html").read_text(encoding="utf-8")
        server = (webui.parent / "server.py").read_text(encoding="utf-8")
        references = set(re.findall(r"(?:src|href)=[\"']([^\"']+)[\"']", html))
        references.update(re.findall(r'_read_webui\\("([^"]+)"\\)', server))
        for reference in references:
            if "://" in reference:
                continue
            with self.subTest(asset=reference):
                self.assertTrue((webui / reference.lstrip("/")).is_file())

    def test_package_fragments_have_unique_order_prefixes(self):
        fragments = sorted((BUILD_FILES / "scripts/packages").glob("*.sh"))
        prefixes = [path.name.split("-", 1)[0] for path in fragments]
        self.assertTrue(fragments)
        self.assertEqual(len(prefixes), len(set(prefixes)))
        self.assertTrue(all(prefix.isdigit() and len(prefix) == 2 for prefix in prefixes))
        orchestrator = (BUILD_FILES / "scripts/packages-static.sh").read_text()
        self.assertIn('run_fragments "packages" "bash"', orchestrator)

    def test_build_profiles_are_wired_to_their_consumers(self):
        dockerfile = (ROOT / "Dockerfile").read_text()
        consumers = {
            "ENABLE_SCX": "packages-static.sh",
            "ENABLE_MESA_GIT": "mesa-git.sh",
            "ENABLE_GAMING_PERIPHERALS": "packages-static.sh",
            "ENABLE_VIRTUALIZATION_HOST": "packages-static.sh",
            "ENABLE_KSM": "packages-static.sh",
        }
        for argument, consumer in consumers.items():
            with self.subTest(argument=argument):
                self.assertIn(f"ARG {argument}=", dockerfile)
                self.assertIn(f"${{{argument}}}", dockerfile)
                self.assertIn(consumer, dockerfile)

    def test_branch_to_image_channel_mapping_is_explicit(self):
        workflow = (ROOT / ".github/workflows/build.yml").read_text()
        self.assertIn('branches=["main","testing"]', workflow)
        self.assertIn("matrix.branch == 'main' && 'latest' || matrix.branch", workflow)


if __name__ == "__main__":
    unittest.main()
