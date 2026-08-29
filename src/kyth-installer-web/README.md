# KythOS installer web frontend

Phase 1 React/TypeScript frontend for the installer migration. It consumes the frozen API in [`docs/installer-api-contract.md`](../../docs/installer-api-contract.md) and intentionally leaves the Python HTTP/SSE backend and legacy WebUI untouched.

Run locally with the Python installer service available on `127.0.0.1:8642`:

```bash
npm install
npm run dev
```

The package is embedded in the unprivileged `kyth-installer-shell` Tauri
window during Phase 2. The shell keeps the Python installer backend as the
compatibility service on `127.0.0.1:7777`; it has no disk, filesystem, or
generic command bridge. Chromium remains the launcher fallback on images that
do not yet contain the shell.

For local development, run the backend on port 7777 and use:

```bash
npm install
npm run tauri:dev
```
