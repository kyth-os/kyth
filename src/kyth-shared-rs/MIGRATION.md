# Migrating kyth_shared to Rust

`src/kyth_shared` (Python) is ~200 modules covering everything from GPU
switching and VPN connection management to installer disk partitioning,
SELinux policy, and systemd unit management. Porting all of it in one pass
isn't realistic, and doing it carelessly is actively dangerous — a lot of
it is exactly what CLAUDE.md already calls out as high-risk (installer,
GPU setup, anything privileged). This crate is not that port. It's the
starting point for one, done incrementally, module by module. Most probes
remain read-only; explicit user-requested Hub actions are added only where
their command policy and bounded execution are already covered.

## What's ported so far

The read-only bridges and pure helpers the Kyth Hub's Tauri shell
(`src/kyth-hub-web/src-tauri`) used to shell out to Python subprocesses
for — see `src/kyth-hub-web/src-tauri/src/main.rs`'s `probe_backend`,
`guardian_snapshot`, `hardware_snapshot`, `storage_snapshot` commands:

| This crate | Ports the read path of | Behavior deliberately NOT ported |
|---|---|---|
| `system::probe` | `kyth_shared.system.probe` | The collector/write side (`collect_snapshot`, `write_cache_file`) — `kyth-probe.service` stays Python and keeps writing the cache this reads. |
| `guardian` | `kyth_shared.guardian` read state, recipe policy, and the explicit Hub repair path | `collect_symptoms()`/`inspect()` — the live probe sweep (a dozen-plus subprocess calls across audio/network/bluetooth/portal/...). The Rust repair path is limited to the user-requested, policy-gated recipes wired in `guardian_actions.py`; Python remains authoritative for the service sweep and state writer. |
| `system::runtime_output` | Pure parsers from `kyth_shared.system.runtime_output` | The commands that collect the raw output remain in their owning probes; this module only parses bounded output. |
| `system::bootc_query`, `system::registry`, `system::update_*` | Hub-facing bootc status, registry manifest, update summaries, and the watcher status read | Image mutation, downloads, watcher writes, and updater installation remain outside this crate. |
| `system::snapshot` | Read-only Snapper/Btrfs snapshot and bootc deployment timeline | Snapshot creation, deletion, rollback, and cache/state writes remain outside this crate. |
| `system::snapshot_autoclean` | Bounded Btrfs quota/Snapper timeline cleanup command planning and filesystem-status normalization | Quota mutation, Snapper cleanup, and deletion remain caller-owned. |
| `system::telemetry_ingest` | Pure MangoHud CSV parsing, game-name derivation, launcher detection, and numeric normalization for `kyth-telem` | MangoHud configuration, SQLite writes, `/proc` inspection, and the active daemon remain Python-owned pending service-level parity tests. |
| `system::telemetry_writer` (`telemetry-writer` feature) | Opt-in SQLite schema creation and CSV session/frame ingestion | Not enabled in Hub or image builds; the Python daemon remains the active writer until real-output and migration tests pass. |
| `system::gpu` | `kyth_shared.system.gpu` | `loaded_kernel_modules`, `rpm_package_installed`, `query_nvidia_smi` — only `lspci_gpu_lines` had a caller. |
| `system::hardware_policy` | Read-only `hardware_policy` inventory, TOML parsing, selector matching, and evaluation | Policy application, modprobe/scheduler writes, and persisted state/report writes remain Python-owned. |
| `system::storage` | (new — was inline Python in the retired `storage_bridge.py`, not really "kyth_shared") | — |
| `system::boot_health` | read/policy surface of `kyth_shared.boot_health` | State transitions, atomic persistence, boot verification, and rollback remain Python-owned. |
| `diagnostics_scrub` | `kyth_shared.diagnostics_scrub.scrub_logs` | Collection, upload, and report composition remain outside the crate. |
| `atomic_io` | `kyth_shared.atomic_io` crash-safe text/bytes/JSON replacement | Callers still decide which state is safe to persist. |
| `config_loader` | Shared TOML defaults/section/candidate loading behavior from `kyth_shared.config` | Type-specific validation and writes remain owned by each setting module. |
| `health` | `kyth_shared.health` typed reports, severity aggregation, remediation text, JSON/text output | Smoke-check collection remains owned by the caller. |
| `system::battery` | `kyth_shared.battery` config defaults/clamping and sysfs health reads | Hardware charge-limit application remains outside this crate. |
| `system::boot_loader` | `kyth_shared.boot_loader` config/status reads | `/boot` loader mutation remains privileged and Python-owned. |
| `system::runtime_diagnostics` | Pure deployment, GPU-driver, GPU/Vulkan/session/rollback status, service-state, and live-image interpretation | Raw command collection remains with existing probes. |
| `system::controllers` | Controller USB/module/input inventory, variant classification, and bounded optional DualSense probe | Hardware command collection and device mutation remain caller-owned. |
| `system::disk_utils` | Safe integer and device-path normalization | Partition discovery and mutation remain installer-owned. |
| `system::sbom` | Offline SBOM diff and CVE severity summaries | No network fetch or vulnerability database update. |
| `system::exe_compat` | Bounded EXE hashing, offline compatibility lookup, filename normalization, and Steam launcher rewriting | No execution of the target file, installer workflow, or runner installation. |
| `system::rollback_state` | `kyth_shared.rollback_single_source` staged/rollback state read | Update coordinator writes remain outside this crate. |
| `system::appstore_cache` | Offline AppStream cache status | Catalog refresh remains probe/service-owned. |
| `system::tuning_profile` | Common TOML profile normalization for small tuning modules | Privileged sysctl/cgroup application is not included. |
| `system::app_presets`, `backup_config`, `print_config` | Offline TOML config models and safe persistence | Service activation, backup execution, and printer setup remain external. |
| `system::windows_verify`, `attest`, `thirdparty` | Read-only migration parity, cached attestation metadata, and downloaded-asset discovery | No installer execution or online signature verification. |
| `system::windows_installer` | PE/MSI header inspection, immutable file identity/hash, compatibility assessment, bottle naming, and Bottles JSON parsing | Installer staging, Flatpak installation, and Windows process launching remain explicit caller-owned actions. |
| `system::firstboot`, `devcontainers`, `search_config`, `session_config` | First-run markers, Distrobox/search config, and browser credential-store transforms | Desktop service application remains outside the shared crate. |
| `system::process` | Session helpers, ANSI/progress formatting, and bounded argv execution | Caller still owns command allowlists and operation-specific timeout policy. |
| `system::display`, `hdr` | KScreen output parsing, EDID HDR hints, and per-display HDR config | KScreen/KWin mutation remains guarded by existing action paths. |
| `system::gaming_master` | Gaming profile normalization plus thermal/battery safety evaluation | Composed tuning application and snapshot/rollback remain outside Rust. |
| `system::gaming_snapshot` | Pre-gaming Snapper/Btrfs fallback command planning and result evaluation | Snapshot creation and filesystem mutation remain caller-owned. |
| `system::sysctl_profiles` | Shared profile/config/drop-in behavior for 44 small sysctl tuning modules | Applying sysctl values and privileged drop-in ownership remain outside this crate. |
| `system::hdr_store`, `hdr_per_game` | HDR preserve preference and per-game peak/ITM config models | KWin/display mutation and driver probing remain outside the shared crate. |
| `system::work_cache` | Work-cache config normalization and service-presence status | tmpfiles/systemd mount generation remains outside Rust. |
| `system::bluetooth` | Bluetooth LE Audio per-device TOML presets | BlueZ/device mutation remains outside Rust. |
| `system::ananicy` | Ananicy profile normalization and explicit gaming rule rendering | Service activation and process scheduling remain outside Rust. |
| `system::flatpak_trim` | Flatpak trim preference and service-presence status | Unit/timer generation and Flatpak execution remain service-owned. |
| `system::quicksettings` | Brightness/tile preference normalization and persistence | D-Bus brightness application remains outside the shared crate. |
| `system::perf_gate` | Performance gate config and recent JSONL p95 regression comparison | Benchmark execution and ledger writes remain outside Rust. |
| `system::driver_config`, `gpu_power` | Graphics driver and GPU power preference normalization/persistence | Driver installation and `/sys` power-level writes remain outside Rust. |
| `system::readahead` | Readahead preference normalization and persistence | Filesystem fadvise application remains outside the shared crate. |
| `system::btrfs_autotune`, `overlay` | Btrfs autotune config/script and Podman metacopy config/drop-in rendering | Timer/service activation and filesystem/container runtime operations remain outside Rust. |
| `system::io_tune` | I/O profile normalization and explicit udev rule rendering | udev reload and device mutation remain outside Rust. |
| `system::office`, `privacy`, `signing` | Office association, privacy, and signing preference models plus Git config projection | Desktop MIME activation, privacy policy application, and signing commands remain outside Rust. |
| `system::memory_tune` | RAM-tier selection and deterministic sysctl/zram configuration content | Boot-time zram setup and sysctl application remain outside Rust. |
| `system::performance`, `system_probe` | CPU topology, Gamescope argument shaping, and firewall/SELinux/Secure Boot/autologin parsing | Active performance writes and live command collection remain outside Rust. |
| `system::numa`, `flatpak_prefetch`, `distrobox_cache`, `quadlet` | NUMA, Flatpak prefetch, Distrobox cache, and Quadlet config models | CPU affinity, systemd/timer activation, mounts, and container execution remain outside Rust. |
| `system::update_coordinator` | Locked atomic boot-health/staged-update state transactions | Policy transitions and upgrade execution remain caller/service-owned. |
| `system::zswap` | Zswap profile/compressor/zpool normalization and sysctl/modprobe rendering | Module loading and active swap policy remain outside Rust. |
| `system::telemetry_opt` | Telemetry enable/collector filtering and auditable purge state | Collector execution and telemetry transport remain outside Rust. |
| `system::input_preset`, `rgb_preset`, `power_preset`, `steam_input`, `overlay_preset` | Offline device/game preset models, clamping, persistence, and overlay environment projection | libinput/OpenRGB/Steam/overlay runtime mutation remains outside Rust. |
| `system::preference_presets` | Fonts, locale, OOMD, immutable `/etc` overlay, Steam deadzone, and SELinux gaming config models | Desktop/system policy application and overlay activation remain outside Rust. |
| `system::service_preferences` | Plymouth, shader-cache hashing/status, polkit rule rendering, and SCX preset models | Service activation, polkit installation, and cache preheating remain outside Rust. |
| `system::audio_network` | PipeWire latency and network DoT/firewall preference models plus deterministic drop-in projections | PipeWire reload, resolved/firewalld mutation, and TTL markers remain outside Rust. |
| `system::runtime_preferences` | Trim, UKSM, journald, IRQ, and FS-Cache config models plus reversible generated snippets | Service activation, CPU autodetection, and active filesystem/scheduler changes remain outside Rust. |
| `system::gaming_kargs` | Per-game HDR preferences and kernel-argument config/drift projection | Gamescope latency setup, DMI-specific mutation, and rpm-ostree kargs changes remain outside Rust. |
| `system::display_policy` | VRR/night-colour config normalization, persistence, and KWin policy mapping | KWin/KScreen/D-Bus mutation remains outside Rust. |
| `system::plasma_hdr` | HDR/VRR preset settings, bounded KWin argv projection, and section-aware status parsing | KWin writes, output HDR application, and D-Bus reconfiguration remain caller-owned. |
| `system::display_live` | Bounded KScreen inspection plan, debounce policy, and mode readback evaluation | Live display mutation remains a guarded desktop action. |
| `system::vpn_saml` | VPN sleep-survival flag and ordered TERM/KILL command projection | Process signaling and worker lifecycle remain caller-owned. |
| `system::network_services` | Cloud-drive and Tailscale offline preference models and persistence | rclone mounts, Tailscale control, and credential/network operations remain outside Rust. |
| `system::extended_preferences` | Fan curves, Fcitx/PipeWire gaming, PCIe/PSI, Wine sync, mimalloc, sccache, and shader-cache preference/rendering helpers | Hardware probing, service activation, preload application, and active device writes remain outside Rust. |
| `system::desktop_preferences` | Flatpak override arguments, Plasma drift section flattening, and window-snap preference models | Flatpak/KDE mutation and session reconfiguration remain outside Rust. |
| `system::akmods_lock` | Single-flight bounded lock for NVIDIA module builds | The lock does not start or supervise an akmods build. |
| `system::qualification` | Acceptance sentinel parsing, qualification reports, and regression budgets | Probe, benchmark, VM, and deployment execution remain caller-owned. |
| `system::vm_acceptance` | Acceptance reference validation, bootc/ostree JSON decoding, state normalization, and event framing | Guest commands, power control, and smoke-check execution remain caller-owned. |
| `system::role_preset` | Offline role preset defaults, TOML loading, list overrides, and persistence | Package/container/extension installation remains an explicit action. |
| `system::wayland` | Wayland/software-compositor policy, DRM detection, greeter-session config, session classification, and argv projection | Session file writes and compositor startup remain caller-owned. |
| `system::tunable_registry` | Declarative tunable catalog loading, name normalization, and safe lookup/listing | Dynamic dispatch and tunable application remain caller/service-owned. |
| `system::ai_plan` | Offline deterministic repair-action planning and serialized plan ordering | Action execution, model calls, and network access remain caller/service-owned. |
| `system::ai_dev` | Environment-derived AI/developer config and Distrobox enter/create argv projection with GPU flags | Container creation, provisioning, model downloads, lifecycle commands, and Ollama remain caller-owned. |
| `system::perf_policy` | Offline AI performance sample model, deterministic SCX/sysctl/GPU policy selection, and p95 rollback gate | Hardware sampling, optional model calls, and privileged policy application remain caller/service-owned. |
| `system::scheduler_arbiter` | Scheduler arbiter configuration normalization, single-writer desired-state policy, and flag projection | Service/process detection, gamemode rewriting, and scheduler activation remain caller/service-owned. |
| `system::gaming_cgroup` | Declarative gaming cgroup configuration normalization and systemd slice drop-in rendering | Drop-in writes, systemd activation, and live process placement remain caller/service-owned. |
| `system::gaming_truth` | Offline compatibility payload parsing, Steam manifest discovery, normalized library lookup, and compatibility classification | Remote compatibility refresh, network access, and UI ownership remain caller/service-owned. |
| `system::gaming_versions` | Pinned UMU/Proton-CachyOS/Mesa gaming metadata loading, candidate-path/cache/env precedence, and OCI-label projection | Remote version resolution and runtime cache writes remain build/runtime-owned. |
| `system::gaming_activity`, `system::gaming_kargs` | Gaming-session trigger precedence, GameMode/process-name interpretation, and per-game launch environment projection | Login-session/D-Bus/`/proc` collection and game launching remain caller-owned. |
| `system::clip_quick` | Clipboard-history/tile config normalization and fixed Klipper argv projection | Klipper configuration application remains an explicit desktop action. |
| `system::kwin_latency` | KWin latency profile normalization and generated drop-in/environment projection | File installation, KWin reload, and session mutation remain caller-owned. |
| `system::app_suggestions` | Packaged EXE-handler application database loading, regex lookup, and embedded fallback behavior | Desktop MIME registration, Flatpak installation, and executable-handler UI remain caller-owned. |
| `system::scaling` | Fractional per-output scaling TOML normalization, persistence, and KWin data projection | KScreen discovery, ICC deployment, and display mutation remain guarded desktop actions. |
| `system::system_audit` | Pure audit aggregation and compact summary formatting | Perf/snapshot collection, cache writes, and live system probing remain caller-owned. |
| `system::save_cloud` | Offline per-game save-cloud TOML model, defaults, and atomic persistence | Save discovery, restic/rclone execution, network access, and credential handling remain caller-owned. |
| `system::maintenance` | Bounded Steam deduplication-target discovery, filesystem capability classification, and deterministic duperemove argv projection | Trash deletion, secure hash-database creation, and deduplication execution remain caller-owned. |
| `system::plymouth` | Plymouth policy constants, image discovery, fingerprints, and pure initramfs inspection | `dracut`, mount remounts, and initramfs writes remain Python-owned. |
| `system::perf_transaction` | Performance transaction plan and dry-run/apply rollback evaluation | Backup copying and privileged `sysctl` execution remain caller-owned. |
| `system::polish_manifest` | Declarative folders, metadata, and MIME-default manifest | Desktop filesystem creation and MIME database writes remain caller-owned. |
| `system::smoke_check` | Typed smoke-check rows, filesystem/content checks, command-presence projection, and exit-status aggregation | Live command/service probes, console/JSON output policy, and process exit remain caller-owned. |
| repos | Third-party repository JSON decoding and deterministic yum-repo rendering | Repository enablement, key import, and package-manager mutation remain explicit actions. |
| transfer | Shared size parsing and human-readable transfer formatting used by installer/welcome surfaces | Network polling, download execution, and UI state remain caller-owned. |
| secret_scan | Pure high-confidence private-key/token pattern matching and binary-file exclusion for CI secret checks | Git enumeration, report output, and CI failure policy remain script-owned. |
| setup_transfer | Setup-archive manifest schema, restore-path allowlist, and support-friendly preview summary | Archive extraction/restoration, Flatpak/network discovery, and credential handling remain caller-owned. |
| desktop_polish | Declarative first-login folder/MIME manifest and owned desktop-shortcut drift detection | KDE configuration writes, folder creation, and user-session commands remain caller-owned. |
| release_identity | Canonical ISO release identity validation and artifact-name projection, with a Rust CLI wrapper | Git HEAD lookup and GitHub output-file writing remain CLI orchestration; the existing Python workflow remains authoritative until runner-toolchain adoption is verified. |
| release_publish | Release channel presentation, asset/release URL projection, and static `gh release` argv planning | GitHub API calls, artifact uploads, notes-file writes, and release deletion remain release orchestration. |
| build_metadata | Typed image, release-artifact, and supply-chain metadata projections matching the build-script JSON contracts | File writes, artifact inspection, and workflow orchestration remain outside the shared crate. |
| build_checks | RPM manifest extraction, coverage-floor ratcheting, base-image label/digest decisions, and stable source hashing | Docker/GitHub inspection, report writes, and CI exit-code policy remain outside the shared crate. |
| build_metrics | Optimization-report static metric calculation and JSON report projection | Filesystem traversal, runtime probes, and report-file writes remain build-script orchestration. |
| commands | Explicit argv validation, `ujust` recipe validation, environment filtering, and sensitive-argument redaction | Process execution, spawning, timeouts, and caller-specific failure policy remain outside the shared crate. |
| diagnostic_report | Typed diagnostic result rows, warning/failure aggregation, exit-status projection, and human-readable rendering | Live probes, notifications, report-file writes, and process exit remain caller-owned. |
| sarif | Changed-file SARIF finding filtering, source-suppression handling, and safe file-URI projection | Report collection, file I/O, and CI exit-code policy remain caller-owned. |
| doctor | Read-only health score calculation and local evidence collection for kernel, hardware, memory, filesystem, scheduler, and desktop-stack status | Repair execution and live notifications remain caller-owned. |

