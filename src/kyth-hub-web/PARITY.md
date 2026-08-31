# Kyth Hub Parity — Python (Qt/PySide6) → Rust/Slint

The native UI migration is active: `src-tauri/src/native_main.rs` and
`src-tauri/ui/hub.slint` provide the Slint shell and direct Rust status reads.
The native Slint binary is now the default launcher. The Tauri/React shell is
kept as a controlled compatibility fallback with `KYTH_USE_REACT_UI=1` until
the remaining feature pages and guarded actions have native parity.

**The native Rust/Slint Hub is now the default Hub the user sees.**
`kyth-welcome-launch` prefers `/usr/bin/kyth-hub-native`, then falls back to
`/usr/bin/kyth-hub-shell` when the native binary is unavailable or
`KYTH_USE_REACT_UI=1`, and finally to the old Qt Hub on older images. The Qt
Hub remains in the tree as an old-image fallback and as the source of the
headless `kyth-probe`/`kyth-guardian` services. The React/Tauri build remains
covered by `check-hub-web-shell.sh` until the compatibility path is retired.

## Destination → Section map (single source: `src/kyth-hub-web/src/data/hubSections.ts` ↔ `src/kyth-welcome/page_registry.py:DESTINATION_SECTIONS`)

| Destination | Sections (Python `DESTINATION_SECTIONS`) | React `HubSection` status | Live data |
|---|---|---|---|
| Home | Welcome (Dashboard) | `Dashboard.tsx` live — Guardian/Channel/GPU/Storage/User/BootChecks/Recovery via `liveData.ts` → `main.rs:kyth-shared` | live, telemetry charts live when sessions exist |
| Play | Gaming, Performance, Compatibility, Controllers | `Play.tsx` → 4 sections, all `LiveSectionCard` with actions | Gaming: `audit-cache` + `gaming_library` + `gaming_slice`. Performance: `audit-cache` + PipeWire quantum presets. Compatibility: `secureboot-state` + `mesa_version` on mount, `mok_status`/`mesa_overlay_dry_run` on demand. Controllers: `controllers-detect` cache + live `controllers_detect` rescan |
| Apps | App Store, Work Setup | `Apps.tsx` → 2 sections | App Store: `flatpak-apps`/`flatpak-updates` + `starter_packs` + `familiar_apps` chooser. Work Setup: `fonts_ready` + `network-summary` on mount, `ipp_discover` on demand |
| This PC | Guardian, Hardware, Plasma Wayland, Diagnostics, Repair, NVIDIA, Kernel, Channels, Just, Feedback (10) | `ThisPc.tsx` → 10 sections, all with actions | Repair: `recovery_status` + `deployment_history` + read-only `snapshot_timeline`/`snapshot_count` + `btrfs_health` + `memory_pressure`. Hardware: `hardware-summary` on mount, `pci_devices_by_class`/`loaded_kernel_modules`/`firmware_updates_count` on demand. Plasma: `display-detect` + `plasma_presets` + `desktop_stack_checks`. Diagnostics: `audit-cache` + `boot_runtime_checks` + `is_live_session`. Feedback: prefilled `kyth-os/kyth` issue via `open_feedback_issue` |
| Move In | Move Files, Cloud Storage, Network Shares, VPN | `MoveIn.tsx` → 4 sections, all with actions | Move Files: `ntfs-drives` cache + live `ntfs_devices` rescan. Cloud: `network-summary` + `cloud_oauth_status` + `rclone_oauth_command`. Shares: `smb_browse`/`smb_mount_command`. VPN: `network-summary` + live `network_identity` refresh. All three network sections escalate to `network_identity` on Refresh |
| Updates | Updates | `Updates.tsx` → dedicated update page | `update_status`/`pending_updates_summary` on mount, `collect_availability` → `update_availability_view` on demand |

`27` page keys total (`Welcome` + `6` landings + `21` sections + `1` Dashboard alias) — `page_registry.py:SEARCH_ITEMS` and `src/kyth-hub-web/src/search.ts` share same keys after `destinations.ts` single-source fix. Updates is a dedicated left-rail destination and is listed last in the web menu.

## Conventions the sections follow

