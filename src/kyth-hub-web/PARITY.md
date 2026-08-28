# Kyth Hub Parity — Python (Qt/PySide6) → React/Rust (Tauri)

Python Hub is authoritative until this file says otherwise. Build is `check-hub-web-shell.sh` (npm ci → npm build → cargo test → cargo build → asset-embed assert) and `validation.yml` pins `PySide6==6.11.1`.

## Destination → Section map (single source: `src/kyth-hub-web/src/data/hubSections.ts` ↔ `src/kyth-welcome/page_registry.py:DESTINATION_SECTIONS`)

| Destination | Sections (Python `DESTINATION_SECTIONS`) | React `HubSection` status | Live data |
|---|---|---|---|
| Home | Welcome (Dashboard) | `Dashboard.tsx` live — Guardian/Channel/GPU/Storage/User/BootChecks/Recovery via `liveData.ts` → `main.rs:kyth-shared` | live, telemetry charts live when sessions exist |
| Play | Gaming, Performance, Compatibility, Controllers | `Play.tsx` → 4 sections, all `LiveSectionCard` | Gaming/Performance/Compatibility/Controllers read `audit-cache`/`controllers-detect` probe |
| Apps | App Store, Work Setup | `Apps.tsx` → 2 sections | App Store `flatpak-apps`, Work Setup probe |
| This PC | Guardian, Update, Hardware, Plasma Wayland, Diagnostics, Repair, NVIDIA, Kernel, Channels, Just, Feedback (11) | `ThisPc.tsx` → 11 sections | All 11 have `liveData.ts` fetchers + `main.rs` bridge |
| Move In | Move Files, Cloud Storage, Network Shares, VPN | `MoveIn.tsx` → 4 sections | Move Files `ntfs-drives`, Cloud `network-summary`, Shares `smb_browse`, VPN probe |

`26` page keys total (`Welcome` + `5` landings + `21` sections + `1` Dashboard alias) — `page_registry.py:SEARCH_ITEMS` and `src/kyth-hub-web/src/search.ts` share same keys after `destinations.ts` single-source fix.

## What is still not 100%

### 1. Charts — live telemetry wired
`PerformanceChart.tsx`/`SessionsChart.tsx` read `kyth-telem` sessions through `liveData.ts:fetchTelemetryRecent` → `telemetry_recent` → `kyth-shared-rs::system::telemetry::recent_sessions` (read-only sqlite). They show `Live` when usable session data exists and an explicit no-data state otherwise; they never render the old `mockDashboard.ts` series.

### 2. Gaming library/migration/setup sub-tabs — PARTIAL LIVE (GamingSection + library scan)
Python `page_gaming.py` composes 6 mixins (`page_gaming_dashboard/setup/library/fixes/tools/migration`) each with workers (`DataWorker`, `WindowsLibraryWorker`, `ProtonDbBatchWorker`). React `GamingSection.tsx` only shows `audit` master pills. Now `GamingSection` shows `gaming_library` scan (Steam/Heroic/Lutris/Bottles) via `gaming_library.rs` + `fetchGamingLibrary`; still TODO: migration checklist, ProtonDB batch and `compatibility` (`protondb`, `anticheat`) bridges.

### 3. Software sub-tabs — PARTIAL LIVE (AppStoreSection + starter packs)
Python `page_software.py` 7 mixins (Starter Packs, Flatpak Store, AppImages, Installed, Developer, Security, Creator) with `software_catalogs.py` (`STARTER_PACKS`, `SEC_BOX`, `FAMILAR_APPS`). React `AppStoreSection` only shows `installedCount/updatesAvailable`. Now `AppStoreSection` shows `starter_packs` via `software_catalog.rs` + `fetchStarterPacks` + flatpak counts; still TODO: `familiar_apps`, `appstream` full catalog, AppImages.

### 4. kyth_shared → kyth-shared-rs coverage
Python `src/kyth_shared/kyth_shared` `≈209` modules / `≈1494` defs vs Rust `src/kyth-shared-rs/src/system` `≈30` modules (≈14%). `MIGRATION.md` reserves write/collector paths (installer partitioning, SELinux, VPN connect, `zypp`/`dnf`, `collect_snapshot`, `execute_recipe`) — intentionally read-only first. Parity for UI does not require 100% of `kyth_shared` — only the UI-facing reads + the `≈8` mutating `just_*` recipes (`upgrade`, `rollback`, `switch-channel`, `guardian_execute`, `just_run`) already exposed.

### 5. Launchers & single-instance — NOW DEFAULT (kyth-welcome-launch switched)
Python: `app.py:QLocalSocket/QLocalServer` + `--page <key>` + `instance_ipc.py`, `krunner_desktop.py`, `kyth-welcome.desktop`. Rust: `main.rs:PendingPage(Mutex<Option<String>>)` + `tauri-plugin-single-instance` + `take_pending_page` — contract matches. `src/kyth-welcome/kyth-welcome-launch` now defaults to `/usr/bin/kyth-hub-shell` when executable, fallback to `kyth-welcome` only on old image/failed build; channel check removed (testing/stable both get Rust shell). `Dockerfile` `COPY --from=hub-web-builder /usr/bin/kyth-hub-shell` already additive, `23-kyth-helper-ctx-installs.sh` installs both .desktop files unchanged.

## Making React/Rust the main — steps

1. **Live-ify charts** — port `telemetry::recent_sessions`, expose `telemetry_recent`, update `PerformanceChart/SessionsChart` to `liveData` with `Live/Preview` badge (this file's #1).
2. **Port gaming/software library readers** — `gaming_slice`, `appstream`, `installed-apps` reads (read-only).
3. **Port search index single source** — `destinations.ts` already single source; verify `search.ts` ↔ `page_registry.py:rank_search_results` tie-break `score desc, key asc (W4)` parity with unit test.
4. **Switch launchers** — `.desktop`, `kyth-welcome-launch` → `kyth-hub-shell --page`, behind `KYTH_USE_PYTHON_HUB=1` fallback for one release.
5. **CI** — `just check-hub-shell` in `validation.yml` alongside `test_kyth_welcome_hub_smoke.py` (already `13 passed` under `KYTH_FORCE_HEAVY_GUI_SMOKE=1`).
6. **Retire Python UI** — remove `src/kyth-welcome` from image; keep `src/kyth_shared` for `kyth-probe`/`kyth-guardian` headless services until Rust ports exist.

This file is the gate — do not delete Python Hub until #1-#3 are `live` and #4 is behind flag.
