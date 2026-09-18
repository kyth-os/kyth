#!/usr/bin/env bash
set -euo pipefail

repo_root="$(git rev-parse --show-toplevel)"
# shellcheck source=lib/desktop-throttle.sh disable=SC1091
source "${repo_root}/build_files/scripts/lib/desktop-throttle.sh"
kyth_deprioritize_on_desktop "$@"

cd "${repo_root}"

if [[ -x /usr/bin/kyth-hardware-policy ]]; then
	hardware_policy_cmd=(/usr/bin/kyth-hardware-policy)
elif [[ -x src/kyth-shared-rs/target/release/kyth-hardware-policy ]]; then
	hardware_policy_cmd=(src/kyth-shared-rs/target/release/kyth-hardware-policy)
elif [[ -x src/kyth-shared-rs/target/debug/kyth-hardware-policy ]]; then
	hardware_policy_cmd=(src/kyth-shared-rs/target/debug/kyth-hardware-policy)
else
	hardware_policy_cmd=(cargo run --quiet --manifest-path src/kyth-shared-rs/Cargo.toml --bin kyth-hardware-policy --)
fi

tool_bin="$(./build_files/scripts/install-validation-tools.sh | tail -n 1)"
export PATH="${tool_bin}:${PATH}"

echo "==> GitHub Actions workflows"
actionlint -color -shellcheck=""
zizmor --persona auditor --min-severity medium --no-online-audits .github/workflows

echo "==> Container build files"
hadolint --failure-threshold error \
	Dockerfile \
	build_base/Dockerfile \
	build_base/Containerfile.docker-overlay \
	installer/Containerfile

echo "==> Shell scripts"
shell_files=()
while IFS= read -r -d '' file; do
	[[ -f "${file}" ]] || continue
	mime_type="$(file --brief --mime-type "${file}")"
	if [[ "${mime_type}" == "text/x-shellscript" ]]; then
		shell_files+=("${file}")
	fi
