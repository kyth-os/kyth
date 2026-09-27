#!/bin/bash
# shellcheck shell=bash
# tunable-dispatcher — install the native dispatcher + 94 aliases.
# Replaces the former Python/bash dispatcher and 94 thin wrappers with one
# Rust binary and symlinks. Preserves symlinks via ln -sf (not cp without -a,
# which would dereference).
#
# Deliberately lives outside build_files/scripts/sysconfig/ and is invoked by
# its own explicit `bash /ctx/scripts/tunable-dispatcher.sh` line in the
# Dockerfile's final RUN block, run once, after every `COPY --from=hub-web-
# builder` instruction. It used to sit at sysconfig/tunable/01-tunable-
# dispatcher.sh, where build_files/scripts/sysconfig-static.sh's generic
# fragment sweep (run_fragments "sysconfig" "bash") picked it up and ran it a
# second time early, before most binaries were copied in. That premature run
# created /usr/bin/kyth-windows-verify as a symlink to kyth-tunable-rs; a
# later `COPY ... /build/kyth-windows-verify /usr/bin/kyth-windows-verify`
# then wrote through that symlink into kyth-tunable-rs's own file content
# (COPY does not unlink an existing destination symlink, it opens and
# truncates whatever the symlink points at), silently corrupting the
# dispatcher binary and shipping images with 0 of the 94 tunable symlinks.
set -euo pipefail

# Install the full mutation-capable Rust dispatcher under both names. The
# direct kyth-tunable name is intentionally native too; there is no Python
# fallback in the supported image.
ln -sfn kyth-tunable-rs /usr/bin/kyth-tunable

# Create compat symlinks for every tunable in the native registry.
mapfile -t tunables < <(/usr/bin/kyth-tunable-rs --list)
mapfile -t native_tunables < <(/usr/bin/kyth-tunable-rs --list-native)
declare -A native_lookup=()
for t in "${native_tunables[@]}"; do
    native_lookup["$t"]=1
done

# Guard against shipping the wrong (or a stale) kyth-tunable-rs binary. The
# loop below only fails on entries present in --list but absent from
# --list-native — if the installed binary can't answer either flag at all
# (wrong binary, predates the tunable dispatcher, --list/--list-native
# renamed, etc.), both mapfiles come back empty and that loop passes
# vacuously with zero symlinks created. Cross-check the registry's own
# declared size (source of truth: build_files/config/tunables.toml, bind-
# mounted at /ctx/config) so a build can't silently ship a dispatcher that
# answers nothing for 94 tunables.
expected_count="$(grep -c '^\[tunables\.' /ctx/config/tunables.toml)"
if (( ${#tunables[@]} != expected_count )); then
    echo "tunable-dispatcher: /usr/bin/kyth-tunable-rs --list returned ${#tunables[@]} entries, expected ${expected_count} from tunables.toml — wrong or stale binary installed at /usr/bin/kyth-tunable-rs?" >&2
    exit 1
fi

for t in "${tunables[@]}"; do
    if [[ ! ${native_lookup[$t]+yes} ]]; then
        echo "tunable-dispatcher: registry entry lacks a Rust implementation: ${t}" >&2
        exit 1
    fi
    ln -sf kyth-tunable-rs "/usr/bin/kyth-${t}"
done

echo "tunable-dispatcher: installed kyth-tunable + ${#tunables[@]} symlinks (${#native_tunables[@]} native)"
