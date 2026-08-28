# Installer Migration Plan

**Status:** Proposed  
**Scope:** Migrate the KythOS installer to the React/Tauri style used by the System Hub.

## Context

The installer already has a web frontend, but it is served by a root-owned Python
HTTP server and displayed in Chromium. The backend owns disk discovery,
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

### 1. React frontend with the existing backend

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
tests.

### 2. Tauri shell

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
  small Rust transport adapter.
- Whether Calamares remains an optional build path or is retired after the
  custom installer reaches parity.
- Whether the first React milestone preserves SSE or moves directly to socket
  events.

## Current progress

- Phase 0 — API contract: complete. See [`installer-api-contract.md`](installer-api-contract.md).
- Phase 1 — React frontend: complete as a standalone package in [`src/kyth-installer-web/`](../src/kyth-installer-web/). Typecheck and production build pass. The Python HTTP/SSE backend and legacy WebUI remain available as the runtime fallback.

## Remaining plan

### Phase 2 — Tauri installer shell

- Add an unprivileged Tauri shell around the React build.
- Embed production assets; do not use a development server or `--no-sandbox`.
- Preserve single-instance/startup routing behavior from System Hub.
- Expose no unrestricted command, filesystem, or disk-writing bridge.
- Add WebKitGTK/runtime dependencies to the installer image and replace the Chromium launcher only after live-ISO validation.

### Phase 3 — Unix-socket privileged service

- Replace loopback HTTP access with a root-owned Unix-socket service.
- Use socket ownership/permissions and peer credentials, retaining the one-time session token as defense in depth.
- Preserve the frozen logical API, SSE/event semantics, validation, journal, and recovery behavior.
- Decide whether the first service wraps Python directly or uses a small Rust transport adapter.

### Phase 4 — Selective Rust migration

Port components only after behavioral parity and focused tests exist:

- request and install-plan validation
- disk and partition discovery
- partition journal and storage guards
- transaction/recovery state
- command runner and cancellation
- mount lifecycle
- bootc installation/configuration
- Secure Boot and MOK handling

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

Begin with Phase 2: inspect the System Hub Tauri shell and create the installer shell/package integration without changing the privileged installer backend.
