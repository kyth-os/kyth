# KythOS Daily-Driver Validation

This checklist is the "make it feel inevitable" gate. A release should not feel
ready just because it boots once. It should survive the normal, boring things a
Windows gamer expects from a daily machine: updates, sleep, Bluetooth, Wi-Fi,
launchers, files, displays, audio, and rollback.

## Smoke Check

Run this after install, after an OS update, and before publishing a release:

```bash
ujust smoke-check
```

For release gating, use strict mode so warnings count:

```bash
ujust smoke-check --strict --verbose
```

Store notable output in the release notes or the matching hardware result. The
check is read-only: it does not install apps, change drivers, run updates, or
mount Windows drives.

For a versioned, machine-readable qualification artifact, run:

```bash
kyth-qualify collect \
  --output qualification.json \
  --markdown qualification.md
```

Gaming telemetry stays local and is excluded by default. Testers may explicitly
include game names and aggregate MangoHud metrics with `--include-gaming`.

KythOS also ships smaller targeted checks:

```bash
ujust post-update-check
ujust nvidia-status
ujust controller-check
ujust resume-check
```

`post-update-check` is also launched silently once per deployment after login.
It confirms the current boot still has rollback visibility, graphics, Vulkan,
Flatpaks, and desktop audio without raising a popup for optional software.
`nvidia-status`, `controller-check`, and `resume-check` are manual validation
helpers for hardware-specific testing.

## Manual VM Acceptance

The live-ISO CI workflow does *not* gate publication on this anymore — an
unattended QEMU lifecycle gate was added and then reverted because it added
too much CI time for the value it provided. The guest service, host driver,
and systemd unit are still shipped and tested as an opt-in local tool:

1. Boot the live ISO and wait for Plasma.
2. Run the smoke check, install the OCI image bundled in that ISO to a dedicated
   virtual disk, and reboot from it.
3. Wait for the installed display manager and run the smoke check again.
4. When `--update-ref` is supplied, switch to that image, verify the new
   deployment and rollback slot, reboot, roll back, and verify the original
   image digest is active again.

The guest service is inert on normal hardware and ordinary virtual machines. It
only runs when the host supplies the private QEMU firmware flag used by the
acceptance driver.

Run the install-only gate locally after building an ISO:

```bash
just accept-live-iso output/live-iso/kyth-live-testing.iso
```

To exercise update and rollback directly, invoke
`build_files/scripts/vm-acceptance.sh` with `--update-ref` pointing at a second,
different KythOS image.

Every successful VM run writes `qualification.json` and `qualification.md` in
the artifact directory alongside the serial log and screenshots. The JSON uses
the same schema as physical-hardware reports, so automation can gate a release
without scraping human-oriented logs.

## Regression Gate

Compare a candidate report with the last qualified report from the same
hardware and workload:

```bash
kyth-qualify gate \
  --candidate candidate.json \
  --baseline baseline.json \
  --budgets /usr/share/kyth/qualification-budgets.json \
  --output gated.json \
  --markdown gated.md
```

The command exits non-zero when a required check fails or a comparable metric
exceeds its regression budget. Metrics only compare when name, workload, and
unit all match; results from different games or hardware should never be mixed.
The default budgets cap average-FPS regression at 5%, 1%-low regression at 8%,
and stutter-rate regression at 10%. A release owner can tighten these values as
the hardware lab accumulates stable baselines.

## Release Gates

A release candidate should pass these before being called daily-driver ready:

- Live ISO reaches the desktop automatically, does not open System Hub, clearly
  prompts for network setup, and exposes only trusted **Install KythOS** and
  **System Hub** desktop shortcuts.
- Live ISO mirrors installed-user comfort polish: KythOS wallpaper, dark theme,
  double-click file behavior, familiar user folders, document templates, app
  defaults, System Hub favorites, and Windows `.exe` / `.msi` helper handling.
- Fresh install reaches the desktop without manual terminal work.
- The installed app launcher keeps expert-only helpers quiet: no live installer,
  terminal-only monitors, mpv backend entry, or guided hardware diagnostics.
- The Games launcher category keeps playable titles at its root and places
  storefronts, launcher managers, compatibility helpers, and save tools under
  Games > Tools.
