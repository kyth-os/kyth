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
python3 - <<'PY'
import ast
import subprocess
from pathlib import Path

tracked = subprocess.check_output(["git", "ls-files", "-z"]).decode().split("\0")
files = []
for name in filter(None, tracked):
    path = Path(name)
    if path.suffix == ".py":
        files.append(path)
        continue
    try:
        with path.open(encoding="utf-8") as stream:
            first_line = stream.readline()
    except (OSError, UnicodeDecodeError):
        continue
    if first_line.startswith("#!") and "python" in first_line.lower():
        files.append(path)

for path in files:
    name = path.as_posix()
    ast.parse(Path(name).read_text(encoding="utf-8"), filename=name)
print(f"Checked {len(files)} Python files")
PY

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
python3 - <<'PY'
import re
import subprocess
from pathlib import Path

patterns = {
    "private key block": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "GitHub token": re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9_]{36,}\b"),
    "GitHub fine-grained token": re.compile(r"\bgithub_pat_[A-Za-z0-9_]{80,}\b"),
    "AWS access key": re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    "Slack token": re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b"),
}
binary_suffixes = {".cer", ".png", ".jpg", ".jpeg", ".webp", ".ico"}
files = subprocess.check_output(["git", "ls-files"], text=True).splitlines()
findings = []
for name in files:
    path = Path(name)
    if path.suffix.lower() in binary_suffixes:
        continue
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        continue
    for label, pattern in patterns.items():
        if pattern.search(text):
            findings.append(f"{name}: matched {label}")
if findings:
    print("Potential committed secrets found:")
    print("\n".join(findings))
    raise SystemExit(1)
print(f"Checked {len(files)} tracked files for high-confidence secret patterns")
PY

echo "==> Python unit tests"
python3 -m unittest discover -s tests

echo "==> Structured configuration"
while IFS= read -r -d '' file; do
	jq empty "${file}"
done < <(git ls-files -z '*.json')
python3 - <<'PY'
import subprocess
import tomllib
from pathlib import Path

files = subprocess.check_output(["git", "ls-files", "*.toml"], text=True).splitlines()
for name in files:
    with Path(name).open("rb") as stream:
        tomllib.load(stream)
print(f"Checked {len(files)} TOML files")
PY

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
	just --justfile "${file}" --list >/dev/null
done < <(git ls-files -z '*.just')

echo "==> Validation passed"
