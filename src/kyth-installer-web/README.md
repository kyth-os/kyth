# KythOS installer web frontend

The native migration is being built in `src-tauri/src/native_main.rs` and
`src-tauri/ui/installer.slint`. `kyth-installer-native` now owns the initial
request flow: disk selection, install mode/kernel choices, account fields,
confirmation gates, guided partition/free-space selection, and fixed-route
start/cancel/reboot/rescue calls. Native install requests now also attach to
the authenticated installer SSE stream for live logs, phases, progress, and
terminal state. The existing Tauri flow remains the compatibility path until
manual partitioning and service-backed configuration choice lists have native
parity.

Phase 1 React/TypeScript frontend for the installer migration. It consumes the frozen API in [`docs/installer-api-contract.md`](../../docs/installer-api-contract.md) and intentionally leaves the Python HTTP/SSE backend and legacy WebUI untouched.

Run locally with the Python installer service available on `127.0.0.1:8642`:

```bash
npm install
npm run dev
```

The package is embedded in the unprivileged `kyth-installer-shell` Tauri
window during Phase 2. The shell keeps the Python installer backend as the
compatibility service on `127.0.0.1:7777`; it has no disk, filesystem, or
generic command bridge. Phase 3 also includes an opt-in fixed Unix-socket
transport with typed native request/event commands; loopback remains the image
default until live-media validation. Chromium remains the launcher fallback on
images that do not yet contain the shell.

For local development, run the backend on port 7777 and use:

```bash
npm install
npm run tauri:dev
```