- LibreOffice launchers appear under Office only; Draw is not duplicated under
  Graphics and Math is not duplicated under Education or Science.
- Dolphin does not expose KDE's broken Google Drive KIO worker; Google Drive
  setup uses the System Hub Cloud Storage `rclone` wizard.
- `ujust smoke-check --strict` has no failures on at least one AMD or Intel
  system.
- NVIDIA hardware either loads the proprietary module or gives a clear
  reboot/build path.
- `ujust kyth-upgrade` stages an update and rebooting activates it.
- The previous deployment remains visible from the boot menu after update.
- Steam installs or launches, Proton runners are available, and one known-good
  game reaches gameplay.
- Bluetooth pairs a controller or headset, then survives logout/login.
- Wi-Fi reconnects after suspend/resume.
- Audio output and microphone are selectable in KDE settings and work in
  Discord or OBS.
- Dolphin shows expected user folders and removable or mounted drives.
- A dirty or hibernated NTFS drive is detected and treated as a migration
  warning, not a normal writable game library.
- Discover manages Flatpaks without presenting phantom RPM system updates.
- Repair and support paths are visible: System Hub Repair opens, and
  `ujust device-info` produces a paste-friendly report.
- The Repair page explains why `/usr` is read-only and points users toward
  Flatpak, Distrobox, `/home`, System Hub, and image updates instead of manual
  system-file edits.
- The default game app setup notifier either confirms Steam/launchers/save tools
  are installed or tells the user how to retry the setup service.

## Hardware Coverage

Record at least one pass or known issue for each class:

| Class | What To Prove |
| --- | --- |
| AMD desktop GPU | Vulkan, VRR/high refresh, sleep/wake, MangoHud |
| NVIDIA desktop GPU | akmod build, reboot activation, Vulkan, sleep/wake |
| Intel laptop/iGPU | Wi-Fi, Bluetooth, suspend, fractional scaling if needed |
| Hybrid laptop | iGPU desktop, dGPU game path, external display behavior |
| Xbox controller | USB and Bluetooth or wireless adapter path |
| DualSense | USB, Bluetooth pairing, Steam Input |
| NTFS Windows drive | clean drive migration and dirty-drive warning |
| Printer or scanner | LAN discovery through KDE/CUPS where available |

## Rough-Edge Drills

Do these intentionally. Evangelists are made when recovery works.

1. Stage an update, reboot, confirm the new deployment is active, then boot the
   previous deployment from the boot menu.
2. Disable networking before first login and confirm first-boot services fail
   softly instead of blocking the desktop.
3. Interrupt or fail a Flatpak metadata refresh, then confirm System Hub and
   `ujust smoke-check` explain the missing app state.
4. On NVIDIA hardware, run `sudo kyth-hardware-policy apply --force`, reboot, and confirm
   the setup path retries instead of silently giving up.
5. Connect a hibernated Windows volume and confirm migration tools warn the user
   to fully shut down Windows.
6. Fill memory pressure with a browser plus a game load screen and confirm the
   desktop survives without killing session-critical services.
7. Suspend and resume with Bluetooth audio or controller connected, then launch
   a game.
8. Try to copy a helper into `/usr/bin` on an installed system and confirm the
   project docs/System Hub messaging explain that the OS image is immutable.
9. On an NVMe system, benchmark a game while downloading or unpacking a large
   file. Record `ujust nvme-tuning status`, then compare the kernel-default
   profile against `ujust nvme-tuning kyth`. Return to defaults with
   `ujust nvme-tuning default` and reboot before the baseline run.

## Result Template

```text
Image tag:
Kernel:
Session:
Hardware:
GPU driver/Mesa:
Fresh install or update:
Smoke check:
Steam/game result:
Bluetooth:
Wi-Fi/suspend:
Audio/mic:
Migration path:
Rollback tested:
Rough edges:
Verdict:
```

Use this alongside the gaming matrix. The gaming matrix proves games work; this
document proves the computer around the games is calm enough to live in.

For new results, attach the generated qualification JSON instead of copying this
template by hand. It intentionally records CPU model, architecture, and kernel,
but no hostname, account name, network address, device serial, or other stable
machine identifier.
