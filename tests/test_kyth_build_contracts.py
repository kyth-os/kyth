"""Static contracts for artifacts assembled by the container build."""
from __future__ import annotations

import configparser
import re
import subprocess
import tempfile
import textwrap
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


class ValidationToolContracts(unittest.TestCase):
    def test_installer_exports_cached_bin_for_later_actions_steps(self):
        installer = (
            BUILD_FILES / "scripts/install-validation-tools.sh"
        ).read_text(encoding="utf-8")

        self.assertIn('if [[ -n "${GITHUB_PATH:-}" ]]', installer)
        self.assertIn(
            'printf \'%s\\n\' "${bin_dir}" >>"${GITHUB_PATH}"',
            installer,
        )


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
    def test_fedora_nvidia_devel_tracks_coordinated_latest_kernel(self):
        script = (
            BUILD_FILES / "scripts/packages/16-gpu-nvidia.sh"
        ).read_text(encoding="utf-8")
        upgrade = script.index("dnf5 upgrade -y --refresh")
        resolve = script.index("KERNEL_VR=$(rpm -q kernel-core")
        self.assertLess(upgrade, resolve)
        for package in (
            "kernel-core", "kernel-modules", "kernel-modules-core",
            "kernel-modules-extra",
        ):
            self.assertIn(package, script[upgrade:resolve])
        self.assertIn('"kernel-devel-${KERNEL_VR}"', script)
        self.assertIn('rpm --nodeps -e "${nevra}"', script)

    def test_fragment_relative_source_targets_exist(self):
        scripts = BUILD_FILES / "scripts"
        for tree in (scripts / "packages", scripts / "sysconfig"):
            for fragment in tree.rglob("*.sh"):
                body = fragment.read_text(encoding="utf-8")
                sources = re.findall(r'^\s*source\s+["\'](\.\.?/[^"\']+)["\']', body, re.M)
                for source in sources:
                    target = (fragment.parent / source).resolve()
                    with self.subTest(fragment=fragment.relative_to(ROOT), source=source):
                        self.assertTrue(target.is_file(), f"missing sourced helper: {target}")

    def test_fragment_runner_resolves_sources_from_fragment_directory(self):
        runner = BUILD_FILES / "scripts/lib/fragment-runner.sh"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            scripts = root / "scripts"
            fragments = scripts / "packages"
            helper_dir = scripts / "lib"
            unrelated_cwd = root / "unrelated"
            fragments.mkdir(parents=True)
            helper_dir.mkdir()
            unrelated_cwd.mkdir()

            (helper_dir / "helper.sh").write_text(
                'helper_value="resolved"\n', encoding="utf-8"
            )
            (fragments / "01-source-helper.sh").write_text(
                textwrap.dedent(
                    """\
                    #!/bin/bash
                    set -euo pipefail
                    source "../lib/helper.sh"
                    [[ "${helper_value}" == "resolved" ]]
                    """
                ),
                encoding="utf-8",
            )
            orchestrator = scripts / "run.sh"
            orchestrator.write_text(
                textwrap.dedent(
                    f"""\
                    #!/bin/bash
                    set -euo pipefail
                    source "{runner}"
                    run_fragments "packages" "bash"
                    """
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                ["bash", str(orchestrator)],
                cwd=unrelated_cwd,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(0, result.returncode, result.stderr)

    def test_standalone_container_scripts_anchor_helper_sources(self):
        scripts = BUILD_FILES / "scripts"
        standalone = (
            "kernel-repair.sh",
            "plymouth-initramfs.sh",
            "proton-cachyos.sh",
            "repair-current-plymouth-initramfs.sh",
        )
        for name in standalone:
            body = (scripts / name).read_text(encoding="utf-8")
            with self.subTest(script=name):
                self.assertIn('SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"', body)
                self.assertNotRegex(body, r'^\s*source\s+["\']lib/',)

    def test_packaged_installer_is_the_only_installation_entry_point(self):
        self.assertFalse((BUILD_FILES / "kyth-install.sh").exists())
        self.assertFalse((BUILD_FILES / "kyth-manual-install.sh").exists())
        installer = BUILD_FILES / "kyth-installer/pyproject.toml"
        launcher = BUILD_FILES / "kyth-launch-installer"
        self.assertIn('kyth-installer = "kyth_installer.app:main"', installer.read_text())
        self.assertIn("/usr/bin/kyth-installer", launcher.read_text())

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

    def test_build_time_python_imports_are_resolvable_in_build_context(self):
        dockerfile = (ROOT / "Dockerfile").read_text()
        package_scripts = (BUILD_FILES / "scripts/packages").glob("*.sh")
        all_content = "\n".join(p.read_text(encoding="utf-8") for p in package_scripts)
        python_imports = set(re.findall(r"from\s+([a-zA-Z0-9_]+)\b", all_content))
        python_imports.update(re.findall(r"import\s+([a-zA-Z0-9_]+)\b", all_content))
        for mod in python_imports:
            if mod in {"sys", "os", "json", "pathlib", "dataclasses", "typing", "subprocess", "shutil"}:
                continue
            if mod == "kyth_shared":
                self.assertIn("PYTHONPATH=\"/ctx/kyth_shared\"", dockerfile)
                self.assertIn("source=build_files/kyth_shared,target=/ctx/kyth_shared", dockerfile)

    def test_cups_browsed_is_purged_not_reinstalled_or_enabled(self):
        # cups-browsed is the legacy LAN printer auto-discovery daemon (2024 CUPS
        # RCE vector on UDP 631). It is deliberately dropped: the cleanup fragment
        # is the single source of truth for the purge, and nothing may quietly
        # re-add it to an install transaction or re-enable its service. Driverless
        # printing still works via cups + Avahi/mDNS.
        cleanup = BUILD_FILES / "scripts/packages/17-desktop-package-cleanup.sh"
        self.assertIn("cups-browsed", cleanup.read_text(encoding="utf-8"))
        for script in BUILD_FILES.rglob("*.sh"):
            text = script.read_text(encoding="utf-8")
            with self.subTest(script=script.relative_to(ROOT)):
                self.assertNotIn(
                    "enable cups-browsed", text,
                    f"{script.relative_to(ROOT)} re-enables purged cups-browsed",
                )
                for line in text.splitlines():
                    token = line.strip().rstrip("\\").strip()
                    if token == "cups-browsed" and script.name != cleanup.name:
                        self.fail(f"{script.relative_to(ROOT)} re-installs purged cups-browsed")


if __name__ == "__main__":
    unittest.main()
