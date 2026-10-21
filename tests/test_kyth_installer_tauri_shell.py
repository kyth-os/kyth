"""Contracts for the Phase 2 React/Tauri installer shell."""
from __future__ import annotations

import json
import pathlib
import re
import os
import subprocess
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
INSTALLER_WEB = ROOT / "src/kyth-installer-web"
SHELL_RS = INSTALLER_WEB / "src-tauri/src/main.rs"
NATIVE_RS = INSTALLER_WEB / "src-tauri/src/native_main.rs"
NATIVE_SLINT = INSTALLER_WEB / "src-tauri/ui/installer.slint"
LAUNCHER = ROOT / "build_files/kyth-launch-installer"
SERVER = ROOT / "src/kyth-installer/kyth_installer/server.py"


class InstallerTauriShellTests(unittest.TestCase):
    def test_wipe_relocates_recovery_journal_before_mount_hides_staging(self):
        source = (INSTALLER_WEB / "src-tauri/src/installer_job_executor.rs").read_text()
        image = source.split("    fn execute_image(", 1)[1].split("    fn ", 1)[0]
        self.assertLess(
            image.index("self.ensure_esp_journal(phase, cancellation)?;"),
            image.index("self.mount_wipe_root(phase, cancellation)?;"),
            "mounting install-root hides the tmpfs journal before relocation can read it",
        )

    def test_esp_assurance_is_read_only_without_remounting_journal_filesystem(self):
        source = (INSTALLER_WEB / "src-tauri/src/installer_assurance.rs").read_text()
        verify = source.split("fn verify_esp_bootloaders(", 1)[1].split("\nfn ", 1)[0]
        # A filesystem-wide `ro` mount conflicts with the ESP journal's RW
        # mount. The check must restrict only its own VFS mount to read-only.
        self.assertIn('.args(["-o", "ro=vfs", device])', verify)
        self.assertIn('Command::new("/usr/sbin/umount")', verify)

    def test_wipe_writes_esp_fstab_before_install_assurance(self):
        source = (INSTALLER_WEB / "src-tauri/src/installer_job_executor.rs").read_text()
        configure = source.split("    fn execute_configuration(", 1)[1].split("    fn ", 1)[0]
        self.assertIn('"wipe" =>', configure)
        self.assertIn("wipe_esp_fstab", configure)
        self.assertLess(configure.index("wipe_esp_fstab"), configure.index("installer_assurance::validate"))

    def test_only_image_phase_uses_udev_compatible_disk_lease(self):
        source = (INSTALLER_WEB / "src-tauri/src/installer_job_executor.rs").read_text()
        image = source.split("    fn execute_image(", 1)[1].split("    fn ", 1)[0]
        self.assertIn("installer_guard::acquire_bootc_disk_lock", image)
        self.assertEqual(source.count("installer_guard::acquire_bootc_disk_lock"), 1)
        self.assertIn("installer_guard::acquire_disk_lock", source)

    def test_native_shell_owns_the_first_parity_slice(self):
        rust = NATIVE_RS.read_text()
        slint = NATIVE_SLINT.read_text()
        for route in ("/api/start", "/api/cancel", "/api/reboot", "/api/rescue/logs-to-usb"):
            self.assertIn(route, rust)
        for field in ("install_mode", "hostname", "username", "password", "confirm_backup", "confirm_erase", "confirm_current"):
            self.assertIn(field, rust)
        for control in ("LineEdit", "CheckBox", "select-disk", "select-mode", "select-kernel", "start-install", "cancel-install", "rescue-probe", "reboot"):
            self.assertIn(control, slint)
        self.assertIn("post_json", rust)
        self.assertIn("ALLOWED", rust)
        self.assertIn("request_from_window", rust)

    def test_native_shell_validates_the_typed_plan_before_starting(self):
        rust = NATIVE_RS.read_text()
        self.assertIn("mod installer_plan;", rust)
        self.assertIn("fn validated_install_plan", rust)
        self.assertIn("installer_plan::build_plan", rust)
        self.assertIn("installer_validation::validate", rust)
        self.assertIn("install_plan_summary", rust)
        self.assertIn("validated_install_plan(&request)", rust)

    def test_native_shell_carries_guided_storage_choices_into_the_request(self):
        rust = NATIVE_RS.read_text()
        slint = NATIVE_SLINT.read_text()
        for route in ("/api/partitions?disk=", "/api/free-space?disk=", "storage_snapshot", "refresh_storage"):
            self.assertIn(route, rust)
        for field in ("target_partition", "free_region_start", "free_region_end", "resize_gib"):
            self.assertIn(f'"{field}"', rust)
        for control in ("storage-details", "partition-one", "free-region-one", "select-target-partition", "select-free-region", "resize-gib", "timezone", "locale", "keymap", "ComboBox", "timezone-options", "locale-options", "keymap-options"):
            self.assertIn(control, slint)
        self.assertIn('install_mode != "manual"', rust)
        self.assertIn('install-mode != "manual"', slint)
        self.assertIn("!part.current", rust)
        self.assertIn("!part.in_use", rust)
        self.assertIn('request.resize_partition = if window.get_install_mode().as_str() == "resize_ntfs"', rust)
        self.assertRegex(
            rust,
            re.escape('self.install_mode != "resize_ntfs"')
            + r"\s*\|\|\s*\(\s*!self\.resize_partition\.is_empty\(\)\s*&&\s*self\.resize_gib\s*>=\s*32\s*\)",
        )

    def test_native_install_uses_the_authenticated_event_stream(self):
        rust = NATIVE_RS.read_text()
        for marker in ("stream_install_events", "GET /api/stream", "text/event-stream", "data: ", "1800"):
            self.assertIn(marker, rust)
        for event_type in ("log", "progress", "phase", "done", "error"):
            self.assertIn(f'"{event_type}"', rust)

    def test_native_shell_decodes_transaction_reports_with_the_shared_rust_model(self):
        rust = NATIVE_RS.read_text()
        self.assertIn("mod installer_transaction;", rust)
        self.assertIn("installer_transaction::decode", rust)

    def test_native_shell_carries_manual_partition_actions_to_the_service(self):
        rust = NATIVE_RS.read_text()
        slint = NATIVE_SLINT.read_text()
        for route in (
            "/api/disk/new-table",
            "/api/disk/create",
            "/api/disk/delete",
            "/api/disk/resize",
            "/api/disk/format",
            "/api/disk/set-mountpoint",
            "/api/disk/pending/remove",
            "/api/disk/commit",
            "/api/disk/rollback",
        ):
            self.assertIn(route, rust)
        for action in ("new-table", "create", "delete", "resize", "format", "mountpoint", "remove-pending", "rollback", "commit"):
            self.assertIn(f'"{action}"', rust)
            self.assertIn(f'manual-action("{action}")', slint)
        for field in ("manual-filesystem", "manual-mountpoint", "manual-size-gib", "manual-committed"):
            self.assertIn(field, slint)
        self.assertIn('install_mode != "manual" || self.manual_committed', rust)

    def test_shell_embeds_assets_and_has_no_privileged_bridge(self):
        config = json.loads((INSTALLER_WEB / "src-tauri/tauri.conf.json").read_text())
        self.assertEqual(config["build"]["frontendDist"], "../dist")
        self.assertIn("127.0.0.1:7777", config["app"]["security"]["csp"])
        rust = SHELL_RS.read_text()
        # Test-only fixture helpers live in the cfg(test) module at the end
        # of the file; the bridge assertions apply to shipped code only.
        production = rust.split("#[cfg(test)]")[0]
        self.assertIn('const BACKEND_URL: &str = "http://127.0.0.1:7777";', production)
        self.assertIn("installer_connection", production)
        self.assertIn("installer_validate_plan", production)
        self.assertIn("installer_recovery_guidance", production)
        self.assertIn("installer_request", production)
        self.assertIn("installer_stream", production)
        self.assertIn("allowlisted_path", production)
        self.assertEqual(production.count("Command::new("), 1)
        self.assertIn("Command::new(program).args(args).spawn()", production)
        # Whitespace-tolerant: rustfmt may lay the tuples out over multiple
        # lines; the contract is absolute paths, never PATH lookup.
        self.assertRegex(
            production,
            r'\(\s*"/usr/bin/plasmawindowed"\s*,\s*&\["org\.kde\.plasma\.networkmanagement"\]\s*,?\s*\)',
        )
        self.assertRegex(
            production,
            r'\(\s*"/usr/bin/kcmshell6"\s*,\s*&\["kcm_networkmanagement"\]\s*,?\s*\)',
        )
        # The only filesystem read allowed in the unprivileged shell is the
        # launcher-written 0600 tokens file (--tokens-file): no writes, no
        # directory access, no generic bridge.
        self.assertNotIn("std::fs::write", production)
        self.assertNotIn("OpenOptions", production)
        self.assertNotIn("create_dir", production)
        self.assertNotIn("remove_file", production)
        self.assertIn("--tokens-file", rust)
        self.assertIn("load_tokens_file", rust)

    def test_launcher_starts_the_daemon_and_execs_the_native_shell(self):
        launcher = LAUNCHER.read_text()
        self.assertIn('if [ "$#" -ne 0 ]; then', launcher)
        self.assertIn("exit 64", launcher)
        self.assertIn('/usr/bin/sudo -n -- /usr/bin/kyth-launch-installer', launcher)
        self.assertIn('/usr/bin/flock -n 9', launcher)
        self.assertIn('exec 9>/run/lock/kyth-installer.lock', launcher)
        self.assertIn('/usr/bin/systemctl restart kyth-installerd.service', launcher)
        self.assertNotIn('/usr/bin/systemctl start kyth-installerd.service', launcher)
        self.assertIn('/usr/bin/systemctl is-active --quiet kyth-installerd.service', launcher)
        self.assertIn('KYTH_INSTALLER_SOCKET="${SOCKET_PATH}"', launcher)
        self.assertNotIn('KYTH_INSTALLER_SESSION_TOKEN="${session_token}"', launcher)
        self.assertIn('--tokens-file "${CLIENT_TOKEN_FILE}"', launcher)
        self.assertIn('/usr/bin/kyth-installer-shell --socket-path "${SOCKET_PATH}" --tokens-file "${CLIENT_TOKEN_FILE}"', launcher)
        self.assertNotIn("chromium", launcher.lower())
        self.assertNotIn("--no-sandbox", launcher)
        self.assertNotIn("kyth_installer", launcher)
        self.assertNotIn("app.py", launcher)
        self.assertNotIn("--bootstrap-token", launcher)

    def test_launcher_tokens_pass_both_shell_validators(self):
        """Exercise the shipped formatter and each real Rust token predicate."""
        launcher = LAUNCHER.read_text()
        formatter = next(line for line in launcher.splitlines()
                         if line.startswith("/usr/bin/printf '{\"bootstrap_token\""))
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            token_file = root / "tokens.json"
            session = "a" * 64
            subprocess.run(
                ["bash", "-eu", "-c", formatter], check=True,
                env={**os.environ, "session_token": session,
                     "bootstrap_token": "b" * 64, "CLIENT_TOKEN_TMP": str(token_file)},
            )
            tokens = json.loads(token_file.read_text())
            self.assertEqual(tokens["session_token"], session)
            for shell in (SHELL_RS, NATIVE_RS):
                match = re.search(
                    r"fn valid_child_token\(value: &str\) -> bool \{.*?\n\}",
                    shell.read_text(), re.DOTALL,
                )
                assert match is not None, f"token validator missing in {shell}"
                predicate = match.group(0)
                probe = root / "probe.rs"
                probe.write_text(predicate + "\nfn main() {\n"
                                 + f'assert!(valid_child_token({json.dumps(tokens["bootstrap_token"])}), "bootstrap rejected");\n'
                                 + f'assert!(valid_child_token({json.dumps(tokens["session_token"])}), "session rejected");\n'
                                 + "}\n")
                subprocess.run(["rustc", str(probe), "-o", str(root / "probe")], check=True)
                result = subprocess.run([str(root / "probe")], capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, f"{shell.name}: {result.stderr}")

    def test_frontend_uses_backend_token_and_fixed_dev_proxy(self):
        api = (INSTALLER_WEB / "src/api.ts").read_text()
        vite = (INSTALLER_WEB / "vite.config.ts").read_text()
        self.assertIn('invoke<InstallerConnection>("installer_connection")', api)
        self.assertIn('invoke("installer_validate_plan"', api)
        self.assertIn('invoke<NonNullable<RescueProbe["rescue_guidance"]>>("installer_recovery_guidance"', api)
        self.assertIn('X-Kyth-Session-Token', api)
        # The session token authenticates via header (mutating requests) and
        # the HttpOnly bootstrap cookie (SSE stream) — it must never appear
        # in a URL query string (request lines, devtools, proxy logs).
        self.assertNotIn("session_token=", api)
        self.assertIn("withCredentials", api)
        self.assertIn("127.0.0.1:7777", vite)

    def test_frontend_403_message_names_the_remedy(self):
        # Oct 9 leftover observation: a bare "Request failed (403)" left
        # users with no hint that the window's session token no longer
        # matches the daemon's, or what to do about it. The 403 branch of
        # the error mapping must name the state and the remedy.
        api = (INSTALLER_WEB / "src/api.ts").read_text()
        self.assertIn("status === 403", api)
        self.assertIn("out of sync (403)", api)
        self.assertIn("Close the installer and launch it again", api)

    def test_server_allows_only_tauri_cors_and_stream_auth(self):
        server = SERVER.read_text()
        self.assertIn('"http://tauri.localhost"', server)
        self.assertIn("Access-Control-Allow-Origin", server)
        self.assertIn("def do_OPTIONS", server)
        # Tokens must never travel in the query string (URLs land in logs
        # and history) — the stream uses the HttpOnly bootstrap cookie.
        self.assertIn("Tokens never", server)
        self.assertNotIn('get("session_token")', server)
        self.assertNotIn('Access-Control-Allow-Origin", "*"', server)

    def test_server_has_opt_in_unix_transport_with_peer_credentials(self):
        server = SERVER.read_text()
        config = (ROOT / "src/kyth-installer/kyth_installer/config.py").read_text()
        self.assertIn("class UnixSocketServer", server)
        self.assertIn("SO_PEERCRED", server)
        self.assertIn("SOCKET_PATH", config)
        self.assertIn("SOCKET_GROUP", config)

    def test_image_build_copies_shell_from_isolated_builder(self):
        containerfile = (ROOT / "installer/Containerfile").read_text()
        self.assertIn("AS installer-web-builder", containerfile)
        self.assertIn("npm ci && npm run build", containerfile)
        self.assertIn("cargo build --release --locked", containerfile)
        self.assertIn("--bin kyth-installer-native", containerfile)
        self.assertIn("--bin kyth-installer-exec", containerfile)
        self.assertIn("/build/kyth-installer-native", containerfile)
        self.assertIn("/build/kyth-installer-exec", containerfile)
        self.assertIn("/usr/bin/kyth-installer-native", containerfile)
        self.assertIn("/usr/bin/kyth-installer-exec", containerfile)
        self.assertIn("COPY --from=installer-web-builder", containerfile)
        build = (ROOT / "installer/build.sh").read_text()
        self.assertIn("webkit2gtk4.1", build)
        self.assertIn("gtk3", build)


    def test_capability_acl_covers_all_tauri_commands(self):
        # M10: installer-web must not rely on Tauri v2's local-origin
        # fail-open carve-out (removed in v3). The capabilities file must
        # exist, and every command in the invoke_handler must have a
        # matching allow-* permission generated by build.rs's AppManifest.
        capability = json.loads(
            (INSTALLER_WEB / "src-tauri/capabilities/default.json").read_text()
        )
        self.assertIn("main", capability["windows"])
        self.assertIn("core:default", capability["permissions"])
        rust = SHELL_RS.read_text()
        handler = re.search(
            r"\.invoke_handler\(\s*tauri::generate_handler!\[(.*?)\]\)",
            rust,
            re.DOTALL,
        )
        self.assertIsNotNone(handler, "invoke_handler not found in main.rs")
        commands = re.findall(r"^\s*(\w+),", handler.group(1), re.MULTILINE)
        self.assertGreater(len(commands), 0, "no commands found in invoke_handler")
        build_rs = (INSTALLER_WEB / "src-tauri/build.rs").read_text()
        for command in commands:
            permission = f"allow-{command.replace('_', '-')}"
            self.assertIn(
                permission,
                capability["permissions"],
                f"command {command} missing {permission} in capabilities",
            )
            self.assertIn(
                f'"{command}"',
                build_rs,
                f"command {command} missing from build.rs AppManifest",
            )


if __name__ == "__main__":
    unittest.main()
