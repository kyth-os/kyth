"""Contracts for lean-default image profiles and pinned third-party inputs."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


class BuildProfileTests(unittest.TestCase):
    def test_optional_image_profiles_default_off(self):
        dockerfile = _read("Dockerfile")
        for profile in ("ENABLE_GAMING_PERIPHERALS", "ENABLE_VIRTUALIZATION_HOST", "ENABLE_KSM"):
            self.assertIn(f"ARG {profile}=0", dockerfile)
            self.assertIn(f'{profile}="${{{profile}}}"', dockerfile)

    def test_common_controllers_remain_core_and_specialized_tools_are_profiled(self):
        core = _read("build_files/scripts/packages/06-gaming-core.sh")
        optional = _read("build_files/scripts/packages/07-gaming-optional-peripherals.sh")
        for package in ("game-devices-udev", "xpadneo", "xone", "dualsensectl", "joycond"):
            self.assertIn(package, core)
            self.assertNotIn(f"\t{package}\n", optional)
        self.assertIn('ENABLE_GAMING_PERIPHERALS:-0', optional)
        for package in ("opentabletdriver", "akmod-v4l2loopback", "ryzenadj", "cec-utils"):
            self.assertIn(package, optional)

    def test_vm_host_is_profiled_but_guest_agent_remains_available(self):
        baseline = _read("build_files/scripts/packages/05-baseline-desktop-tooling.sh")
        host = _read("build_files/scripts/packages/08-virtualization-host.sh")
        guest = _read("build_files/scripts/packages/13-gpu-amd-and-qemu-guest.sh")
        for package in ("qemu-system-x86-core", "qemu-img"):
            self.assertNotIn(package, baseline)
            self.assertIn(package, host)
        self.assertIn('ENABLE_VIRTUALIZATION_HOST:-0', host)
        self.assertIn("qemu-guest-agent", guest)

    def test_ksm_is_opt_in(self):
        source = _read("build_files/scripts/packages/10-ksmtuned.sh")
        self.assertIn('ENABLE_KSM:-0', source)
        self.assertLess(source.index('ENABLE_KSM:-0'), source.index("dnf5 install"))

    def test_smb_client_stack_remains_a_required_base_capability(self):
        windows_tools = _read("build_files/scripts/packages/21-windows-management-tools.sh")
        smoke = _read("build_files/kyth_shared/kyth_shared/smoke_check.py")
        self.assertIn("dnf5 install -y cifs-utils libsmbclient samba-client", windows_tools)
        self.assertIn('("smbclient", "SMB client")', smoke)
        self.assertIn('optional=command in {"fprintd", "pcscd"}', smoke)

    def test_third_party_downloads_use_exact_resolved_tags(self):
        resolver = _read("build_files/scripts/resolve-versions.py")
        self.assertIn("thirdparty-versions", resolver)
        self.assertNotIn("thirdparty-hash", resolver)

        version_vars = {"umu.sh": "UMU_VERSION"}
        for filename, variable in version_vars.items():
            source = _read(f"build_files/scripts/thirdparty/{filename}")
            self.assertNotIn("/releases/latest", source)
            self.assertIn(f"/releases/tags/${{{variable}}}", source)
            self.assertIn("${" + variable + ":?", source)

        proton = _read("build_files/scripts/proton-cachyos.sh")
        self.assertNotIn("/latest", proton)
        self.assertIn("/tags/${PROTON_CACHYOS_VER}", proton)
        self.assertIn("PROTON_CACHYOS_VER must be an exact release tag", proton)

    def test_ci_passes_and_records_exact_third_party_versions(self):
        workflow = _read(".github/workflows/build.yml")
        self.assertIn("--build-arg UMU_VERSION=", workflow)
        self.assertIn("org.kyth.build.umu-version", workflow)
        self.assertNotIn("LATENCYFLEX_VERSION", workflow)
        self.assertNotIn("SCX_VERSION", workflow)

    def test_scx_uses_fedora_package_and_kyth_owned_launcher(self):
        gaming = _read("build_files/scripts/packages/06-gaming-core.sh")
        thirdparty = _read("build_files/scripts/thirdparty.sh")
        loader = _read("build_files/kyth-scx-loader")
        self.assertRegex(gaming, r"dnf\w*\s+install.*scx_rusty")
        self.assertNotIn("install_scx", thirdparty)
        self.assertIn('^scx_[a-z0-9_]+$', loader)

    def test_dependent_workflows_require_successful_image_build(self):
        workflow = _read(".github/workflows/build.yml")
        self.assertGreaterEqual(workflow.count("needs.build_push.result == 'success'"), 2)


if __name__ == "__main__":
    unittest.main()
