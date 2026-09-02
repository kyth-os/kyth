# System Hub command ledger

This is the baseline contract inventory for the Dashboard and Updates workflows.
The contract test in `tests/command-contract.test.mjs` checks that every ledger
entry still has a frontend wrapper and is registered in the Tauri handler.

## Trust classes

- **read** — observes local state; must not mutate the system.
- **check** — performs a bounded availability or health check; may use network
  or external tools but must not apply changes.
- **mutate** — changes system state or starts an action requiring confirmation
  and an explicit UI busy/error state.

## Dashboard

| Wrapper | Rust command | Payload / selector | Response | Class | Status |
| --- | --- | --- | --- | --- | --- |
| `fetchGuardianSnapshot` | `guardian_snapshot` | none | `GuardianBridgeResponse` | read | covered |
| `fetchUpdateChannel` | `current_update_channel` | none; cache with bootc fallback | `string \| null` | read | covered |
| `fetchGpuName` | `hardware_snapshot` | none | `HardwareBridgeResponse` | read | covered |
| `fetchStorageFree` | `storage_snapshot` | none | `StorageBridgeResponse` | read | covered |
| `fetchUserName` | `current_user_name` | none | `string` | read | covered |
| `fetchBootRuntimeChecks` | `boot_runtime_checks` | none | `BootRuntimeCheck[]` | read | covered |
| `fetchRecoveryStatus` | `recovery_status` | none | `RecoveryStatus` | read | covered |

## Updates

| Wrapper / action | Rust command | Payload / selector | Response | Class | Status |
| --- | --- | --- | --- | --- | --- |
| `fetchBootcSnapshot` | `probe_backend` | `section: "bootc-status-data"` | `ProbeBridgeResponse` | read | covered |
| `fetchBootcSnapshot` | `probe_backend` | `section: "bootc-branch"` | `ProbeBridgeResponse<string>` | read | covered |
| `fetchUpdateStatus` | `update_status` | none | `UpdateStatusLive` | read | covered |
| `fetchPendingUpdatesSummary` | `pending_updates_summary` | none | `Record<string, string>` | read | covered |
| `fetchUpdaterAvailable` | `updater_available` | none | `boolean` | read | covered |
| `checkForUpdates` | `collect_availability` | `{ branch: null, useCached: false }` | `AvailabilityStatusLive` | check | covered |
| `checkForUpdates` | `update_availability_view` | availability view model | `UpdateAvailabilityView` | read | covered |
| `invokeBootcUpgrade` | `bootc_upgrade` | none | `string` | mutate | covered |
| `invokeBootcRollback` | `bootc_rollback` | none | `string` | mutate | covered |
| `invokeApplyStaged` | `apply_staged` | none | `string` | mutate | covered |
| update job polling | `update_job_status` | `{ job }` | `InstallStatus` | read | covered |
| `fetchUpdateHealth` | `update_health` | none | `UpdateHealthLive` | read | covered |
| `healthReport` | `update_health` | none | `UpdateHealthLive` | check | covered |

## Baseline gaps exposed by this ledger

1. The frontend contract is currently encoded in string literals spread across
   `liveData.ts`; there is no generated schema or compile-time check against
   Rust response fields.
2. `probe_backend` is a multiplexed command, so selector coverage must be
   tested separately from command-name coverage.
3. `run_hub_action` is shared by read/check and mutating recipes; its closed
   Rust `HubAction` enum represents the recipe allowlist, while the recipe
   body remains bounded OS orchestration behind the Tauri command.
4. The mutating wrappers return plain strings rather than a structured action
   result, so confirmation and failure semantics remain a follow-up item.

## Full interactive surface

The table below is the release inventory for every remaining non-navigation
Tauri handler.  It is deliberately grouped by policy rather than duplicating
implementation details: additions must be recorded here and in the
frontend/Rust invocation tests.

