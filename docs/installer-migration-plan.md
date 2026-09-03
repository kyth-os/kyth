# Installer Migration Plan

**Status:** In progress; Phase 1 needs parity work before the Tauri shell starts
**Scope:** Migrate the KythOS installer to the React/Tauri style used by the System Hub.

## Context

The installer already has a web frontend, but its compatibility backend is
Python and is displayed through a native client. The backend owns disk discovery,
partitioning, filesystem resize, bootc deployment, Secure Boot setup, progress,
cancellation, transaction recovery, and rescue mode.

The migration must preserve those safety properties. A UI rewrite and a
Python-to-Rust rewrite should not happen simultaneously: that would make disk
and boot failures difficult to distinguish from frontend regressions.

## Decision

Migrate in layers:

1. Rewrite the existing WebUI in React/TypeScript while retaining the Python
   backend and HTTP/SSE contract.
2. Host the React build in an unprivileged Tauri shell.
3. Move the privileged backend behind a root-owned Unix-socket service.
4. Port backend components selectively to Rust after behavioral parity is
   established.

The Tauri process must not run as root and must not gain a generic command,
filesystem, or disk-writing bridge. The privileged service remains the trust
boundary.

```text
Live-session user
    |
    v
React + Tauri installer shell
    | typed IPC over Unix socket
    v
kyth-installerd (root-owned)
    |
    +-- partition journal and transaction state
    +-- bootc / filesystem / mount operations
    +-- existing Python backend initially
```

## Migration phases

### 0. Freeze the API contract

Document the current routes and events from `src/kyth-installer/kyth_installer/server.py`,
`post_routes.py`, `context.py`, and `webui/install-flow.js`:

- request and response schemas
- lifecycle states and valid transitions
- event types, ordering, and reconnect behavior
- cancellation semantics
- secret handling
- read-only versus destructive operations
- transaction recovery rules

This contract is the compatibility target for both implementations.

### 1. React compatibility frontend with the existing backend

Create `src/kyth-installer-web/` with typed services and page components:

- Welcome
- Disk and installation mode
- Kernel
- Configuration
- Review
- Install/progress
- Rescue

Keep the Python HTTP server and SSE stream unchanged initially. The milestone
is identical installer behavior with a typed React state model and component
tests. This client is compatibility-only; the Rust/Slint client is the
production UI.

### 2. Rust/Slint production UI and Tauri compatibility shell

Create `src/kyth-installer-web/src-tauri/`, following the System Hub shell's
build and single-instance patterns, with these differences:

- run as the live-session user, never root
- do not use `--no-sandbox`
- embed production assets
- expose no unrestricted command or filesystem bridge
- preserve startup routing and one-instance behavior

Initially, Tauri may proxy to the existing loopback Python service. Add a
builder stage and WebKitGTK runtime dependencies to `installer/Containerfile`,
then replace the Chromium launcher only after the shell works in a built live
ISO.

### 3. Unix-socket privileged service

Replace loopback HTTP with a root-owned Unix socket once the Tauri frontend is
stable. Use socket ownership/permissions and peer credentials, retaining a
one-time session token as defense in depth.

Read-only commands:

- disks, partitions, free space, and filesystem options
- locale, timezone, and keymap lists
- source-image status
- transaction and rescue state

Mutating commands:

- create, delete, resize, format, and mount-point operations
- partition journal commit/rollback
- start and cancel installation
- reboot
- copy rescue logs

All validation remains server-side; the UI is never trusted.

### 4. Selective Rust backend migration

Port in this order:

1. Pure request and install-plan validation
2. Disk and partition discovery
3. Partition journal model and serialization
4. Transaction state and recovery guidance
5. Streaming command runner and cancellation
6. Mount lifecycle management
7. bootc installation and target configuration
8. Secure Boot/MOK handling

Retain the Python implementation behind a compatibility adapter until each
subsystem has equivalent tests.

Highest-risk source areas are:

- `partition_ops_journal.py`
- `storage_guard.py`
- `plan_validate.py`
- `recovery.py`
- `phases/storage.py`
- `phases/finalize.py`

## Required safety gates

Before replacing Chromium in the image:

- React build, typecheck, and embedded-asset checks pass.
- All existing installer tests remain green.
- The Tauri shell starts in a live ISO without a development server.
- No unrestricted command execution is available from the UI.
- Passwords never appear in URLs, logs, process arguments, or persistent state.
- Cancellation works during every long-running phase.
- Recovery is tested after partition changes, filesystem resize, image deploy,
  and final configuration.
