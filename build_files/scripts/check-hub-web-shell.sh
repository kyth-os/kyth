#!/usr/bin/env bash
# Build/typecheck gate for the Kyth Hub Tauri shell
# (src/kyth-hub-web). Mirrors validate.sh's role for the rest of the repo:
# a single entry point `just check-hub-shell` and CI both call, so the two
# never drift.
#
# Builds the React frontend first (Tauri's build.rs reads tauri.conf.json's
# frontendDist at compile time, so `dist/` needs to exist), runs the
# kyth-shared crate's real unit tests (it's a plain library — no
# GPU/display needed to test it, unlike the shell binary), then links the
# Tauri shell and inspects the binary it produced. CI has no GPU/display to
# actually launch the real `kyth-hub-shell` binary against (that would need
# Xvfb plus a full WebKitGTK runtime — a separate, larger follow-up, not
# attempted here); what *is* checkable without a display is (1) whether the
# frontend got embedded at all — see the assertion at the bottom — and (2)
# whether every Hub section component constructs without throwing, which
# `npm run test:smoke` below now covers by server-rendering each one
# (`tests/hub-shell-smoke.test.mjs`, via `react-dom/server`).
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
hub_web="$repo_root/src/kyth-hub-web"
kyth_shared_rs="$repo_root/src/kyth-shared-rs"

echo "== kyth-hub-web: npm ci =="
(cd "$hub_web" && npm ci)

echo "== kyth-hub-web: frontend build =="
(cd "$hub_web" && npm run build)

echo "== kyth-hub-web: frontend/Rust contract tests =="
(cd "$hub_web" && npm run test:contracts)

echo "== kyth-hub-web: headless section construction smoke =="
(cd "$hub_web" && npm run test:smoke)

echo "== kyth-shared-rs: cargo test =="
(cd "$kyth_shared_rs" && cargo test --locked)

echo "== kyth-hub-web/src-tauri: cargo test =="
(cd "$hub_web/src-tauri" && cargo test --locked)

echo "== kyth-hub-web/src-tauri: cargo build =="
# A full build, not `cargo check`: the assertion below needs a real binary to
# look inside, and `cargo check` ran green for the whole time a shell that
# could not load its own frontend was shipping to users. Debug profile is
# enough — the dev-vs-production choice rides on a cargo *feature*, not on
# the profile, so it reproduces here at a fraction of the release build's
# LTO cost.
(cd "$hub_web/src-tauri" && cargo build --locked)

echo "== kyth-hub-shell: assert the frontend is embedded =="
# tauri-macros decides dev-vs-production from `dev: cfg!(not(feature =
# "custom-protocol"))`. In a dev context tauri-codegen substitutes an empty
# asset map and the webview loads tauri.conf.json's devUrl instead, so the
# app opens on "Could not connect to localhost: Connection refused" on any
# machine that isn't running `vite`. Grepping for the devUrl would not catch
# it — tauri-codegen tokenizes the whole config into the binary either way —
# so assert on the asset keys, which tauri-codegen emits as plain &str phf
# map keys and which exist only when dist/ was really embedded.
shell_bin="$hub_web/src-tauri/target/debug/kyth-hub-shell"

# Collect first and require a non-empty list: an empty dist/ (or a failed cd,
# which set -e cannot catch inside a process substitution) would otherwise run
# the loop zero times and report success against a binary with nothing in it —
# the same vacuous pass that let `cargo check` stay green through this bug.
mapfile -t hub_assets < <(cd "$hub_web/dist" && find assets -type f \( -name '*.js' -o -name '*.css' \))
if [[ "${#hub_assets[@]}" -eq 0 ]]; then
    echo "FAIL: no dist/assets/*.{js,css} to assert on — did the frontend build run?" >&2
    exit 1
fi

missing=0
for asset in "${hub_assets[@]}"; do
    if ! grep -aqF "$asset" "$shell_bin"; then
        echo "  missing from binary: $asset" >&2
        missing=1
    fi
done

if [[ "$missing" -ne 0 ]]; then
    cat >&2 <<'EOF'
FAIL: kyth-hub-shell did not embed the built frontend.
      Almost certainly the `custom-protocol` feature is off — check that
      src/kyth-hub-web/src-tauri/Cargo.toml still declares it as a default
      feature, and that nothing passes --no-default-features. Failing that,
      the embedded asset key form may have changed: see tauri-codegen's
      AssetKey::from, which is what makes these greppable as plain strings.
EOF
    exit 1
fi
echo "   frontend assets embedded in $shell_bin"
