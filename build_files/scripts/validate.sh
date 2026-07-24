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
python3 -m unittest discover -s tests

echo "==> Structured configuration"
while IFS= read -r -d '' file; do
	[[ -f "${file}" ]] || continue
	jq empty "${file}"
done < <(git ls-files -z '*.json')
python3 build_files/scripts/validate-toml-syntax.py

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