- **Nothing renders a fixture.** `services/liveData.ts` returns `null` on failure, and the section shows an honest empty state. `mockDashboard.ts` is now `dashboardTypes.ts` and holds only types; `SectionPreviewCard.tsx` is deleted.
- **Cheap reads on mount, expensive reads on a button.** `mokutil` (~seconds), `fwupd` (20s timeout), `collect_availability` (15s deadline), `ipp_discover`/`smb_browse` (network) and the live driver scan all sit behind an explicit button so switching tabs never stalls.
- **Where a cached and a live read both exist, mount uses the cache and a Refresh/Rescan button escalates to live.** The live result wins once it exists (Controllers, Move Files, the three network sections, Hardware).
- **A recipe is never reported as complete before it finishes.** `just_run`, upgrade, rollback, and channel switching start a captured background job. The Tauri shell waits for the process result, keeps a concise stdout/stderr summary, and the Hub renders running, complete, or failed status inline. KDE's graphical askpass helper handles sudo authentication when needed, so the user never has to hunt for a newly opened terminal window.
- **`*_command` helpers return argv and are rendered as copyable text, not spawned.** A generic "run this argv" bridge command would be a new privilege surface. Where a ujust recipe covers the same ground, the section pairs the text with a `RecipeButton` — that path goes through `just_run`, which validates the recipe name and lets the recipe do its own privilege prompt.
- **`just` is invoked the way `ujust` invokes it.** `ujust` is `JUST_JUSTFILE="/usr/share/ublue-os/justfile" /usr/bin/just "${@}"`, and `branding/31-ujust-recipes.sh` appends kyth's import to that file. A bare `just` walks up from the process working directory instead — the Hub's is whatever the .desktop launcher gives it, so on a real install `just --list` returned "no justfile found" and every recipe button spawned a process that exited immediately while the UI said it was running. `system::just` sets that variable (which also gives `just` the justfile's parent as its working directory, matching `ujust` exactly on just 1.58) and is the only module allowed to spawn `just`. `build_files/kyth-welcome/kyth_welcome/page_just.py` still has the bare-`just` defect; deliberately not fixed, since the Qt Hub is the old-image fallback only and follow-up item 6 retires it.
- **The listing includes upstream's recipes, because ujust's justfile does.** Pointing at `/usr/share/ublue-os/justfile` reaches ublue's own imports (`10-update.just`, `30-distrobox.just`, …) as well as kyth's — 23 more recipes, 14 of them argument-free, so Recipes (Just) offers buttons for `bios`, `clean-system`, `update-firmware`, `enroll-secure-boot-key` and friends. That is the same exposure as typing `ujust <name>`, and the terminal wrapper means each still shows its own output and prompt; it is listed here because it is a behaviour change from the kyth-only list, not a defect.

## Privileged action boundary

Long-running Hub actions return a job and are polled by the frontend; they do not block the Tauri UI thread. User Flatpak removal runs with `--user`. System Flatpak removal and named hardware/storage operations use `/run/kyth/privileged.sock`, provided by the root-owned `kyth-privileged.service`. The socket accepts fixed operation names only (`flatpak_uninstall`, `firmware_update`, `nvidia_install`, `kernel_switch`, `windows_verify`, `secureboot_enroll`, and `bitlocker_unlock`), validates peer credentials and arguments, passes BitLocker keys on stdin, and records an audit line without the secret. It is not a generic command or argv bridge.
- **Recipe launches stay in the Hub.** The shipped recipes use `sudo`, never `pkexec` (`build_files/just/kyth/*.just`). The Tauri runner invokes `/usr/bin/just` directly with `JUST_JUSTFILE` set, captures output, and supplies `SUDO_ASKPASS=/usr/bin/ksshaskpass` when available. No Konsole/xterm wrapper is used for Hub actions; explicit terminal-app buttons elsewhere remain intentional user requests to open a shell.
- **`tests/test_kyth_hub_web_actions.py` and `tests/test_kyth_hub_web_invocation.py` are the gate.** It fails the build if any `liveData.ts` export is orphaned, if any `generate_handler!` command lacks a wrapper without a documented exemption, if a section key has no component, or if a `RecipeButton` names a recipe that does not exist in `build_files/just/` — or names one that takes parameters. `just_run` spawns `just <name>` with no arguments, so a parameterized recipe runs its defaults, which need not be what the button says: `switch-kernel flavor="fedora"` under a "Switch kernel" button staged a switch *off* the CachyOS default. Those belong in a `CommandLine`, where the argument is visible. The Recipes (Just) listing builds its rows from `just --list` at runtime, so no static check can see those names — `just_list` returns a `params` field and the section renders parameterized rows as text instead of buttons. `main.rs`'s `JustRecipeResponse` did not serialize `params`, so that guard read `undefined` and buttoned every row anyway; `test_kyth_hub_web_invocation.py` now checks each bridge struct against the TS interface that reads it. Verified against real `just 1.58` output for ublue's justfile with kyth's import appended — what `ujust --list` prints on the image, not kyth's recipes alone: 223 recipes, 101 argument-free (buttons) and 122 parameterized (text). Two kinds of non-recipe line are dropped: the `[KythOS]` heading `[group('KythOS')]` produces (it used to become a button that spawned `just [KythOS]`), and a doc comment `just` prints on its own line when the signature is long, which used to become a row named `#` — upstream's `distrobox-assemble`/`distrobox-new` produce two of those, so the listing also had duplicate React keys.

## What is still not 100%

### Native Rust/Slint interactive surface — expanded

The native shell now exposes fixed interactive controls for the high-value
workflows that can be safely represented without a generic command bridge:
updates and rollback, Guardian safe repair, Flatpak search/install, gaming and
balanced performance profiles, firmware update, Office fonts, Windows
verification, save-migration tooling, Tailscale setup, AppImage import/launch,
user-scoped Flatpak removal, curated starter packs, ProtonDB lookup, feedback report generation,
BitLocker unlock, SMB browse/mount, and the read-only
desktop/network/deployment/kernel/channel refresh actions. System-changing
native actions use a two-step confirmation gate and the core recipe runner now
publishes structured running/complete/failed state with a native job id, while
reporting bounded completion or failure inline. Remaining parity work is richer dynamic presentation and
selection: cloud OAuth terminal handoff, installed-app/AppImage inventories,
arbitrary recipe selection, and deeper per-section details. All secret-bearing
inputs are validated and kept out of status text.

### 1. Charts — live telemetry wired
`PerformanceChart.tsx`/`SessionsChart.tsx` read `kyth-telem` sessions through `liveData.ts:fetchTelemetryRecent` → `telemetry_recent` → `kyth-shared-rs::system::telemetry::recent_sessions` (read-only sqlite). They show `Live` when usable session data exists and an explicit no-data state otherwise; they never render the old `mockDashboard.ts` series.

### 2. Gaming library/migration/setup sub-tabs — PARTIAL LIVE (GamingSection + library scan)
Python `page_gaming.py` composes 6 mixins (`page_gaming_dashboard/setup/library/fixes/tools/migration`) each with workers (`DataWorker`, `WindowsLibraryWorker`, `ProtonDbBatchWorker`). React `GamingSection.tsx` covers the workflow with audit/master state, detected launchers and library counts, gaming-slice launch options, ProtonDB batch lookup, anti-cheat compatibility, migration guidance, and recipe-backed setup/fix/tool actions.

### 3. Software sub-tabs — PARTIAL LIVE (AppStoreSection + starter packs + familiar apps)
Python `page_software.py` 7 mixins (Starter Packs, Flatpak Store, AppImages, Installed, Developer, Security, Creator) with `software_catalogs.py` (`STARTER_PACKS`, `SEC_BOX`, `FAMILAR_APPS`). React `AppStoreSection` covers Flatpak counts, starter packs with selectable apps, the familiar-app chooser, debounced Flathub search/install, AppImage discovery/import/launch, installed Flatpak removal, and recipe-backed developer tools. Install actions poll the Rust job bridge and refresh the inventory after completion.

### 4. Guardian repairs — PARTIAL (command table + eligibility gate ported)
`guardian_execute_recipe` used to hand the recipe id to `just_run`. Guardian ids are dotted (`audio.restart`) and are not just recipes, so nothing ever ran — and the spawn still succeeded, so the Hub reported every repair as launched, advisory notifications included. `guardian.rs` now carries each recipe's `command` argv from `guardian.py`, ports the user-initiated gate, implements all ten `guardian_actions.py:ACTION_EXECUTORS` with bounded argv calls, verifies results, enforces cooldowns, and records Hub executions in Guardian history. `GuardianSection` only offers "Run fix" for a runnable risk.

### 5. kyth_shared → kyth-shared-rs coverage
Python `src/kyth_shared/kyth_shared` `≈209` modules / `≈1494` defs vs Rust `src/kyth-shared-rs/src/system` `≈31` modules (≈15%). The Rust hardware-policy slice now evaluates read-only inventory and selectors, while `MIGRATION.md` reserves policy application and other collector/high-risk writer paths (installer partitioning, SELinux, VPN connect, `zypp`/`dnf`, and `collect_snapshot`). The Hub's explicit Guardian repair path is ported with the same eligibility, cooldown, verification, and fixed-command policy as Python; the live Guardian sweep and service state writer remain Python-owned. Parity for UI does not require 100% of `kyth_shared` — only the UI-facing reads plus the small set of explicitly exposed mutating actions.

### 6. Launchers & single-instance — NATIVE UI NOW DEFAULT
Python: `app.py:QLocalSocket/QLocalServer` + `--page <key>` + `instance_ipc.py`, `krunner_desktop.py`, `kyth-welcome.desktop`. Rust: the native Slint shell accepts `--page <key>` and preserves the same destination contract. `src/kyth-welcome/kyth-welcome-launch` now defaults to `/usr/bin/kyth-hub-native`; `KYTH_USE_REACT_UI=1` selects the React/Tauri compatibility shell, and older images fall through to `/usr/bin/kyth-welcome`. `Dockerfile` already ships both Rust binaries, and `23-kyth-helper-ctx-installs.sh` installs the unchanged desktop entries.

## Remaining work

The four React feature-completeness items remain implemented in the compatibility
shell: Gaming has a migration checklist, ProtonDB lookup, and anti-cheat
guidance; App Store has Flatpak catalog search, AppImage discovery, and
background Flatpak installation status; presets preview before confirmation;
and Guardian repairs execute with verification/cooldowns/history. The native
Rust migration now covers the common interactive paths plus read-only
snapshot/deployment timeline and staged-update truth used by Repair. Remaining
product work is dedicated native controls for the listed high-risk workflows,
installed-image acceptance testing, deeper parity in still-Python collector
paths, and eventual React/Qt removal.