- Wipe, alongside, resize, free-space, and manual modes pass VM tests.
- Rescue mode remains read-only and diagnoses interrupted installs.

## Suggested work breakdown

1. API contract and frontend state model — 1–2 days
2. React WebUI rewrite — 3–5 days
3. Tauri shell and live-image packaging — 2–4 days
4. Unix-socket service — 3–5 days
5. Rust logic ports and parity tests — 1–2 weeks
6. VM destructive-path acceptance testing — 3–5 days
7. Remove Chromium/Python UI launcher — 1–2 days after parity

## Open decisions

- Whether the Unix-socket service initially wraps Python directly or uses a
  small Rust transport adapter. **Decided:** the native Rust daemon owns the
  Unix socket and proxies to the Python backend on a private local socket until the
  destructive backend parity ports are complete.
- Whether Calamares remains an optional build path or is retired after the
  custom installer reaches parity.
- Whether the first React milestone preserves SSE or moves directly to socket
  events.

## Current progress

- Phase 0 — API contract: complete. See [`installer-api-contract.md`](installer-api-contract.md).
- Phase 1 — React frontend: complete as a compatibility client. Typecheck,
  production build, API decoding, request guards, manual-error handling, and
  contract smoke tests pass. The Rust/Slint client is the production UI.

## Review findings (2026-08-31)

The code-level migration is complete for the current Rust/Slint production
client and native Rust Unix-socket boundary. The Python backend remains
authoritative for destructive execution until future Rust backend ports
independently achieve behavioral parity. The remaining release work is
live-media and disposable-VM validation.

## Prepared continuation

### Next change set — live-media release gate

1. Restore Cargo dependencies and build both Rust binaries with `--locked`.
2. Run the native Rust unit and parity tests.
3. Build the live ISO with the native client packaged.
4. Exercise all install modes in disposable VMs.
5. Test cancellation and power-loss recovery at every durable phase.
6. Complete the credential, socket, privilege-boundary, and rescue-export audit.
7. Remove obsolete launcher paths only after live-media acceptance.

### Following change set — Phase 2 shell scaffold

After Phase 1 closes, create `src/kyth-installer-web/src-tauri/` with:

- an unprivileged, production-asset-only Tauri configuration;
- the minimum capabilities needed to host the application (no shell, generic
  filesystem, process, or disk APIs);
- a narrow bootstrap transport to the existing loopback service, preserving
  the one-use bootstrap and HttpOnly-cookie authentication flow;
- single-instance behavior and clean backend-child shutdown, without copying
  the Hub's system-action commands;
- unit tests for startup argument parsing and an embedded-asset smoke check;
- image packaging additions that build the shell but do not switch the live
  launcher until live-ISO validation succeeds.

Phase 3 should then define the socket protocol from the frozen logical API.
Do not start selective installer logic ports merely because a Rust shell exists.

## Remaining plan

### Phase 2 — Tauri installer shell (in progress)

- Add an unprivileged Tauri shell around the React build. **Done:** `src/kyth-installer-web/src-tauri/` embeds the production assets and exposes only the fixed backend connection/token handoff.
- Embed production assets; do not use a development server or `--no-sandbox`.
- Preserve single-instance/startup routing behavior from System Hub. **Done:** the shell uses the single-instance plugin and the launcher passes bootstrap/session tokens.
- Expose no unrestricted command, filesystem, or disk-writing bridge. **Done:** the shell has one typed connection command and no OS command/file APIs.
- Add WebKitGTK/runtime dependencies to the installer image and replace the Chromium launcher only after live-ISO validation. **Build wiring done;** launcher keeps Chromium as a safe compatibility fallback until the live-ISO gate passes.

### Phase 3 — Unix-socket privileged service

- **Done:** Add a root-owned native Rust service entrypoint and activate the socket transport in the installer launcher.
- **Done:** Replace loopback HTTP access with a root-owned Unix-socket service in the live-image configuration; development keeps the loopback fallback.
- **Done:** Use socket ownership/permissions and peer credentials, retaining the per-run session token as defense in depth.
- Validate the activated service and Tauri client in a built live ISO before removing the compatibility fallback.
- Preserve the frozen logical API, SSE/event semantics, validation, journal, and recovery behavior.
- **Done:** The Rust service validates the token, configured socket peer,
  request size, route allowlist, and loopback backend boundary before
  proxying to Python.