Most functions ported are pure reads against on-disk state, parsers, or a
single bounded subprocess call. A few explicit Hub actions are exceptions:
Guardian repairs, firmware update helpers, PipeWire configuration, and
software catalog import/install helpers are user-invoked and bounded; they
must not be expanded into generic command execution. The crate still does
not run Guardian's live multi-probe sweep, and it does not contain installer
partitioning or other high-risk writers. Keep those boundaries explicit when
adding another port.

## How more of it moves over

One module (or one function) at a time, in this order of preference:

1. **Read-only first.** A function that reads a file, a cache, or runs one
   cheap command and returns data is a good candidate. A function that
   writes state, executes a repair, or runs a probe sweep is not — do
   those later, once there's a real reason (a Rust caller that needs it)
   and real test coverage proving parity with the Python original.
2. **Port faithfully, not "improved."** Match the Python original's
   behavior exactly, including its quirks (see `system::gpu`'s doc comment
   for a real example — `lspci_gpu_lines`'s substring-match gotcha is
   preserved on purpose). Fix bugs as a separate, deliberate, reviewed
   change — not silently as part of a port, where it's easy to miss that
   the behavior changed at all.
3. **Test parity, not just "it compiles."** Every module here has
   `#[cfg(test)]` unit tests exercising the same scenarios the retired
   Python bridge tests (`tests/test_kyth_hub_shell_bridges.py`, since
   deleted — check git history for the shape) covered, using an explicit
   path/state parameter rather than mutating process-global env vars (see
   `system::probe::read_section_in` / `guardian::load_state_from`) — keeps
   tests parallel-safe and avoids flakiness from shared mutable env state.
4. **The Python module stays authoritative until its Rust port is proven.**
   Nothing here deletes or stops calling the Python original elsewhere in
   the codebase (kyth-welcome, ujust recipes, systemd units all keep using
   `kyth_shared` directly) — this crate is additive, a second consumer path
   for the Tauri shell specifically, not a replacement deployed everywhere
   at once.

## Why a separate crate instead of folding into kyth-hub-shell

Because the Tauri shell isn't going to be the only Rust consumer forever —
keeping this as its own crate (`kyth-shared`, a plain path dependency, no
workspace yet — see `src-tauri/Cargo.toml`) means the next Rust thing that
needs `kyth_shared` reads doesn't need to depend on a GUI shell binary to
get them.
