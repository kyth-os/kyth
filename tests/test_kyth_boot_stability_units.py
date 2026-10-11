"""Contracts for boot-path timeouts, MOK retry, and /boot mutator caps."""
from __future__ import annotations

import pathlib
import re
import subprocess
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth_shared"))
sys.path.insert(0, str(ROOT / "build_files" / "kyth-installer"))
SELINUX_UNIT = (
    ROOT / "build_files/scripts/sysconfig/systemd"
    / "32-selinux-relabel-var-home-after-each-new-deployment.sh"
)
BOOT_SPLASH = ROOT / "build_files/scripts/branding/28-bootc-kernel-arguments-and-boot-splash.sh"
ENROLL_SCRIPT = ROOT / "build_files/tests/secureboot-enrollment.sh"
VAR_HOME_ALIAS_FRAGMENT = (
    ROOT / "build_files/scripts/sysconfig/systemd/33-selinux-var-home-label-alias.sh"
)


class BootStabilityUnitTests(unittest.TestCase):
    def test_var_home_is_not_aliased_to_home_in_selinux_policy(self) -> None:
        """F45's "/var/home /home" subs rule left every home file as default_t.

        The alias rewrites lookups to /home/..., but the generated user-home rules
        are for /var/home/..., so nothing matched: xdm_t was denied the KWallet
        salt, pam_kwallet5 could not unlock at login and KWallet prompted for a
        password on first boot. Run the real fragment on a copy of F45's file.
        """
        import os
        import subprocess
        import tempfile

        original = (
            "/var/lib/xguest/home /home\n"
            "/home-inst           /home\n"
            "/home/home-inst      /home\n"
            "/var/home            /home\n"
            "/var/roothome        /root\n"
            "/var/home-backup     /keepme\n"
            "/var/homes /alsokeep\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            subs = os.path.join(tmp, "file_contexts.subs_dist")
            with open(subs, "w", encoding="utf-8") as handle:
                handle.write(original)
            os.chmod(subs, 0o644)
            env = {**os.environ, "KYTH_SELINUX_SUBS_DIST": subs}
            for _ in range(2):  # second pass must be a no-op
                result = subprocess.run(
                    ["bash", str(VAR_HOME_ALIAS_FRAGMENT)],
                    env=env,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
            with open(subs, encoding="utf-8") as handle:
                lines = handle.read().splitlines()
            self.assertNotIn("/var/home            /home", lines)
            self.assertFalse([l for l in lines if l.split()[:1] == ["/var/home"]])
            # Every other alias, including look-alike prefixes, is preserved.
            expected = [l for l in original.splitlines() if l.split()[:1] != ["/var/home"]]
            self.assertEqual(lines, expected)
            self.assertEqual(oct(os.stat(subs).st_mode & 0o777), "0o644")
            missing = subprocess.run(
                ["bash", str(VAR_HOME_ALIAS_FRAGMENT)],
                env={**env, "KYTH_SELINUX_SUBS_DIST": os.path.join(tmp, "absent")},
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(missing.returncode, 0, "absent policy file must not fail the build")

    def test_persisted_var_home_alias_is_removed_before_login_relabel(self) -> None:
        """The prior image's /etc overlay survives upgrades; remove its alias at boot."""
        import os
        import tempfile

        helper = ROOT / "build_files/scripts/sysconfig/kyth-selinux-var-home-alias"
        self.assertTrue(helper.is_file(), "install a runtime /var/home alias repair helper")
        unit = SELINUX_UNIT.read_text(encoding="utf-8")
        fast_unit = unit.split("RELABELEOF", 1)[1].split("RELABELEOF", 1)[0]
        self.assertIn("ExecStartPre=/usr/libexec/kyth-selinux-var-home-alias", fast_unit)
        self.assertLess(
            fast_unit.index("ExecStartPre=/usr/libexec/kyth-selinux-var-home-alias"),
            fast_unit.index("ExecStart=/usr/libexec/kyth-selinux-relabel-home"),
        )
        helper_source = (SELINUX_UNIT.parent / "../kyth-selinux-var-home-alias").resolve()
        self.assertTrue(helper_source.is_file(), "the image fragment must stage the runtime helper")
        self.assertIn(
            "install -m 0755 ../kyth-selinux-var-home-alias /usr/libexec/kyth-selinux-var-home-alias",
            unit,
        )

        original = "/var/home /home\n/var/home-backup /keep\n/var/roothome /root\n"
        with tempfile.TemporaryDirectory() as tmp:
            subs = pathlib.Path(tmp) / "file_contexts.subs_dist"
            subs.write_text(original, encoding="utf-8")
            env = {**os.environ, "KYTH_SELINUX_SUBS_DIST": str(subs)}
            for _ in range(2):
                result = subprocess.run(
                    ["bash", str(helper)], env=env, capture_output=True, text=True,
                    check=False,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                subs.read_text(encoding="utf-8"),
                "/var/home-backup /keep\n/var/roothome /root\n",
            )

    def test_kwallet_pam_bridge_does_not_duplicate_dash_prefixed_rules(self) -> None:
        """PAM's leading '-' suppresses missing-module logging; it does not disable the rule."""
        import os
        import tempfile

        helper = ROOT / "build_files/scripts/sysconfig/desktop/kyth-kwallet-pam-ensure"
        source = helper.read_text(encoding="utf-8")
        live_paths = "for PAM_FILE in /etc/pam.d/plasmalogin /usr/lib/pam.d/plasmalogin; do"
        self.assertIn(live_paths, source)

        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            pam_file = root / "plasmalogin"
            pam_file.write_text(
                "#%PAM-1.0\n-auth optional pam_kwallet5.so\n"
                "-auth optional pam_oo7.so\n"
                "-session optional pam_kwallet5.so auto_start\n"
                "auth     optional     pam_kwallet5.so\n"
                "session  optional  pam_exec.so /usr/libexec/kyth-kwallet-relabel\n"
                "session  optional     pam_kwallet5.so auto_start\n",
                encoding="utf-8",
            )
            isolated_helper = root / "ensure-pam"
            isolated_helper.write_text(
                source.replace(live_paths, f"for PAM_FILE in {pam_file}; do"),
                encoding="utf-8",
            )
            bin_dir = root / "bin"
            bin_dir.mkdir()
            rpm_stub = bin_dir / "rpm"
            rpm_stub.write_text(
                "#!/bin/sh\nprintf '%s\\n' /usr/lib64/security/pam_kwallet5.so\n",
                encoding="utf-8",
            )
            rpm_stub.chmod(0o755)
            env = {**os.environ, "PATH": f"{bin_dir}:/usr/bin:/bin"}

            for _ in range(2):
                result = subprocess.run(
                    ["bash", str(isolated_helper)], env=env, capture_output=True,
                    text=True, check=False,
                )
                self.assertEqual(result.returncode, 0, result.stderr)

            lines = pam_file.read_text(encoding="utf-8").splitlines()
            active_auth = [
                line for line in lines
                if re.match(r"^\s*-?auth\s+.*pam_kwallet5\.so(?:\s|$)", line)
            ]
            active_session = [
                (index, line) for index, line in enumerate(lines)
                if re.match(r"^\s*-?session\s+.*pam_kwallet5\.so.*auto_start", line)
            ]
            self.assertEqual(active_auth, ["-auth optional pam_kwallet5.so"])
            self.assertEqual(len(active_session), 1)
            index, _ = active_session[0]
            self.assertEqual(lines[index - 1], "session  optional  pam_exec.so /usr/libexec/kyth-kwallet-relabel")
            self.assertEqual(sum("kyth-kwallet-relabel" in line for line in lines), 1)
            self.assertEqual(
                sum("pam_oo7.so" in line and not line.lstrip().startswith("#") for line in lines),
                0,
            )

        build_fragment = (
            ROOT / "build_files/scripts/sysconfig/desktop/26-kwallet-pam-bridge-wire-pam-kwallet5-so-into-the-s.sh"
        ).read_text(encoding="utf-8")
        self.assertIn("^[[:space:]]*-?(auth|session)", build_fragment)
        self.assertIn("$0 ~ /^[[:space:]]*-?session[[:space:]]/", build_fragment)

    def test_selinux_home_relabel_is_capped_and_still_before_greeter(self) -> None:
        """The login-critical relabel must stay bounded and gate the greeter;
        the exhaustive full-tree pass must run separately, in the background,
        and must never be able to delay login. Before 27ca9887 these were one
        oneshot with a single 300s cap around a full `restorecon -RF`, which
        scales with home directory size — on a large home it can run past the
        cap, the completion stamp is never written, and every subsequent boot
        repeats the same doomed relabel instead of it costing once.
        """
        body = SELINUX_UNIT.read_text(encoding="utf-8")
        fast_unit = body.split("RELABELEOF", 1)[1].split("RELABELEOF", 1)[0]
        full_unit = body.split("RELABELFULLEOF", 1)[1].split("RELABELFULLEOF", 1)[0]
        # StartLimitIntervalSec/StartLimitBurst are only recognized in
        # [Unit] — systemd silently logs "Unknown key ... in section
        # [Service], ignoring" and drops both if they land in [Service].
        # Split each unit at its own [Service] header so the assertions
        # below actually pin *which* section a key lives in, instead of
        # matching anywhere in the file.
        # Split on the section *header line*, not a bare substring match —
        # both units' comments quote systemd's own "in section [Service]"
        # log message, which would otherwise split the string early.
        fast_unit_sec, fast_service_sec = fast_unit.split("\n[Service]\n", 1)
        full_unit_sec, full_service_sec = full_unit.split("\n[Service]\n", 1)

        self.assertIn("Before=plasmalogin.service display-manager.service", fast_unit)
        self.assertIn("TimeoutStartSec=60", fast_service_sec)
        # Rate limiting is disabled outright (not just tuned) on the unit
        # that gates plasmalogin.service — see kyth-selinux-relabel-home.
        self.assertIn("StartLimitIntervalSec=0", fast_unit_sec)
        self.assertIn("Conflicts=shutdown.target", fast_unit_sec)
        self.assertNotIn("StartLimit", fast_service_sec)
        self.assertNotIn("restorecon -RF -T0 /var/home", body.split("RELABELFULLEOF")[0])

        self.assertNotIn("Before=plasmalogin", full_unit)
        self.assertNotIn("Before=display-manager", full_unit)
        self.assertIn("Conflicts=shutdown.target", full_unit_sec)
        self.assertIn("IOSchedulingClass=idle", full_service_sec)
        self.assertIn("TimeoutStartSec=86400", full_service_sec)
        self.assertIn("StartLimitIntervalSec=3600", full_unit_sec)
        self.assertIn("StartLimitBurst=3", full_unit_sec)
        self.assertNotIn("StartLimit", full_service_sec)
        self.assertIn("kyth-selinux-relabel-home-full", body)

        fast_script = (
            SELINUX_UNIT.parents[1] / "kyth-selinux-relabel-home"
        ).read_text(encoding="utf-8")
        full_script = (
            SELINUX_UNIT.parents[1] / "kyth-selinux-relabel-home-full"
        ).read_text(encoding="utf-8")
        # The login-critical script must never recurse into a user's bulk
        # data — that would reintroduce the same size-dependent stall.
        self.assertNotIn("restorecon -RF", fast_script)
        self.assertNotIn("restorecon -RF -T0 /var/home", fast_script)
        self.assertIn("restorecon -RF -D -T0", full_script)
        self.assertIn("selinux-relabel-home-full.stamp", full_script)
        self.assertIn("selinux-relabel-home.stamp", fast_script)
        # Both scripts run under set -euo pipefail; a failing `ostree admin
        # status` (seen in the field as a silent status=1/FAILURE with no
        # script output at all) must fall through to the /proc/cmdline and
        # stat(1) fallbacks below it, not abort the script outright.
        for script in (fast_script, full_script):
            deployment_block = script.split("deployment_id=\"\"", 1)[1].split(
                "if [ -z \"$deployment_id\" ] && [ -r /proc/cmdline ]", 1
            )[0]
            self.assertIn("awk '/^\\* /{print $2\" \"$3; exit}')\" || true", deployment_block)
        # The top-level restorecon must not be able to hard-fail the whole
        # script the way the per-home loop below it is already guarded.
        self.assertNotIn("\n/sbin/restorecon -F /var/home\n", fast_script)

    def test_full_home_relabel_stamps_selinux_policy_fingerprint(self) -> None:
        """A deployment-only stamp needlessly repeats multi-hour scans after
        every OS update; the full pass should rerun when the active file
        contexts change, not merely when the deployment id changes.
        """
        shared = (ROOT / "src/kyth-shared-rs/src/system/selinux_relabel.rs").read_text(
            encoding="utf-8"
        )
        full_bin = (ROOT / "src/kyth-shared-rs/src/selinux_relabel_home_full_bin.rs").read_text(
            encoding="utf-8"
        )
        self.assertIn("active_file_contexts_fingerprint", shared)
        self.assertIn("full_relabel_stamp", full_bin)
        self.assertNotIn("already_done(&stamp_dir, STAMP, &deployment)", full_bin)

    def test_full_relabel_uses_resumable_digests_and_long_timeout(self) -> None:
        unit = SELINUX_UNIT.read_text(encoding="utf-8")
        shared = (ROOT / "src/kyth-shared-rs/src/system/selinux_relabel.rs").read_text(
            encoding="utf-8"
        )
        full_bin = (ROOT / "src/kyth-shared-rs/src/selinux_relabel_home_full_bin.rs").read_text(
            encoding="utf-8"
        )
        full_script = (
            SELINUX_UNIT.parents[1] / "kyth-selinux-relabel-home-full"
        ).read_text(encoding="utf-8")
        full_service = unit.split("RELABELFULLEOF", 1)[1].split("RELABELFULLEOF", 1)[0]
        self.assertIn("TimeoutStartSec=86400", full_service)
        self.assertIn("full_restorecon_argv", full_bin)
        self.assertIn('"-D".to_string()', shared)
        self.assertIn("restorecon -RF -D -T0", full_script)

    def test_full_relabel_excludes_rootless_overlay_from_digest_walk(self) -> None:
        """restorecon -D writes security.sehash on every directory.

        Overlayfs copy-up of those directories in a rootless user namespace
        returns EPERM, so dnf/apt inside distrobox cannot replace files that
        still live only in the image layer. The full-home walk must exclude
        rootless overlay storage and strip leftover sehash xattrs.
        """
        full_bin = (ROOT / "src/kyth-shared-rs/src/selinux_relabel_home_full_bin.rs").read_text(
            encoding="utf-8"
        )
        shared = (ROOT / "src/kyth-shared-rs/src/system/selinux_relabel.rs").read_text(
            encoding="utf-8"
        )
        full_script = (
            SELINUX_UNIT.parents[1] / "kyth-selinux-relabel-home-full"
        ).read_text(encoding="utf-8")
        self.assertIn("overlay_exclude_paths", full_bin)
        self.assertIn("overlay_sehash_cleanup_argv", full_bin)
        self.assertIn("restorecon_xattr", shared)
        self.assertIn("storage/overlay", full_script)
        self.assertIn("restorecon_xattr", full_script)
        self.assertNotIn("/sbin/restorecon -RF -D -T0 /var/home\n", full_script)

    def test_plocate_prunes_cache_dependency_and_metadata_trees_without_replacing_vendor_defaults(self) -> None:
        script_path = (
            ROOT
            / "build_files/scripts/sysconfig/systemd/44-plocate-home-cache-pruning.sh"
        )
        self.assertTrue(script_path.is_file(), "install an updatedb drop-in for cache pruning")
        script = script_path.read_text(encoding="utf-8")
        self.assertIn("plocate-updatedb.service.d/50-kyth-home-cache-pruning.conf", script)
        self.assertIn("ExecStart=", script)
        self.assertNotIn("PRUNEFS=", script)
        self.assertNotIn("PRUNEPATHS=", script)
        self.assertIn(
            'ExecStart=/usr/bin/updatedb --add-prunenames ".cache .git node_modules shadercache"',
            script,
        )

    def test_boot_mutators_have_timeouts_and_path_trigger_limit(self) -> None:
        body = BOOT_SPLASH.read_text(encoding="utf-8")
        self.assertIn("kyth-boot-splash-kargs.service", body)
        self.assertIn("kyth-boot-branding.service", body)
        self.assertIn("kyth-boot-splash-initramfs.service", body)
        self.assertGreaterEqual(body.count("TimeoutStartSec=60"), 2)
        # initramfs refresh must outlast the binary's dracut budget (2x600s);
        # a shorter timeout SIGTERMs dracut mid-run.
        self.assertIn("TimeoutStartSec=1260", body)
        self.assertIn("TriggerLimitIntervalSec=10", body)
        self.assertIn("TriggerLimitBurst=5", body)

    def test_secureboot_enrollment_does_not_stamp_flag_on_import_failure(self) -> None:
        result = subprocess.run(
            ["bash", str(ENROLL_SCRIPT)],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn("secureboot enrollment tests passed", result.stdout)

    def test_sched_user_unit_does_not_order_on_system_loader(self) -> None:
        # kyth-sched.service runs in the user manager, which cannot order on
        # system units — Wants=/After= scx_loader.service never took effect.
        # Loader absence is covered by a bounded retry in code instead.
        body = (ROOT / "build_files/kyth-sched.service").read_text(encoding="utf-8")
        directives = [
            line.split("=", 1)[0].strip()
            for line in body.splitlines()
            if "scx_loader.service" in line and not line.lstrip().startswith("#")
        ]
        self.assertEqual(directives, [])
        self.assertIn("After=graphical-session.target", body)

    def test_privileged_service_restarts_on_failure(self) -> None:
        body = (ROOT / "build_files/kyth-privileged.service").read_text(encoding="utf-8")
        self.assertIn("Restart=on-failure", body)
        self.assertIn("RestartSec=2", body)

    def test_sched_and_telem_install_as_user_units(self) -> None:
        body = (ROOT / "build_files/scripts/branding/27-performance-daemons.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn("/usr/lib/systemd/user/kyth-sched.service", body)
        self.assertIn("/usr/lib/systemd/user/kyth-telem.service", body)
        self.assertNotIn("/usr/lib/systemd/system/kyth-sched.service", body)
        self.assertNotIn("/usr/lib/systemd/system/kyth-telem.service", body)

    def test_privileged_service_writable_paths_are_created_in_the_image(self) -> None:
        """ProtectSystem=strict requires ReadWritePaths to exist before launch."""
        body = (ROOT / "build_files/scripts/branding/27-performance-daemons.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn("install -d -m 0755 /var/cache/kyth /var/log/kyth", body)

    def test_restart_limited_units_cap_start_burst(self) -> None:
        units = (
            ROOT / "build_files/kyth-batteryd.service",
            ROOT / "build_files/rclone@.service",
            ROOT / "build_files/kyth-telem.service",
            ROOT / "build_files/kyth-privileged.service",
        )
        for path in units:
            body = path.read_text(encoding="utf-8")
            with self.subTest(unit=path.name):
                self.assertIn("StartLimitIntervalSec=60", body)
                self.assertIn("StartLimitBurst=3", body)
                self.assertIn("RestartSec=", body)
        zram = (ROOT / "build_files/scripts/branding/51-zram.sh").read_text(encoding="utf-8")
        self.assertIn("StartLimitIntervalSec=60", zram)
        self.assertIn("StartLimitBurst=3", zram)
        # oneshot + RemainAfterExit cannot use Restart=; keep a start-limit
        # so a crash loop still cannot take the boot. The arbiter unit is
        # generated at build time, so audit the generator script instead of
        # a repo copy (the stale shadow has been removed).
        generated = (
            ROOT / "build_files/scripts/sysconfig/gaming/15-sched-arbiter.sh"
        ).read_text(encoding="utf-8")
        self.assertIn("StartLimitIntervalSec=60", generated)
        self.assertIn("StartLimitBurst=3", generated)
        self.assertNotRegex(generated, r"^Restart=", re.M)
        self.assertIn("After=local-fs.target", generated)
        self.assertNotIn("Restart=on-failure", generated)
        self.assertNotRegex(generated, r"^After=multi-user\.target$", re.M)

    def test_zram_setup_does_not_wait_for_udev_device(self) -> None:
        """After switch-root, udevd is down until sysinit; sysinit After=swap.
        Waiting for dev-zram0.device is a 30s timeout every boot.
        """
        zram = (ROOT / "build_files/scripts/branding/51-zram.sh").read_text(encoding="utf-8")
        ntsync = (
            ROOT / "build_files/scripts/sysconfig/kernel/13-ntsync.sh"
        ).read_text(encoding="utf-8")
        self.assertIn("kyth-zram-swap.service", zram)
        self.assertIn("mknod -m 0600 /dev/zram0", zram)
        self.assertIn("After=systemd-modules-load.service", zram)
        self.assertIn("Before=swap.target", zram)
        self.assertNotIn("After=systemd-udevd.service", zram)
        self.assertNotIn("After=dev-zram0.device", zram)
        self.assertNotIn("Requires=dev-zram0.device", zram)
        self.assertIn("system-generators/zram-generator", zram)
        self.assertIn("systemctl mask", zram)
        self.assertIn("dev-zram0.device", zram)
        self.assertIn("dev-zram0.swap", zram)
        self.assertIn("systemd-zram-setup@zram0.service", zram)
        self.assertNotIn("JobTimeoutSec=30", ntsync)
        self.assertNotIn("dev-zram0.device.d", ntsync)

    def test_zram_swap_sources_a_plain_contract_instead_of_parsing_generator_syntax(
        self,
    ) -> None:
        """kyth-zram-swap must not re-derive memory_tune's formula by
        pattern-matching zram-generator.conf's math-expression grammar — a
        format this project owns the writer of but that script doesn't parse.
        A new shape memory_tune emits (that the old awk `case` didn't
        enumerate) would silently fall back to the wrong tier instead of
        erroring. It should source memory_tune's plain key=value sidecar
        file instead.
        """
        zram = (ROOT / "build_files/scripts/branding/51-zram.sh").read_text(encoding="utf-8")
        self.assertIn("/etc/kyth/zram-runtime.env", zram)
        self.assertIn("KYTH_ZRAM_PERCENT", zram)
        self.assertIn("KYTH_ZRAM_CAP_MB", zram)
        self.assertIn("KYTH_ZRAM_ALGO", zram)
        # The old awk one-liners only recognized a fixed set of formula
        # shapes memory_tune happened to emit at the time they were written.
        self.assertNotIn("awk -F=", zram)
        self.assertNotIn("min(ram*0.5,8192)", zram)

    def test_memory_tune_applies_only_its_own_sysctl_file(self) -> None:
        body = (ROOT / "build_files/scripts/sysconfig/kernel/56-memory-tune.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn("sysctl --load=/etc/sysctl.d/99-kyth-memory.conf", body)
        self.assertIn("ExecStartPost=-/usr/bin/sysctl --load=/etc/sysctl.d/99-kyth-memory.conf", body)
        self.assertNotIn("ExecStartPost=/usr/bin/sysctl --system", body)
        self.assertNotIn("sudo sysctl --system", body)
        self.assertIn("After=local-fs.target systemd-sysctl.service", body)
        self.assertNotRegex(body, r"^After=multi-user\.target$", re.M)

    def test_irqbalance_args_only_use_options_the_shipped_daemon_accepts(self) -> None:
        """irqbalance 1.9.x has no --hintpolicy; passing it kills the unit at start."""
        body = (ROOT / "build_files/scripts/sysconfig/systemd/05-irqbalance-tuning.sh").read_text(
            encoding="utf-8"
        )
        args = next(
            line for line in body.splitlines() if line.startswith("IRQBALANCE_ARGS=")
        )
        self.assertNotIn("--hintpolicy", args)
        self.assertIn("--deepestcache=2", args)

    def test_irqbalance_oneshot_does_not_fail_type_simple(self) -> None:
        body = (ROOT / "build_files/scripts/sysconfig/systemd/05-irqbalance-tuning.sh").read_text(
            encoding="utf-8"
        )
        late = (ROOT / "build_files/scripts/sysconfig/kernel/48-irqbalance-tuning.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn("IRQBALANCE_ONESHOT=yes", body)
        self.assertIn("irqbalance.service.d/10-kyth-oneshot.conf", body)
        self.assertIn("Type=oneshot", body)
        self.assertIn("RemainAfterExit=yes", body)
        self.assertIn("--deepestcache=2", body)
        self.assertNotIn("write_config /etc/sysconfig/irqbalance", late)

    def test_ntsync_device_is_usable_by_the_logged_in_user(self) -> None:
        """Nobody is in the 'users' group, so a group-only rule left /dev/ntsync unusable."""
        body = (ROOT / "build_files/scripts/sysconfig/kernel/13-ntsync.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn('TAG+="uaccess"', body)
        rule_path = next(
            part.split(" ")[-1]
            for part in body.splitlines()
            if part.startswith("write_line") and "ntsync.rules" in part
        )
        name = rule_path.rsplit("/", 1)[1]
        # uaccess is applied by 73-seat-late.rules, so the tag must be set earlier.
        self.assertLess(int(name.split("-", 1)[0]), 73, name)
        self.assertIn("rm -f /usr/lib/udev/rules.d/99-ntsync.rules", body)

    def test_system_accounts_unit_cannot_form_an_ordering_cycle(self) -> None:
        """After=local-fs.target and Before=systemd-sysusers.service are a cycle.

        sysusers < tmpfiles-setup-dev < local-fs-pre.target < local-fs.target, so a
        unit After=local-fs.target cannot also be Before=sysusers. systemd resolved
        it by deleting a job on every boot, and validate.sh used to mask the
        warning, which is how it shipped.
        """
        body = (
            ROOT / "build_files/scripts/sysconfig/desktop/09-autostart-log-noise-guards.sh"
        ).read_text(encoding="utf-8")
        unit = body.split("SYSACCOUNTUNITEOF", 1)[1].split("SYSACCOUNTUNITEOF", 1)[0]
        directives = [line for line in unit.splitlines() if not line.lstrip().startswith("#")]
        after = " ".join(line for line in directives if line.startswith("After="))
        before = " ".join(line for line in directives if line.startswith("Before="))
        self.assertIn("local-fs.target", after)
        self.assertNotIn("systemd-sysusers.service", before)
        # It must still run before the consumers of the merged account databases.
        self.assertIn("systemd-tmpfiles-setup.service", before)
        self.assertIn("systemd-udevd.service", before)
        validate = (ROOT / "build_files/scripts/validate.sh").read_text(encoding="utf-8")
        # The cycle may only be tolerated while the *installed* host unit still
        # carries the stale edge; never unconditionally.
        self.assertIn("stale_host_cycle_filter", validate)
        self.assertIn(
            "host_accounts_unit=/usr/lib/systemd/system/kyth-system-accounts.service",
            validate,
        )
        self.assertNotIn("kyth-system-accounts\\.service): .*' ||", validate)

    def test_dbus_runtime_dir_stays_active_after_mkdir(self) -> None:
        body = (
            ROOT / "build_files/scripts/sysconfig/desktop/09-autostart-log-noise-guards.sh"
        ).read_text(encoding="utf-8")
        dbus_unit = body.split("DBUSRUNDIREOF", 1)[1].split("DBUSRUNDIREOF", 1)[0]
        # StartLimitIntervalSec/StartLimitBurst are only recognized in
        # [Unit] — stranded in [Service] they are silently dropped and the
        # unit runs under systemd's compiled-in 10s/5 default instead.
        unit_sec, service_sec = dbus_unit.split("\n[Service]\n", 1)
        self.assertIn("RemainAfterExit=yes", service_sec)
        self.assertIn("StartLimitIntervalSec=0", unit_sec)
        self.assertNotIn("StartLimit", service_sec)

    def test_asus_dbus_policy_fixup_disables_start_limit(self) -> None:
        body = (
            ROOT / "build_files/scripts/sysconfig/hardware/57-asus-dbus-policy-fixup.sh"
        ).read_text(encoding="utf-8")
        unit = body.split("ASUSDBUSUNITEOF", 1)[1].split("ASUSDBUSUNITEOF", 1)[0]
        # StartLimitIntervalSec/StartLimitBurst are only recognized in
        # [Unit] — stranded in [Service] they are silently dropped and the
        # unit runs under systemd's compiled-in 10s/5 default instead.
        unit_sec, service_sec = unit.split("\n[Service]\n", 1)
        self.assertIn("StartLimitIntervalSec=0", unit_sec)
        self.assertNotIn("StartLimit", service_sec)
        self.assertIn("RemainAfterExit=yes", service_sec)

    def test_local_bin_migrate_can_write_state_and_homes(self) -> None:
        body = (ROOT / "build_files/kyth-local-bin-migrate.service").read_text(
            encoding="utf-8"
        )
        self.assertIn("RemainAfterExit=yes", body)
        self.assertIn("StateDirectory=kyth/migrations", body)
        self.assertIn("ReadWritePaths=-/root", body)
        self.assertNotIn("PrivateUsers=yes", body)

    def test_flathub_setup_skips_offline_and_can_write_flatpak_state(self) -> None:
        body = (ROOT / "build_files/kyth-flathub-setup.service").read_text(
            encoding="utf-8"
        )
        self.assertIn("Wants=network-online.target", body)
        self.assertNotIn("Requires=network-online.target", body)
        self.assertIn("ExecCondition=", body)
        self.assertIn("ReadWritePaths=-/var/lib/flatpak -/var/cache/flatpak", body)
        self.assertNotIn("PrivateUsers=yes", body)
        self.assertIn("exit 0", body.split("ExecStart=", 1)[1])

    def test_live_owe_autoconnect_counts_connected_wifi_as_a_single_number(self) -> None:
        """`grep -c ... || echo 0` yields "0\\n0" when nothing matches, which made
        the numeric test error out and skipped the one auto-connect case."""
        import os
        import subprocess
        import tempfile

        script = (ROOT / "build_files/scripts/kyth-live-owe-wifi-setup.sh").read_text(encoding="utf-8")
        line = next(l for l in script.splitlines() if l.startswith("wifi_connected=$(nmcli"))
        default = next(l for l in script.splitlines() if l.startswith("wifi_connected=${wifi_connected"))
        self.assertNotIn("|| echo", line)
        cases = (("wlp1:wifi:disconnected\\nlo:loopback:unmanaged\\n", "0"), ("wlp1:wifi:connected\\n", "1"))
        for nmcli_output, expected in cases:
            with tempfile.TemporaryDirectory() as tmp:
                stub = os.path.join(tmp, "nmcli")
                with open(stub, "w", encoding="utf-8") as handle:
                    handle.write(f"#!/bin/sh\nprintf '{nmcli_output}'\n")
                os.chmod(stub, 0o755)
                result = subprocess.run(
                    ["bash", "-c", f"set -euo pipefail\n{line}\n{default}\nprintf '%s' \"$wifi_connected\""],
                    env={**os.environ, "PATH": f"{tmp}:{os.environ['PATH']}"},
                    capture_output=True, text=True, check=False,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, expected)

    def test_gaming_hint_lives_where_an_unprivileged_game_can_write(self) -> None:
        """/run/kyth is kyth-privileged's root:wheel 0750 RuntimeDirectory, so the
        hint a game launch writes there always failed silently and Wi-Fi
        power-save / NVMe read-ahead never switched to gaming mode."""
        wifi = (ROOT / "build_files/scripts/sysconfig/network/16-wifi-disable-power-management.sh").read_text(encoding="utf-8")
        tmpfiles = (ROOT / "build_files/scripts/branding/27-performance-daemons.sh").read_text(encoding="utf-8")
        launcher = (ROOT / "src/kyth-shared-rs/src/game_launch_bin.rs").read_text(encoding="utf-8")
        self.assertIn("/run/kyth-gaming/hint-*", wifi)
        self.assertNotIn("/run/kyth/gaming-hint", wifi)
        self.assertIn("d /run/kyth-gaming 1777 root root -", tmpfiles)
        self.assertIn("d /run/kyth-state 0755 root root -", tmpfiles)
        shipped = launcher.split("#[cfg(test)]")[0]
        self.assertNotIn("/run/kyth/gaming-hint", shipped)
        self.assertIn("GAMING_HINT_DIR", shipped)

    def test_default_flatpaks_do_not_fail_when_flathub_is_absent(self) -> None:
        body = (ROOT / "build_files/kyth-default-flatpaks.service").read_text(
            encoding="utf-8"
        )
        self.assertIn("Wants=network-online.target kyth-flathub-setup.service", body)
        self.assertNotIn("Requires=network-online.target", body)
        self.assertIn("ExecCondition=", body)
        self.assertIn("kyth-runtime flathub-setup", body)
        self.assertIn("will retry next boot", body)
        self.assertNotIn("ExecStartPost=/bin/touch", body)

    def test_qemu_guest_agent_is_vm_only(self) -> None:
        body = (
            ROOT / "build_files/scripts/packages/13-gpu-amd-and-qemu-guest.sh"
        ).read_text(encoding="utf-8")
        self.assertIn("qemu-guest-agent.service.d", body)
        self.assertIn("ConditionVirtualization=vm", body)

    def test_boot_rw_uses_prepare_boot_and_cannot_fail_sysinit(self) -> None:
        body = (
            ROOT / "build_files/scripts/sysconfig/systemd/kyth-boot-rw.service"
        ).read_text(encoding="utf-8")
        self.assertIn("ExecStart=-/usr/libexec/kyth-finalize-staged prepare-boot", body)
        self.assertNotIn("mount -o remount,bind,rw /boot", body)
        finalize = (ROOT / "build_files/scripts/sysconfig/kyth-finalize-staged").read_text(
            encoding="utf-8"
        )
        self.assertIn('echo "kyth-finalize-staged: could not bind /boot to /sysroot/boot"', finalize)
        self.assertNotIn("mount --bind /boot /sysroot/boot 2>/dev/null || true", finalize)

    def test_restart_queues_reboot_without_repeating_finalize_in_the_hub(self) -> None:
        helper = (
            ROOT / "src/kyth-shared-rs/src/system/boot_finalize.rs"
        ).read_text(encoding="utf-8")
        reboot_path = helper.split("pub fn finalize_staged", 1)[1].split("#[cfg(test)]", 1)[0]
        reboot_branch = reboot_path.split("if reboot", 1)[1].split("}", 1)[0]
        self.assertIn("request_reboot()", reboot_branch)
        self.assertIn('["--no-block", "reboot"]', helper)
        script = (ROOT / "build_files/scripts/sysconfig/kyth-finalize-staged").read_text(
            encoding="utf-8"
        )
        self.assertIn('if [[ "${mode}" == "reboot" ]]', script)
        self.assertIn("exec /usr/bin/systemctl --no-block reboot", script)

    def test_splash_and_branding_wait_for_writable_boot(self) -> None:
        body = BOOT_SPLASH.read_text(encoding="utf-8")
        self.assertGreaterEqual(body.count("After=local-fs.target kyth-boot-rw.service"), 2)
        # Splash kargs converge via bootc kargs.d (durable across
        # deployments), never via grubby edits to live BLS entries — and the
        # migration must never strip user kargs (GPU flags included).
        self.assertIn("/etc/bootc/kargs.d/99-kyth-splash.toml", body)
        self.assertIn("boot-splash-kargs-v4", body)
        self.assertNotIn("grubby --", body)
        self.assertNotIn("command -v grubby", body)
        self.assertNotIn("--remove-args", body)
        self.assertNotIn("kyth-firstboot-notice.service", body)
        self.assertNotIn("first-boot-done", body)

    def test_first_boot_plymouth_message_stamps_before_plymouth(self) -> None:
        body = (
            ROOT / "build_files/scripts/sysconfig/systemd/33-first-boot-plymouth-message.sh"
        ).read_text(encoding="utf-8")
        unit = body.split("FIRSTBOOTEOF", 1)[1].split("FIRSTBOOTEOF", 1)[0]
        self.assertIn("touch /var/lib/kyth/.first-boot-complete", unit)
        self.assertIn("ExecStart=-/usr/bin/plymouth", unit)
        self.assertNotIn("ExecCondition=/usr/bin/plymouth --ping", unit)
        self.assertIn("open Kyth Hub", unit)
        self.assertLess(
            unit.find("touch /var/lib/kyth/.first-boot-complete"),
            unit.find("plymouth message"),
        )

    def test_wait_online_offline_exit_is_success(self) -> None:
        body = (ROOT / "build_files/scripts/branding/31-ujust-recipes.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn("systemctl disable NetworkManager-wait-online.service", body)
        self.assertNotIn("systemctl enable NetworkManager-wait-online.service", body)

    def test_storage_maint_is_timer_only(self) -> None:
        body = (ROOT / "build_files/kyth-storage-maint.service").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("[Install]", body)
        self.assertNotRegex(body, r"^WantedBy=", re.M)

    def test_boot_timing_and_batteryd_avoid_multiuser_cycle(self) -> None:
        timing = (ROOT / "build_files/scripts/branding/51-zram.sh").read_text(
            encoding="utf-8"
        )
        battery = (ROOT / "build_files/kyth-batteryd.service").read_text(encoding="utf-8")
        power = (ROOT / "build_files/kyth-power-arbiter.service").read_text(
            encoding="utf-8"
        )
        self.assertIn("After=local-fs.target", timing)
        self.assertNotRegex(timing, r"^After=multi-user\.target$", re.M)
        self.assertIn("After=local-fs.target", battery)
        self.assertNotIn("After=multi-user.target", battery)
        self.assertIn("After=local-fs.target", power)
        self.assertNotIn("After=multi-user.target", power)

    def test_branding_guard_prefers_bind_rw(self) -> None:
        guard = (ROOT / "build_files/kyth-boot-branding-guard").read_text(encoding="utf-8")
        ply = (ROOT / "src/kyth_shared/kyth_shared/plymouth.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("remount,bind,rw /boot", guard)
        self.assertIn('["mount", "-o", "remount,bind,rw", "/boot"]', ply)
        repair = (
            ROOT / "build_files/scripts/repair-current-plymouth-initramfs.sh"
        ).read_text(encoding="utf-8")
        self.assertIn("remount,bind,rw /boot", repair)

    def test_greenboot_waits_for_selinux_relabel_and_stays_active(self) -> None:
        from kyth_shared.system.boot_runtime import DEFAULT_DEADLINE

        body = (
            ROOT / "build_files/scripts/branding/35-diagnostic-script-installs.sh"
        ).read_text(encoding="utf-8")
        self.assertIn("After=kyth-selinux-relabel-home.service", body)
        self.assertIn("TimeoutStartSec=600", body)
        self.assertIn("RemainAfterExit=yes", body)
        self.assertGreaterEqual(DEFAULT_DEADLINE, 300.0)

        # StartLimitIntervalSec/StartLimitBurst are only recognized in
        # [Unit] — stranded in [Service] they are silently dropped and the
        # unit runs under systemd's compiled-in 10s/5 default instead.
        drop_in = body.split("40-kyth-timeout.conf", 1)[1].split(
            "<<'EOF'", 1
        )[1].split("\nEOF", 1)[0]
        unit_sec, service_sec = drop_in.split("\n[Service]\n", 1)
        self.assertIn("StartLimitIntervalSec=0", unit_sec)
        self.assertNotIn("StartLimit", service_sec)

    def test_greenboot_rollback_trigger_drop_in_disables_start_limit(self) -> None:
        body = (
            ROOT / "build_files/scripts/packages/22-greenboot.sh"
        ).read_text(encoding="utf-8")
        drop_in = body.split("10-kyth.conf", 1)[1].split(
            "<<'GBROLLBACK'", 1
        )[1].split("\nGBROLLBACK", 1)[0]
        # The drop-in originally had no [Unit] header at all, so its
        # StartLimitIntervalSec/StartLimitBurst keys (only recognized in
        # [Unit]) were silently dropped and the unit ran under systemd's
        # compiled-in 10s/5 default instead of the intended relief.
        unit_sec, service_sec = drop_in.split("\n[Service]\n", 1)
        self.assertIn("[Unit]", unit_sec)
        self.assertIn("StartLimitIntervalSec=0", unit_sec)
        self.assertNotIn("StartLimit", service_sec)
        self.assertIn("RemainAfterExit=yes", service_sec)
        self.assertIn("kyth-finalize-staged prepare-boot", service_sec)

    def test_probe_oneshot_stays_active_for_timer(self) -> None:
        body = (ROOT / "build_files/kyth-probe.service").read_text(encoding="utf-8")
        unit = body.split("[Service]", 1)[0]
        self.assertIn("RemainAfterExit=yes", body)
        self.assertIn("StartLimitIntervalSec=120", unit)
        self.assertIn("StartLimitBurst=5", unit)

    def test_power_arbiter_can_retrigger_without_start_limit(self) -> None:
        body = (ROOT / "build_files/kyth-power-arbiter.service").read_text(
            encoding="utf-8"
        )
        self.assertIn("RemainAfterExit=no", body)
        self.assertIn("StartLimitBurst=20", body)
        self.assertNotIn("PrivateUsers=yes", body)

    def test_scx_loader_skips_when_unconfigured(self) -> None:
        unit = (ROOT / "build_files/kyth-scx-loader.service").read_text(encoding="utf-8")
        script = (ROOT / "build_files/kyth-scx-loader").read_text(encoding="utf-8")
        self.assertIn("ConditionPathExists=/etc/scx/scx_loader.conf", unit)
        self.assertIn("leaving sched_ext unset", script)
        self.assertNotIn("exit 1", script.split("missing", 1)[1].split("scheduler", 1)[0])

    def test_splash_initramfs_cannot_fail_the_boot_unit_list(self) -> None:
        body = BOOT_SPLASH.read_text(encoding="utf-8")
        self.assertIn("ExecStart=-/usr/libexec/kyth-refresh-boot-splash-initramfs", body)


class InstallerMokFailClosedTests(unittest.TestCase):
    def test_failed_mok_staging_blocks_install_success(self) -> None:
        from kyth_installer.phases.run import _require_secure_boot_ready

        with self.assertRaisesRegex(RuntimeError, "could not stage MOK"):
            _require_secure_boot_ready("failed")

    def test_successful_mok_states_do_not_block_install(self) -> None:
        from kyth_installer.phases.run import _require_secure_boot_ready

        for state in ("skipped", "enrolled", "pending", "staged", {}):
            with self.subTest(state=state):
                _require_secure_boot_ready(state)


if __name__ == "__main__":
    unittest.main()
