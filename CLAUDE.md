# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# kyth

Custom atomic gaming and development desktop OS built on Fedora Kinoite (KDE Plasma) + CachyOS kernel. Uses [bootc](https://containers.github.io/bootc/) to ship the entire OS as a container image — immutable, atomic updates, one-command rollback.

## Build & Test Commands

```bash
just build                        # Build base image + full OS image (requires Docker)
just check-dockerfile              # Docker buildx --check without building the full image (fast sanity check)
just build-live-iso                # Live ISO from the stable channel image
just build-live-iso testing        # Live ISO from the testing channel image
just rebuild-live-iso-local        # Live ISO embedding the local image
just run-live-iso-native-local     # Native QEMU/SPICE boot of the local ISO
just preview-installer              # Browser preview of the installer; touches no disks
just build-qcow2                  # Build QCOW2 VM image
just clean / just clean-all / just purge  # Reclaim build/disk space (increasing scope)
just lint && just format          # Shellcheck + shfmt on all *.sh
```

Quality gates — run these before pushing, or when validating a change:

```bash
just test                          # Python unit tests (tests/) via unittest discover
just test-coverage                 # Same, with statement coverage report -> coverage-html/index.html
just check-optimization            # Enforce maintainability/size budgets in build_files/config/optimization-budgets.json
just validate                      # Full validation suite (same as CI + pre-push)
just ci-preflight                  # validate + changed-file Codacy + pinned CodeQL
just install-git-hooks             # One-time: wires .githooks/ (pre-commit, pre-push, prepare-commit-msg)
```

Run a single test file or case directly (mirrors what `just test` does):

```bash
PYTHONPATH=build_files/kyth_shared:build_files/kyth-welcome:build_files/kyth-installer \
  python3 -m unittest tests.test_kyth_probe_cache -v

PYTHONPATH=build_files/kyth_shared:build_files/kyth-welcome:build_files/kyth-installer \
  python3 -m unittest tests.test_kyth_probe_cache.SomeTestCase.test_thing -v
```

`.githooks/pre-push` also runs a headless PySide6 smoke test that instantiates every System Hub page (`kyth_welcome.windows.MainWindow`, `QT_QPA_PLATFORM=offscreen`) — a common source of pre-push failures when a page module has an import-time or construction-time bug. Reproduce it directly if `just validate` passes but pre-push still fails.

Feature flags (image build):
```bash
ENABLE_SCX=0 sudo just build                     # sched-ext is on by default; disable with 0
ENABLE_GAMING_PERIPHERALS=1 sudo just build
ENABLE_VIRTUALIZATION_HOST=1 sudo just build
ENABLE_KSM=1 sudo just build
```

## Common Issues

**Docker permission denied on socket:**

`just build-base` now handles this automatically — if you're not in the `docker` group it adds you and re-execs under `sg docker` without requiring a logout. If you hit the error outside of a just recipe, run `newgrp docker` to activate the group in the current shell.

## Architecture

The image is built in ordered layers rather than one monolithic Dockerfile, so packages, config, branding, and helpers stay independently reviewable:

```
Fedora Kinoite / Universal Blue base
        │
  KythOS base layer        (build_base/ — kernel flavor, plymouth, dracut, display-manager defaults)
        │
  final OCI desktop image  (Dockerfile — packages, build_files/scripts/* fragments, branding, units)
        │
   live ISO installer      (installer/ + build_files/kyth-installer — graphical bootc-based installer)
        │
  bootc deployment on disk
        │
 atomic updates + rollback deployments
```

- **`Dockerfile`** assembles the final image via a sequence of `RUN --mount=type=bind` steps, each pulling in one `build_files/scripts/*.sh` fragment (packages, thirdparty repos, sysconfig, mesa-git, secureboot, branding, plymouth). Adding a new build-time concern usually means adding a new ordered fragment here rather than editing existing ones.
- **`build_files/kyth_shared/kyth_shared/`** is a large library of small, single-purpose Python modules — one file per tunable, preset, or feature (e.g. `swappiness.py`, `zram.py`, `vrr.py`, `gaming_scan_atomic.py`, `cloud_idempotent.py`). Runtime helpers, `ujust` recipes, and System Hub services all import from here. Follow this convention for new host-tuning logic: a small, independently testable module rather than growing an existing one. Several are explicitly idempotent/transactional (see recent commit history: `PST/fonts idempotent`, `rclone idempotent`, `transactional profile switch`) — new state-mutating modules should follow that pattern (safe to re-run, and either fully applies or fully rolls back).
- **`build_files/kyth-welcome/`** is the System Hub — a PySide6 desktop app plus a standalone VPN app sharing the same services. Pages are lazily composed: a page module defines a thin `Page` subclass, and `lazy_page.compose_on_first_init` mixes in the real tab implementation only when the user first navigates there (see `page_registry.py`, `lazy_page.py`). This keeps Hub startup cheap even though there are dozens of pages. Cross-page state (probe results, update status) goes through shared caches in `services/probe.py` / `services/hub_state.py` so multiple pages/notifications don't repeat expensive system probes.
- **`build_files/kyth-installer/`** is the local-only installer service (Python backend in `kyth_installer/`, JS/HTML frontend in `kyth_installer/webui/`) that drives `bootc install to-disk`. Disk-affecting logic is split across `plan_*.py` (compute a plan), `partition_ops*.py` / `disk/` (execute it), and `recovery.py`/`assurance.py` (verify + durable transaction logging). Treat anything touching these as high-risk: prefer adding tests in `tests/test_kyth_installer_*` alongside changes.
- **`build_files/just/kyth.just`** imports domain-specific `*.just` files (gaming, performance, network, diagnostics, dualboot, secureboot, containers, ...) — these become the `ujust` recipes shipped inside the built OS, distinct from the repo-root `Justfile` used for building the OS itself.
- **`tests/`** is flat (no subpackages) with ~100+ files named after the module/feature under test; `PYTHONPATH` must include `kyth_shared`, `kyth-welcome`, and `kyth-installer` for imports to resolve (see commands above).

## Branches & Workflow

- `main` → `:latest` tag (stable). `testing` → `:testing` tag (active dev, may be unstable).
- This repository does not use a PR workflow for routine maintainer work: changes are committed and pushed **directly to `testing`** (per `AGENTS.md`). Promotion to stable (`main`) happens only after CI validation and, for boot/login/networking/audio/GPU/installer/privileged-helper changes, live-ISO or real-hardware checks.
- Changes affecting boot, login, networking, audio, GPU setup, updates, the installer, or privileged helpers should include an automated regression test where practical, and a documented manual recovery path where hardware behavior can't be automated.

Switch channel on a running system:
```bash
sudo bootc switch ghcr.io/mrtrick37/kyth:testing
sudo bootc upgrade
```

## Project Layout

```text
Dockerfile              # Main OS image (layers 2+3)
Justfile                # Build orchestration (imports build_files/just/*.just for dev commands)
build_base/             # Layer 1: CachyOS kernel + base Fedora Kinoite 44
  Dockerfile
  build.sh
build_files/             # Layer 2+: packages, gaming tweaks, branding, and installed runtime code
  build-live-iso.sh     # Local Titanoboa live ISO wrapper
  kyth-installer/        # Graphical installer (Python backend + web UI, packaged into the live ISO)
  kyth-welcome/          # System Hub app (kyth_welcome/), VPN app, first-run wizard
  kyth_shared/           # Shared library: one small module per host tunable/feature/preset
  branding/              # KythOS logos and branding CSS
  scripts/               # Build-layer fragments: packages, thirdparty, sysconfig, branding, proton-cachyos, mesa-git
  just/kyth.just         # ujust recipes shipped in the OS (imports kyth/*.just by domain)
  config/                # Tracked budgets/config consumed by scripts (e.g. optimization-budgets.json)
installer/               # Bazzite-style live payload customization
tests/                    # Flat unittest suite (~100+ files) for installer, Hub, and shared helpers
docs/                     # Architecture, security model, hardware policy, validation/support docs
.githooks/                # pre-commit / pre-push / prepare-commit-msg (installed via `just install-git-hooks`)
.github/workflows/        # CI: daily rebuilds at 10:05 UTC, validation, signing, provenance, CVE scans
```

## Key Details

- Base: `ghcr.io/ublue-os/kinoite-main:44` (Fedora 44 KDE)
- Kernel: CachyOS with BORE scheduler, sched-ext, BBRv3, NTSYNC
- GPU: Mesa-git from xxmitsu/mesa-git COPR (bleeding-edge RADV/RADEONSI)
- SELinux: enforcing (bootc/ostree relabels the deployed tree on every deployment using the bundled policy)
- Live ISOs published to Cloudflare R2: `kyth-live-latest.iso` / `kyth-live-testing.iso`
- GitHub: https://github.com/mrtrick37/kyth