done < <(git ls-files -z)
if ((${#shell_files[@]} == 0)); then
	echo "No shell scripts found" >&2
	exit 1
fi
shellcheck --severity=warning "${shell_files[@]}"
for file in "${shell_files[@]}"; do
	bash -n "${file}"
done

echo "==> Python syntax"
python3 build_files/scripts/validate-python-syntax.py

echo "==> Optimization budgets"
python3 build_files/scripts/optimization-report.py --check

echo "==> Gaming hash gate"
bash build_files/scripts/hash-gaming-versions.sh

echo "==> Perf gate (10% ledger, probe collection duration)"
if [[ "${KYTH_PERF_GATE_ADVISORY:-0}" == "1" ]]; then
	if ! PYTHONPATH=build_files/kyth_shared python3 build_files/scripts/check-perf-gate.py; then
		echo "warning: perf gate regression is advisory in this local validation context" >&2
	fi
else
	PYTHONPATH=build_files/kyth_shared python3 build_files/scripts/check-perf-gate.py
fi

echo "==> Sysconfig hash gate (must stay unset locally, pinned in CI)"
if grep -qE '^ARG SYSCONFIG_HASH=unset' Dockerfile && grep -qE '^ARG RPM_SET_HASH=unset' Dockerfile && grep -qE '^ARG GAMING_VERSIONS_HASH=unset' Dockerfile; then echo "hash ARGs unset locally — ok"; else echo "hash ARGs must be unset locally (pinned only in CI)" >&2; exit 1; fi

echo "==> JavaScript syntax"
js_files=()
while IFS= read -r -d '' file; do
	js_files+=("${file}")
done < <(git ls-files -z '*.js')
for file in "${js_files[@]}"; do
	node --check "${file}"
done
echo "Checked ${#js_files[@]} JavaScript files"

echo "==> Rust formatting"
if ! command -v cargo >/dev/null 2>&1; then
	echo "cargo is required for the Rust formatting gate" >&2
	exit 1
fi
while IFS= read -r -d '' manifest; do
	cargo fmt --manifest-path "${manifest}" --all -- --check
done < <(git ls-files -z '*Cargo.toml')

echo "==> Committed-secret patterns"
python3 build_files/scripts/check-committed-secrets.py

echo "==> Runtime migration inventory and frontend boundaries"
python3 build_files/scripts/check-runtime-migration-inventory.py

# --fast skips the heavy 600s unittest discover; it is strictly opt-in via
# the --fast flag. There is deliberately no live-desktop autodetection:
# implicit behavior that depends on which session happens to run the suite
# made local and CI runs diverge. The full suite is CI-gated
# (validation.yml); force the heavy path locally with --full or
# KYTH_FORCE_FULL_VALIDATION=1. `pre-push` passes --fast/--full explicitly.
validate_fast=0
validate_force_full=0
for _arg in "$@"; do
    case "${_arg}" in
        --fast) validate_fast=1 ;;
        --full) validate_force_full=1 ;;
    esac
done
if [[ -n "${KYTH_FORCE_FULL_VALIDATION:-}" ]]; then
    validate_force_full=1
fi
# An explicit full-suite request wins over --fast when both are given.
if [[ ${validate_force_full} -eq 1 ]]; then
    validate_fast=0
fi

echo "==> Python unit tests"
test_home="$(mktemp -d)"
trap 'rm -rf -- "${test_home}"' EXIT
# Keep the runner's installed Rust toolchain visible after HOME is isolated
# for the Python suite. On GitHub-hosted runners `cargo` is a rustup shim; if
# RUSTUP_HOME follows the temporary HOME, Rust tests fail with "no default
# toolchain" even though the workflow configured stable successfully.
rustup_home="${RUSTUP_HOME:-${HOME}/.rustup}"
cargo_home="${CARGO_HOME:-${HOME}/.cargo}"
export HOME="${test_home}/home"
export RUSTUP_HOME="${rustup_home}"
export CARGO_HOME="${cargo_home}"
export XDG_CACHE_HOME="${test_home}/cache"
export XDG_CONFIG_HOME="${test_home}/config"
export XDG_DATA_HOME="${test_home}/data"
export XDG_STATE_HOME="${test_home}/state"
mkdir -p "${HOME}" "${XDG_CACHE_HOME}" "${XDG_CONFIG_HOME}" "${XDG_DATA_HOME}" "${XDG_STATE_HOME}"
if [[ ${validate_fast} -eq 1 ]]; then
	echo "==> Python unit tests SKIPPED (--fast) — CI validation.yml gates the full suite"
else
	# Guard with timeout so CI doesn't hang on slow network/hardware probes; --foreground
	# lets the suite read from TTY and avoids timeout's process-group SIGTERM
	# killing the caller's session. 600s matches CI's 10m job timeout.
  PYTHONPATH=build_files/kyth_shared:build_files/kyth-installer timeout --foreground 600 python3 -m unittest discover -s tests -b
fi

echo "==> Structured configuration"
while IFS= read -r -d '' file; do
	[[ -f "${file}" ]] || continue
	jq empty "${file}"
done < <(git ls-files -z '*.json')
python3 build_files/scripts/validate-toml-syntax.py
"${hardware_policy_cmd[@]}" \
	--policy build_files/config/hardware-profiles.toml validate --fail-expired
hardware_matrix="${test_home}/hardware-support-matrix.md"
"${hardware_policy_cmd[@]}" \
	--policy build_files/config/hardware-profiles.toml matrix --output "${hardware_matrix}"
if ! cmp --silent "${hardware_matrix}" docs/hardware-support-matrix.md; then
	echo "Hardware support matrix is stale — docs/hardware-support-matrix.md" >&2
	echo "diff vs generated (build_files/config/hardware-profiles.toml):" >&2
	diff -u docs/hardware-support-matrix.md "${hardware_matrix}" >&2 || true
	echo "Fix: kyth-hardware-policy --policy build_files/config/hardware-profiles.toml matrix --output docs/hardware-support-matrix.md" >&2
	exit 1
fi

echo "==> installer/iso.yaml schema (Titanoboa/bootc-image-builder contract)"
python3 - <<'EOF'
import re
import sys
from pathlib import Path

path = Path("installer/iso.yaml")
if not path.is_file():
    print("ERROR: installer/iso.yaml is missing", file=sys.stderr)
    sys.exit(1)
lines = path.read_text(encoding="utf-8").splitlines()


def fail(msg):
    print(f"ERROR: installer/iso.yaml: {msg}", file=sys.stderr)
    sys.exit(1)


stripped = [ln for ln in lines if ln.strip() and not ln.strip().startswith("#")]
m = re.match(r'^label:\s*"?([^"\s][^"]*)"?\s*$', stripped[0] if stripped else "")
if not m:
    fail("first entry must be a non-empty 'label:'")
label = m.group(1).strip()
if not re.match(r"^[A-Za-z0-9][A-Za-z0-9._-]*$", label):
    fail(f"label {label!r} must match ^[A-Za-z0-9][A-Za-z0-9._-]*$")

text = "\n".join(lines)
m = re.search(r"^grub2:\s*$", text, re.M)
if not m:
    fail("missing 'grub2:' section")
m = re.search(r"^\s+timeout:\s*(\d+)\s*$", text, re.M)
if not m:
    fail("grub2.timeout must be a non-negative integer")
if int(m.group(1)) < 0:
    fail("grub2.timeout must be >= 0")

# Entries are "- name:" list items; each must carry linux: + initrd:.
names = re.findall(r"^\s*-\s*name:\s*\"?([^\"]*?)\"?\s*$", text, re.M)
if not names or any(not n.strip() for n in names):
    fail("grub2.entries must be a non-empty list with a non-empty name per entry")
blocks = re.split(r"^\s*-\s*name:", text, flags=re.M)[1:]
if len(blocks) != len(names):
    fail("could not parse grub2.entries")
for name, block in zip(names, blocks):
    # Block runs until the next list item at the same level or end of entries.
    body = block.split("\n- ", 1)[0]
    ml = re.search(r"^\s*linux:\s*\"(.*)\"\s*$", body, re.M)
    mi = re.search(r"^\s*initrd:\s*\"?([^\"]\S*)\"?\s*$", body, re.M)
    if not ml or not ml.group(1).strip():
        fail(f"entry {name.strip()!r} is missing a non-empty 'linux:' cmdline")
    if not mi or not mi.group(1).strip().startswith("/"):
        fail(f"entry {name.strip()!r} is missing an absolute 'initrd:' path")
    if f"root=live:CDLABEL={label}" not in ml.group(1):
        fail(f"entry {name.strip()!r} linux: must contain 'root=live:CDLABEL={label}'")
print(f"iso.yaml ok: label={label} entries={len(names)}")
EOF

echo "==> systemd units"
output="$(systemd-analyze verify build_files/*.service build_files/*.timer 2>&1 || true)"
printf '%s\n' "${output}"
unexpected="$(printf '%s\n' "${output}" |
	grep -Ev \
		-e '^[^:]+: Command .+ is not executable: No such file or directory$' \
		-e '^Failed to turn off SO_PASSRIGHTS on user lookup socket, ignoring: Operation not permitted$' \
		-e '^Failed to enable SO_PASSCRED on handoff timestamp socket(, ignoring)?: Operation not permitted$' \
		-e '^ERROR: ld\.so: object .* cannot be preloaded .* ignored\.$' \
		-e '^Configuration file .* is marked world-writable\. Please remove world writability permission bits\. Proceeding anyway\.$' \
		-e '^(local-fs(-pre)?\.target|systemd-(tmpfiles-setup-dev|sysusers)\.service|kyth-system-accounts\.service): .*' ||
	true)"
