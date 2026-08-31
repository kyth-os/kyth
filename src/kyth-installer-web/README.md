# KythOS installer web frontend

The primary installer client is the Tauri/React shell in this directory. It
uses the shared Kyth Hub visual system while keeping disk and boot operations
behind the authenticated, fixed-route backend. The native Slint client lives
in `src-tauri/src/native_main.rs` and `src-tauri/ui/installer.slint` as an
explicit recovery path selected with `KYTH_USE_NATIVE_INSTALLER=1`.

Both clients support the same initial request flow, authenticated installer
SSE stream, and fixed-route storage operations. The launcher falls back to the
native binary if the Tauri shell is unavailable, then to the legacy Chromium
frontend on older images.

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
