# Kyth Hub Rust rollback runbook

Use this runbook when a Tauri-only System Hub release has a startup, routing,
action, secret-handling, or update-lifecycle regression. It is written for the
testing/stable image promotion path and assumes that the previous bootc
deployment is still available.

## Release-blocking signals

Stop promotion and keep the previous image available if any of these are
observed:

- `/usr/bin/kyth-hub-shell` does not start, has a blank/failed embedded
  frontend, or cannot open the requested `--page` route.
- A second launch creates another Hub window instead of focusing the existing
  one and forwarding the requested page.
- A privileged action bypasses confirmation, runs an operation outside the
  fixed allowlist, exposes a BitLocker key/share password, or reports a secret
  in UI status, logs, audit detail, or process arguments.
- A Guardian, hardware, application, gaming, VPN, or update action reports
  success before the underlying operation has completed.
- Update health records a failed boot or quarantines the new image digest.

## Prerequisites

- Administrator access to the affected KythOS machine or disposable VM.
- The image digest/tag that was booted and the previous bootc deployment.
- Access to the release validation run and its build artifact.

Do not clear a quarantine or delete the previous deployment while diagnosing
the incident.

## Telemetry-free first response

These checks use local state and do not upload telemetry:

```bash
ujust status
ujust update-health
kyth-boot-health status --json
systemctl --failed
journalctl -b 0 -u kyth-hub-shell.service --no-pager
```

For a launch or deep-link failure, run the launcher directly and capture only
the non-secret exit/status output:

```bash
/usr/bin/kyth-welcome-launch --page updates
/usr/bin/kyth-welcome-launch --page diagnostics
```

The native Hub surfaces the same local signals through the `probe_backend`,
`boot_runtime_checks`, `recovery_status`, `update_status`, and `update_health`
Tauri commands. Helper output is bounded and passed through the shared
sensitive-text redactor before it becomes a job status or diagnostic detail.

## Roll back the affected deployment

1. Record the current booted digest and health state:

   ```bash
   sudo bootc status --json
   sudo kyth-boot-health status --json
   ```

2. If the system still has a usable shell, use the Updates page's Rollback
   action. If the shell is unavailable, use the administrator fallback:

   ```bash
   sudo bootc rollback
   sudo kyth-finalize-staged reboot
   ```

   If the finalizer is unavailable, prepare the staged boot entry and reboot
   using the image's documented fallback:

   ```bash
   sudo mount -o remount,bind,rw /boot
   sudo ostree admin finalize-staged
   sudo systemctl reboot
   ```

3. After reboot, verify that the previous digest is booted and that the Hub
   starts through `/usr/bin/kyth-hub-shell`. Check one read-only route and one
   harmless status command before considering the rollback successful.

4. Keep the failed digest quarantined. Do not clear it until the release owner
   has identified the cause and a corrected image has passed the release gates.

If the automatic health hook has already attempted rollback, inspect
`rollback_attempted_for`, `last_rollback_error`, and `last_rollback_at` in
`/var/lib/kyth/boot-health.json` before retrying. A failed rollback can be
retried after the underlying condition is fixed:

```bash
sudo kyth-boot-health retry-rollback --digest sha256:FAILED_DIGEST
```

## Revert or remove the failed release

- Mark the image digest failed in the release record and stop testing/stable
  promotion.
- Revert the Rust/Tauri default or packaging change on the publishing branch,
  then rebuild from the last known-good commit. Kyth publishes from `testing`
  and promotes to `main` only as a human step.
- Keep the failed image and validation logs for diagnosis; do not overwrite
  the immutable artifact.
- If the failure is a secret leak or authorization bypass, treat it as a
  security incident, revoke any exposed credential, and preserve the local
  audit/journal evidence before cleanup.

## Closure criteria

Close the incident only after the corrected image has:

- passed the Hub build, contract, Rust unit, and redaction tests;
- passed the launcher/deep-link, single-instance, representative-action, and
  rollback checks on the exact installed image; and
- updated the migration plan and release checklist with the digest, run IDs,
  result, and any remaining operational risk.

The current YOLO migration intentionally waives installed-image/user
acceptance. That waiver does not turn a runtime check into a pass; it remains
an explicit release risk until a later qualification run is completed.