### Phase 4 — Selective Rust migration

The first slice is now implemented: the native Rust transport daemon performs
pure request normalization and install-plan projection before calling the
privileged Python service. The service remains authoritative and repeats all
storage-dependent checks before any mutation. Shared Rust/Python parity
fixtures now cover all five modes and representative rejection branches.
The Rust shell also parses explicit `lsblk` snapshots into typed disk and
partition records; the same fixture is exercised through the Python discovery
functions to pin safety-relevant output.

Port components only after behavioral parity and focused tests exist:

- **Done as a transport preflight:** request and install-plan normalization
  (native Rust daemon; Python server-side validation remains authoritative).
  Shared parity cases live in
  `src/kyth-installer-web/src-tauri/testdata/installer_plan_cases.json`.
- **Done as a runtime query:** the root-owned Rust daemon now performs fixed,
  read-only `lsblk`, `findmnt`, and `blockdev` probes for disk inventory,
  partition inventory, and free-space regions. The Rust parser applies the
  protected-disk policy before returning API-compatible records; Python keeps
  authoritative validation immediately before destructive operations.
- **Done as metadata/validation plus a typed execution boundary:** the
  partition journal model, serialization, and safety checks remain covered,
  while GPT backup/restore, table creation, partition create/delete/flag
  operations, and supported filesystem formatting now go through the
  root-only Rust `kyth-installer-exec` helper. Python still owns target
  validation and journal commit/rollback orchestration. The helper also
  synchronizes completed partition-table backups and their parent directory
  before they can be used as recovery snapshots. Filesystem-specific
  shrinking is now executed by the typed
  Rust helper for NTFS, ext, and Btrfs; Python retains target validation,
  pre-shrink safety guards, stage ordering, error guidance, mount lifecycle
  orchestration, and journal orchestration. Both manual-journal and guided
  NTFS partition-boundary resize use the same typed Rust operation, including
  its fixed interactive confirmation and cancellation-safe child handling.
- **Done as a decoder/classifier:** transaction/recovery state and Rescue guidance; durable writes and recovery actions remain Python-owned.
- **Done as a pure model:** streaming command output framing, bounded failure
  tails, independent I/O/network/absolute timeout decisions, and cooperative
  cancellation; shared Rust/Python fixtures cover framing and failure tails,
  while process execution and privilege boundaries remain Python-owned.
- **Done as a pure state model:** mount registration, release, LIFO cleanup
  ordering, and cleanup-state clearing; mount/unmount syscalls remain
  Python-owned behind the privileged service.
- **Bootc image-write handoff complete at the process boundary:** the typed
  bootc operation is validated and projected by Rust, then
  `kyth-installer-exec` pins and `exec`s `/usr/bin/bootc`. Python still owns
  phase orchestration, power monitoring, transaction reporting, and target
  configuration. The compatibility command builder remains until the full
  storage/configuration executor is ported.
- **Done as a pure decision model:** Rust and Python agree on Secure Boot/MOK
  states and import-result classification; `mokutil`, passwords, and firmware
  interactions remain Python-owned.

### Phase 5 — VM destructive-path acceptance

- Validate wipe, alongside/resize, free-space, and manual modes in disposable VMs.
- Test cancellation during every long-running phase.
- Test interrupted partitioning, filesystem resize, image deployment, final configuration, and reboot recovery.
- Verify rescue mode stays read-only and produces support-safe exports.

### Phase 6 — Live-image integration and parity gate

- Build and typecheck the React/Tauri application in the image pipeline.
- Start the shell from a built live ISO without a development server.
- Verify authentication, asset embedding, single-instance behavior, and all installer workflows on live media.
- Confirm passwords never appear in URLs, logs, process arguments, persistent state, telemetry, or rescue exports.

### Phase 7 — Launcher retirement

- Switch the live image to the validated Tauri launcher.
- Keep the Python backend behind the privileged-service compatibility adapter until every subsystem has parity coverage.
- Remove the Chromium/Python UI launcher only after all safety gates pass.
- Reassess whether Calamares remains an optional fallback or can be retired.

## Next session starting point

Begin with the Phase 1 parity change set above. The first bounded slice is to
add the frontend test harness, extract/test install-mode request selection, and
fix the missing `target_partition`, `resize_partition`, free-region, and
`confirm_current` values. Do not create the Tauri shell until this slice and the
remaining Phase 1 gates pass.
