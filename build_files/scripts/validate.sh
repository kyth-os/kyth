#!/usr/bin/env bash
set -euo pipefail

repo_root="$(git rev-parse --show-toplevel)"
cd "${repo_root}"

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

echo "==> RPM lock hash gate"
bash build_files/scripts/hash-rpm-lock.sh

echo "==> Perf gate (5% ledger, stale p95 check)"
PYTHONPATH=build_files/kyth_shared python3 -c "from kyth_shared.perf_gate import check_perf_gate; r=check_perf_gate(current_ms=None); assert r.get('pass') is True, r; print(f\"perf gate ok threshold={r.get('threshold')}%\")"

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

echo "==> Committed-secret patterns"
python3 build_files/scripts/check-committed-secrets.py

echo "==> Python unit tests"
test_home="$(mktemp -d)"
trap 'rm -rf -- "${test_home}"' EXIT
export HOME="${test_home}/home"
export XDG_CACHE_HOME="${test_home}/cache"
export XDG_CONFIG_HOME="${test_home}/config"
export XDG_DATA_HOME="${test_home}/data"
export XDG_STATE_HOME="${test_home}/state"
mkdir -p "${HOME}" "${XDG_CACHE_HOME}" "${XDG_CONFIG_HOME}" "${XDG_DATA_HOME}" "${XDG_STATE_HOME}"
python3 -m unittest discover -s tests -b

echo "==> Structured configuration"
while IFS= read -r -d '' file; do
	[[ -f "${file}" ]] || continue
	jq empty "${file}"
done < <(git ls-files -z '*.json')
python3 build_files/scripts/validate-toml-syntax.py
PYTHONPATH=build_files/kyth_shared python3 -m kyth_shared.hardware_policy \
	--policy build_files/config/hardware-profiles.toml validate --fail-expired
hardware_matrix="${test_home}/hardware-support-matrix.md"
PYTHONPATH=build_files/kyth_shared python3 -m kyth_shared.hardware_policy \
	--policy build_files/config/hardware-profiles.toml matrix --output "${hardware_matrix}"
if ! cmp --silent "${hardware_matrix}" docs/hardware-support-matrix.md; then
	echo "Hardware support matrix is stale — docs/hardware-support-matrix.md" >&2
	echo "diff vs generated (build_files/config/hardware-profiles.toml):" >&2
	diff -u docs/hardware-support-matrix.md "${hardware_matrix}" >&2 || true
	echo "Fix: PYTHONPATH=build_files/kyth_shared python3 -m kyth_shared.hardware_policy --policy build_files/config/hardware-profiles.toml matrix --output docs/hardware-support-matrix.md" >&2
	exit 1
fi

echo "==> systemd units"
output="$(systemd-analyze verify build_files/*.service build_files/*.timer 2>&1 || true)"
printf '%s\n' "${output}"
unexpected="$(printf '%s\n' "${output}" |
	grep -Ev \
		-e '^[^:]+: Command .+ is not executable: No such file or directory$' \
		-e '^Failed to turn off SO_PASSRIGHTS on user lookup socket, ignoring: Operation not permitted$' \
		-e '^Failed to enable SO_PASSCRED on handoff timestamp socket(, ignoring)?: Operation not permitted$' \
		-e '^ERROR: ld\.so: object .* cannot be preloaded .* ignored\.$' ||
	true)"
if [[ -n "${unexpected}" ]]; then
	printf 'Unexpected systemd verification errors:\n%s\n' "${unexpected}" >&2
	exit 1
fi

echo "==> Just recipes"
just --list >/dev/null
while IFS= read -r -d '' file; do
	[[ -f "${file}" ]] || continue
	just --justfile "${file}" --list >/dev/null
done < <(git ls-files -z '*.just')

echo "==> Validation passed"
