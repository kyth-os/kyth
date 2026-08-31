#!/usr/bin/env bash
# Build/typecheck gate for the KythOS installer shells
# (src/kyth-installer-web). Mirrors check-hub-web-shell.sh's role for the
# installer frontend: a single entry point `just check-installer-shell` and
# CI both call, so the two never drift. Unlike the Hub, this crate is not
# wired into the Dockerfile yet — this script is the only thing standing
# between it and silently bit-rotting against kyth-shared-rs changes.
#
# Builds the React frontend first (Tauri's build.rs reads tauri.conf.json's
# frontendDist at compile time, so `dist/` needs to exist), runs the
# kyth-shared crate's real unit tests (it's a plain library — no
# GPU/display needed to test it, unlike the shell binaries), then links both
# Tauri shells and inspects the compatibility binary it produced. CI has no
# GPU/display to actually launch the app against, but the one
# launch-blocking property that *is* checkable without a display is whether
# the frontend got embedded at all — see the assertion at the bottom.
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
installer_web="$repo_root/src/kyth-installer-web"
kyth_shared_rs="$repo_root/src/kyth-shared-rs"

echo "== kyth-installer-web: npm ci =="
(cd "$installer_web" && npm ci)

echo "== kyth-installer-web: frontend build =="
(cd "$installer_web" && npm run build)

echo "== kyth-shared-rs: cargo test =="
(cd "$kyth_shared_rs" && cargo test --locked)

echo "== kyth-installer-web/src-tauri: cargo build =="
# A full build, not `cargo check`: the assertion below needs a real binary to
# look inside, matching check-hub-web-shell.sh's reasoning for the Hub.
# Debug profile is enough — the dev-vs-production choice rides on a cargo
# *feature*, not on the profile.
(cd "$installer_web/src-tauri" && cargo build --locked)
(cd "$installer_web/src-tauri" && cargo build --locked --bin kyth-installer-native)

native_bin="$installer_web/src-tauri/target/debug/kyth-installer-native"
if [[ ! -x "$native_bin" ]]; then
    echo "FAIL: native Slint installer binary was not produced." >&2
    exit 1
fi
echo "   native Slint installer binary linked at $native_bin"

echo "== kyth-installer-shell: assert the frontend is embedded =="
# Same tauri-codegen dev-vs-production trap as the Hub shell: a build missing
# the `custom-protocol` feature links fine and opens on
# "Could not connect to localhost" on any machine not running `vite`.
# Grepping for the devUrl would not catch it, so assert on the embedded
# asset keys instead — see check-hub-web-shell.sh for the full rationale.
shell_bin="$installer_web/src-tauri/target/debug/kyth-installer-shell"

# Collect first and require a non-empty list: an empty dist/ (or a failed cd,
# which set -e cannot catch inside a process substitution) would otherwise run
# the loop zero times and report success against a binary with nothing in it.
mapfile -t installer_assets < <(cd "$installer_web/dist" && find assets -type f \( -name '*.js' -o -name '*.css' \))
if [[ "${#installer_assets[@]}" -eq 0 ]]; then
    echo "FAIL: no dist/assets/*.{js,css} to assert on — did the frontend build run?" >&2
    exit 1
fi

missing=0
for asset in "${installer_assets[@]}"; do
    if ! grep -aqF "$asset" "$shell_bin"; then
        echo "  missing from binary: $asset" >&2
        missing=1
    fi
done

if [[ "$missing" -ne 0 ]]; then
    cat >&2 <<'EOF'
FAIL: kyth-installer-shell did not embed the built frontend.
      Almost certainly the `custom-protocol` feature is off — check that
      src/kyth-installer-web/src-tauri/Cargo.toml still declares it as a
      default feature, and that nothing passes --no-default-features.
      Failing that, the embedded asset key form may have changed: see
      tauri-codegen's AssetKey::from, which is what makes these greppable
      as plain strings.
EOF
    exit 1
fi
echo "   frontend assets embedded in $shell_bin"

# node_modules is committed as a symlink to ../kyth-hub-web/node_modules
# (the two React apps share one install to save local disk) but `npm ci`
# above always deletes the path first and reinstalls a real directory in
# its place — it has no notion of preserving a symlink. That materialized
# copy is exactly what a from-scratch CI checkout needs (the symlink
# target doesn't exist there yet), but on a dev machine that already had
# both node_modules populated it silently breaks the shared-install setup
# git tracks. Everything above already ran against whatever was on disk at
# the time, so restoring the tracked symlink now — after the build, not
# before — is safe: a no-op in CI's disposable checkout, and a no-op for
# git status on a dev machine.
if [[ -n "$(cd "$repo_root" && git ls-tree HEAD -- src/kyth-installer-web/node_modules 2>/dev/null)" ]] \
    && [[ ! -L "$installer_web/node_modules" ]]; then
    echo "   restoring node_modules symlink (npm ci replaced it with a real directory)"
    (cd "$repo_root" && git checkout -- src/kyth-installer-web/node_modules)
fi