if [[ -n "${unexpected}" ]]; then
	printf 'Unexpected systemd verification errors:\n%s\n' "${unexpected}" >&2
	exit 1
fi
# Security audits — warn, but also enforce bash -c variable interpolation gate
# Fail only on shell-variable interpolation ($var / ${var}), not static $(cmd) subshells
if grep -rn --include="*.py" 'bash.*-c.*\$[A-Za-z_]' src/kyth_shared src/kyth-installer 2>/dev/null | grep -v "static" | grep -v "test_" | grep -q .; then
	echo "Bash -c variable interpolation (\$var/\${var}) found — use validated python helper instead" >&2
	grep -rn --include="*.py" 'bash.*-c.*\$[A-Za-z_]' src/kyth_shared src/kyth-installer 2>/dev/null | grep -v "static" | head -n 5 >&2
	exit 1
fi
# Non-blocking security audit — warn, don't fail (thresholds are advisory while
# the demonolith is being split). Surfaces hardening regressions early.
if command -v systemd-analyze >/dev/null 2>&1; then
	output_sec="$(systemd-analyze security build_files/kyth-ai-perfd.service build_files/kyth-guardian.service build_files/kyth-sched.service build_files/kyth-sched-arbiter.service build_files/kyth-batteryd.service build_files/kyth-probe.service build_files/kyth-probe-user.service build_files/kyth-update-watcher.service 2>&1 || true)"
	printf '%s\n' "${output_sec}" | grep -E "^(build_files|Overall exposure)" || true
fi
# Supply-chain audit — non-blocking, surfaces cargo/pip advisories
if command -v cargo >/dev/null 2>&1 && [ -f Cargo.lock ]; then
	cargo audit 2>&1 | head -n 30 || true
fi
if command -v pip-audit >/dev/null 2>&1; then
	pip-audit 2>&1 | head -n 30 || true
fi

echo "==> Just recipes"
just --list >/dev/null
while IFS= read -r -d '' file; do
	[[ -f "${file}" ]] || continue
	just --justfile "${file}" --list >/dev/null
done < <(git ls-files -z '*.just')

echo "==> Validation passed"
