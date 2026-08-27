#!/usr/bin/env bash
# Build/typecheck gate for the React + Tauri (Rust) Kyth Hub shell
# (src/kyth-hub-web). Mirrors validate.sh's role for the rest of the repo:
# a single entry point `just check-hub-shell` and CI both call, so the two
# never drift.
#
# Builds the React frontend first (Tauri's build.rs reads tauri.conf.json's
# frontendDist at compile time, so `dist/` needs to exist), then compiles
# the Rust shell. `cargo check` only — not `cargo build` — since this is a
# compile-correctness gate, not a release artifact; CI has no GPU/display
# to actually launch the app against anyway (see web_shell.py's prior art
# doc comments for how the GUI side gets exercised instead, via the
# offscreen PySide6 smoke test — this shell doesn't have an offscreen
# equivalent yet).
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
hub_web="$repo_root/src/kyth-hub-web"

echo "== kyth-hub-web: npm ci =="
(cd "$hub_web" && npm ci)

echo "== kyth-hub-web: frontend build =="
(cd "$hub_web" && npm run build)

echo "== kyth-hub-web/src-tauri: cargo check =="
(cd "$hub_web/src-tauri" && cargo check --locked)