| Area | Commands | Class | Boundary / release expectation |
| --- | --- | --- | --- |
| Guardian | `guardian_check`, `guardian_control`, `guardian_execute_recipe`, status/history reads | check / mutate | Fixed recipe policy, eligibility and cooldowns; completion must be polled before success is shown. |
| Privilege broker | `privileged_action`, `privileged_action_status` | mutate / read | Fixed operation allowlist only; local peer authorization; secrets never enter argv, status, or audit detail. |
| Updates and channels | `bootc_upgrade`, `bootc_rollback`, `bootc_switch_branch`, `collect_availability`, `run_hub_action`, job status | check / mutate | Explicit confirmation for state changes; `HubAction` and channel values are allowlisted. |
| Applications | `install_flatpak`, `uninstall_flatpak`, AppImage import/chmod/launch, install status | mutate / read | User Flatpak removal stays user-scoped; system changes use their dedicated policy path. |
| Network and migration | `smb_save_configured_share`, `smb_remove_configured_share`, cloud/app launch handoffs, VPN launch, printer discovery/setup text | read / check / mutate | Credentials remain outside config; command-returning helpers are copyable text, never generic execution. |
| Hardware and desktop | firmware, PipeWire, Plasma preset, controllers, display/hardware reads | read / check / mutate | Expensive scans stay on demand; mutating presets require confirmation and bounded argv. |
| Security | Kali lifecycle and host-tool install/uninstall/launch plus job status | read / mutate | Fixed Kali templates and two-tool catalog; no caller-supplied container or Flatpak identifiers. |
| Gaming | tool catalog actions, Discord/OBS fixes, folder open, SCX controls, per-game profile save | read / mutate | Fixed 14-tool catalog and fixed folder/scheduler/profile value sets; no arbitrary path or command bridge. |

### Ledger maintenance rule

Any new `generate_handler!` entry that is not navigation-only must add a row
to this inventory (or the Dashboard/Updates tables above), state its trust
class, and be covered by `test_kyth_hub_web_actions.py` and
`test_kyth_hub_web_invocation.py`.  A handler without that evidence is not
release-ready.

## Native Rust/Tauri additions

The Tauri bridge uses dedicated commands rather than exposing a generic
command or argv surface. Updates, Guardian controls, curated recipes, AppImage
operations, user Flatpak removal, and feedback reports are now represented by
dedicated native handlers. Kernel flavor and channel switches use fixed
allowlisted values and the shared `just` argument validators. BitLocker,
network share browse/mount, AppImage management, and feedback now have typed
typed inputs. BitLocker recovery keys are passed only to the existing
validated privilege request and are never copied into action status. Cloud
OAuth still presents a validated command for a terminal handoff, since its
interactive browser flow is not safely hostable inside the shell.

The Tauri Gaming surface additionally covers the verified launcher/tool
recipes (`install-prismlauncher`, `install-itch`, `install-epic-launcher`,
`install-battlenet`, `install-ea-app`, `install-ubisoft-connect`,
`export-steam-games`, `install-gpu-screen-recorder`, `install-goverlay`,
`install-mangojuice`, `install-lact`, `install-piper`, and `install-solaar`).
They dispatch through the shared `just` allowlist; no free-form command text
is accepted by the bridge.

The Security tab's Kali distrobox lifecycle (`kali_status`, `kali_create`,
`kali_export`, `kali_remove`, `kali_enter_terminal`) and host-tools grid
(`sec_host_tools`, `sec_host_tool_install`/`_uninstall`/`_launch`) are typed
commands backed by `kyth-shared-rs::system::security_container`'s fixed
command templates and 2-tool catalog — never a caller-supplied Flatpak id or
container name.

The Gaming tab's tool grid (`gaming_tools`, `gaming_tool_install`/
`_uninstall`/`_launch`) follows the same fixed-catalog pattern against
`kyth-shared-rs::system::gaming_tools`'s 14-tool list. `fix_discord_screenshare`
and `fix_obs_pipewire` run bounded, `--user`-scoped `flatpak override`
argv synchronously (no sudo, no job needed). `open_game_folder` validates
its `key` against a fixed 2-entry set (`compatdata`, `shadercache`) rather
than accepting a caller-supplied path. `security_job_status` and
`gaming_job_status` both poll the same shared job store in
`commands/job.rs`.

The Gaming tab's overlay/sched-ext/profile-builder commands
(`gaming_perf_status`, `scx_status`, `scx_set_scheduler`,
`profile_launch_option`, `per_game_profile`, `save_per_game_profile`) back
`page_gaming_tools_perf.py`'s remaining cards. `scx_set_scheduler` only
accepts `"rusty"`/`"stop"` — the two schedulers the Hub's buttons offer,
not an arbitrary scheduler name. `profile_launch_option` validates `goal`
against the fixed five-goal set and `fps` as a short digit string.
`save_per_game_profile` validates the Steam app id (non-empty, bounded
length, no quote/control characters — it's interpolated into a TOML
section header) and `profile` against the same fixed goal set before
writing `~/.config/kyth/gaming-per-game.toml`.
