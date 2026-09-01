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
| `RecipeButton: apply-staged` | `just_run` | `{ recipe: "apply-staged" }` | `JustLaunch` | mutate | indirect |
| `RecipeButton: update-health` | `just_run` | `{ recipe: "update-health" }` | `JustLaunch` | check | indirect |
| `waitJustJob` | `just_run_status` | `{ job }` | `InstallStatus` | read | covered |

## Baseline gaps exposed by this ledger

1. The frontend contract is currently encoded in string literals spread across
   `liveData.ts`; there is no generated schema or compile-time check against
   Rust response fields.
2. `probe_backend` is a multiplexed command, so selector coverage must be
   tested separately from command-name coverage.
3. `just_run` is shared by read/check and mutating recipes; the recipe trust
   class is not represented in its Rust signature.
4. The mutating wrappers return plain strings rather than a structured action
   result, so confirmation and failure semantics remain a follow-up item.

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
