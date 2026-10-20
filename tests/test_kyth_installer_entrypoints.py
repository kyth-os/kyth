import ast
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INSTALLER_ROOT = ROOT / "build_files" / "kyth-installer"
sys.path.insert(0, str(ROOT / "build_files" / "kyth_shared"))
sys.path.insert(0, str(INSTALLER_ROOT))


class InstallerEntrypointTests(unittest.TestCase):
    def test_python_entrypoint_compiles_and_imports_package_main(self):
        entrypoint = INSTALLER_ROOT / "kyth-installer"
        tree = ast.parse(entrypoint.read_text())
        imports_main = any(
            isinstance(node, ast.ImportFrom)
            and node.module == "kyth_installer.app"
            and any(alias.name == "main" for alias in node.names)
            for node in ast.walk(tree)
        )

        self.assertTrue(imports_main)

    def test_installer_package_imports_without_starting_browser(self):
        from kyth_installer import app, partition_cli, server  # noqa: PLC0415

        self.assertEqual(app.PORT, 7777)
        self.assertTrue(hasattr(server, "Handler"))
        self.assertTrue(callable(partition_cli.main))

    def test_desktop_launcher_shell_syntax(self):
        import subprocess  # noqa: PLC0415

        subprocess.run(
            ["bash", "-n", str(ROOT / "build_files" / "kyth-launch-installer")],
            check=True,
        )

    def test_live_image_installs_native_installer_runtime(self):
        containerfile = (ROOT / "installer" / "Containerfile").read_text()
        build_script = (ROOT / "installer" / "build.sh").read_text()

        self.assertIn("COPY --from=installer-web-builder /build/kyth-installer-shell /usr/bin/kyth-installer-shell", containerfile)
        self.assertIn("COPY --from=installer-web-builder /build/kyth-installerd /usr/bin/kyth-installerd", containerfile)
        self.assertIn("kyth-launch-installer", build_script)
        self.assertIn("kyth-installerd.service", build_script)
        self.assertNotIn("python3 -m pip install", build_script)
        self.assertNotIn("kyth-installer-package", build_script)

    def test_installer_socket_service_is_packaged_but_not_boot_enabled(self):
        unit = (ROOT / "build_files" / "kyth-installerd.service").read_text()
        build = (ROOT / "installer" / "build.sh").read_text()
        cargo = (ROOT / "src" / "kyth-installer-web" / "src-tauri" / "Cargo.toml").read_text()
        self.assertIn('name = "kyth-installerd"', cargo)
        self.assertIn("kyth-installerd.service", build)
        self.assertIn("/usr/bin/kyth-installerd", (ROOT / "installer" / "Containerfile").read_text())
        # A missing session token must fail visibly (daemon token validation
        # exits nonzero -> Restart=on-failure loop), never skip silently via
        # a path condition while the WebUI waits on the socket forever.
        conditions = [
            line for line in unit.splitlines()
            if line.startswith("ConditionPathExists=") and "session-token" in line
        ]
        self.assertEqual(conditions, [])
        self.assertIn("Restart=on-failure", unit)
        self.assertIn("User=root", unit)
        self.assertIn("Group=root", unit)
        self.assertIn("--socket-group liveuser", unit)
        self.assertNotIn("systemctl enable kyth-installerd.service", build)

    def test_installer_service_does_not_reown_launcher_session_tokens(self):
        unit = (ROOT / "build_files" / "kyth-installerd.service").read_text()
        launcher = (ROOT / "build_files" / "kyth-launch-installer").read_text()

        # The launcher places a 0600 tokens.json in a session-user-owned
        # directory below /run/kyth-installer. RuntimeDirectory on that same
        # path would recursively chown the tree to User=/Group= (root:root),
        # making the live user's token unreadable and causing an API 403.
        self.assertNotIn("RuntimeDirectory=kyth-installer", unit)
        self.assertIn('install -d -m 0750 -o root -g liveuser "${LAUNCH_DIR}"', launcher)
        self.assertIn('install -d -m 0700 -o "${session_user}" -g "${session_gid}" "${CLIENT_TOKEN_DIR}"', launcher)

    def test_installer_service_sandbox_allows_stdio_and_all_block_device_groups(self):
        unit = (ROOT / "build_files" / "kyth-installerd.service").read_text()
        device_policy = next(
            line for line in unit.splitlines() if line.startswith("DevicePolicy=")
        )
        device_allow = [
            line for line in unit.splitlines() if line.startswith("DeviceAllow=")
        ]

        # The daemon's default systemd stdin is /dev/null, and the installer
        # needs device-group matching for arbitrary disks. Path globs such as
        # /dev/nvme* are not valid DeviceAllow path selectors.
        self.assertEqual(device_policy, "DevicePolicy=closed")
        self.assertIn("DeviceAllow=block-* rw", device_allow)
        self.assertFalse(
            any(line.startswith("DeviceAllow=/dev/") and "*" in line for line in device_allow),
            "systemd DeviceAllow path entries do not support wildcards",
        )

    def test_launcher_preserves_only_fixed_installer_transport_settings(self):
        launcher = (ROOT / "build_files" / "kyth-launch-installer").read_text()
        sudoers = (ROOT / "installer" / "build.sh").read_text()
        self.assertIn("KYTH_INSTALLER_SOCKET", launcher)
        self.assertNotIn("KYTH_INSTALLER_SESSION_TOKEN", launcher)
        self.assertIn("--tokens-file", launcher)
        for name in ("KYTH_INSTALLER_SOCKET", "KYTH_INSTALLER_SOCKET_GROUP", "KYTH_INSTALLER_TOKEN_FILE"):
            self.assertIn(name, sudoers)


if __name__ == "__main__":
    unittest.main()
