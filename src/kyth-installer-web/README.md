# KythOS installer web frontend

Phase 1 React/TypeScript frontend for the installer migration. It consumes the frozen API in [`docs/installer-api-contract.md`](../../docs/installer-api-contract.md) and intentionally leaves the Python HTTP/SSE backend and legacy WebUI untouched.

Run locally with the Python installer service available on `127.0.0.1:8642`:

```bash
npm install
npm run dev
```

The package is not installed into the live image yet. Image integration and the Tauri shell are Phase 2 work.
