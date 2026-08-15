import "_vars.just"
import "build.just"
import "vm.just"
import "_internal.just"

alias build-vm := build-qcow2
alias run-vm := run-vm-qcow2

[private]
default:
    @just --list

# Check Just Syntax
[group('Just')]
check:
    #!/usr/bin/bash
    find . -type f -name "*.just" | while read -r file; do
    	echo "Checking syntax: $file"
    	just --unstable --fmt --check -f $file
    done
    echo "Checking syntax: Justfile"
    just --unstable --fmt --check -f Justfile

# Check Dockerfile frontend/build rules without requiring the local kyth-base image.
[group('Build')]
check-dockerfile check_base_image=default_base_image:
    #!/usr/bin/env bash
    set -euo pipefail
    if ! id -nG | grep -qw docker; then
        exec sg docker -c "just check-dockerfile '{{ check_base_image }}'"
    fi
    docker buildx build --check \
        --build-arg BASE_IMAGE={{ check_base_image }} \
        .

# Run Python unit tests.
[group('Quality')]
test:
    PYTHONPATH=build_files/kyth_shared:build_files/kyth-welcome:build_files/kyth-installer python3 -m unittest discover -s tests -b

# Verify codecs/drivers are baked (Nobara-style one-click, no post-install dnf)
[group('Quality')]
verify-codecs image="localhost/kyth:latest":
    #!/usr/bin/env bash
    set -euo pipefail
    for pkg in gstreamer1-plugins-bad-freeworld gstreamer1-plugins-ugly gstreamer1-libav gstreamer1-vaapi; do
        podman run --rm {{ image }} rpm -q $pkg >/dev/null && echo "OK $pkg" || (echo "MISSING $pkg" >&2; exit 1)
    done
    echo "Codecs baked — no post-install dnf needed"

# Run Python unit tests with a statement coverage report.
[group('Quality')]
test-coverage:
    ./build_files/scripts/run-quality.sh
    echo ""
    echo "HTML report: coverage-html/index.html"

# Check maintainability/optimization budgets tracked in source control.
[group('Quality')]
check-optimization:
    python3 build_files/scripts/optimization-report.py --check

# Print source metrics; pass runtime=1 on a representative installed system.
[group('Quality')]
optimization-report runtime="0":
    #!/usr/bin/env bash
    set -euo pipefail
    args=()
    if [[ "{{ runtime }}" == "1" ]]; then args+=(--runtime); fi
    python3 build_files/scripts/optimization-report.py "${args[@]}"

# Create/update the local pinned quality-tool environment.
[group('Quality')]
setup-quality:
    python3 -m venv .venv-quality
    .venv-quality/bin/python -m pip install --disable-pip-version-check -r requirements-quality.txt
    .venv-quality/bin/coverage --version
    .venv-quality/bin/ruff --version

# Run the complete validation suite used by GitHub Actions and pre-push.
[group('Quality')]
validate:
    ./build_files/scripts/validate.sh

# Run Validation plus changed-file Codacy and pinned CodeQL security checks.
[group('Quality')]
ci-preflight:
    ./build_files/scripts/ci-preflight.sh

# Fix Just Syntax
[group('Just')]
fix:
    #!/usr/bin/bash
    find . -type f -name "*.just" | while read -r file; do
    	echo "Checking syntax: $file"
    	just --unstable --fmt -f $file
    done
    echo "Checking syntax: Justfile"
    just --unstable --fmt -f Justfile || { exit 1; }

# Clean local build temp dirs and fix output/ ownership.
[group('Utility')]
clean:
    #!/usr/bin/bash
    set -eoux pipefail
    rm -rf _build* *_build*
    rm -f previous.manifest.json
    if [[ -d output ]]; then
        sudo chown -R "$(id -u):$(id -g)" output/
    fi

# Sudo-clean: run 'clean' with sudo if needed
[group('Utility')]
[private]
sudo-clean:
    just sudoif just clean

# Show a disk-usage summary: Docker images, build cache, and output/ ISOs
[group('Utility')]
disk-usage:
    #!/usr/bin/env bash
    set -euo pipefail
    echo "── Docker ────────────────────────────────────────────────────────────────"
    docker system df
    echo ""
    echo "── Output ISOs ───────────────────────────────────────────────────────────"
    just _list-output-images
    echo ""
    echo "── /var/tmp kyth-live build dirs ─────────────────────────────────────────"
    find /var/tmp -maxdepth 1 \( -name "kyth-live.*" -o -name "kyth-titanoboa.*" \) -exec du -sh {} \; 2>/dev/null || echo "(none)"

# Set up a Kali Linux security toolbox via the shipped KythOS ujust recipe.
[group('Utility')]
setup-kali-box tools="headless":
    #!/usr/bin/env bash
    set -euo pipefail
    exec just --justfile build_files/just/kyth.just setup-kali-box "{{ tools }}"

# Export Kali Linux GUI apps via the shipped KythOS ujust recipe.
[group('Utility')]
export-kali-apps:
    #!/usr/bin/env bash
    set -euo pipefail
    exec just --justfile build_files/just/kyth.just export-kali-apps

# Install tracked git hooks for validation and commit message helpers.
[group('Utility')]
install-git-hooks:
    #!/usr/bin/env bash
    set -euo pipefail
    git config core.hooksPath .githooks
    chmod +x .githooks/pre-commit .githooks/pre-push .githooks/prepare-commit-msg build_files/scripts/install-validation-tools.sh build_files/scripts/validate.sh build_files/scripts/run-quality.sh build_files/scripts/ci-preflight.sh
    echo "Git hooks installed via core.hooksPath=.githooks"

# Remove old output ISOs — keeps only the current live ISO and current BIB ISO.
[group('Utility')]
clean-output:
    #!/usr/bin/env bash
    set -euo pipefail
    echo "Cleaning stale output artefacts..."
    just _clean-output-artefacts
    echo "Remaining output files:"
    just _list-output-images

# Prune Docker build cache and dangling (unreferenced) image layers.
[group('Utility')]
clean-docker:
    #!/usr/bin/env bash
    set -euo pipefail
    echo "Pruning Docker build cache and dangling image layers..."
    just _prune-docker-cache
    echo ""
    docker system df

# Reclaim space specifically for live ISO dev loops.
[group('Utility')]
prune-live-dev:
    #!/usr/bin/env bash
    set -euo pipefail

    echo "── Removing stale kyth-live images ──────────────────────────────────────"
    docker images \
        | awk 'NR>1 {print $1":"$2}' \
        | grep '^kyth-live:' \
        | xargs -r docker rmi -f || true

    echo ""
    echo "── Pruning Docker cache/volumes ──────────────────────────────────────────"
    docker builder prune -af || true
    docker image prune -af || true
    docker volume prune -f || true

    echo ""
    echo "── Removing stale VM/build temp artefacts ───────────────────────────────"
    find /tmp -maxdepth 1 -type f -name 'kyth-live-test.qcow2' -delete || true
    find /var/tmp -maxdepth 2 -type f -name 'kyth-live-test.qcow2' -delete || true
    find /tmp -maxdepth 1 -type d -name 'kyth-vm-share-*' -exec rm -rf {} + || true
    just _clean-vartmp-builddirs

    echo ""
    echo "── Post-cleanup summary ───────────────────────────────────────────────────"
    df -h /tmp /var || true
    docker system df || true

# Full local cleanup: build temps + stale outputs + Docker cache.
[group('Utility')]
clean-all: clean clean-output clean-docker

# Nuclear purge: reclaim maximum disk space.
[group('Utility')]
purge:
    #!/usr/bin/env bash
    set -euo pipefail

    echo "── Stale _build* temp dirs in project root ───────────────────────────────"
    shopt -s nullglob
    build_dirs=( _build* )
    if [[ ${#build_dirs[@]} -gt 0 ]]; then
        sudo rm -rf "${build_dirs[@]}"
        printf '  removed: %s\n' "${build_dirs[@]}"
    else
        echo "  (none)"
    fi

    echo ""
    echo "── /var/tmp kyth-live.* / kyth-titanoboa.* build dirs ───────────────────"
    just _clean-vartmp-builddirs
    echo "  Done"

    echo ""
    echo "── Old output artefacts (previous-built-iso, archive, manifest backups) ──"
    just _clean-output-artefacts
    echo "  Done"

    echo ""
    echo "── Docker build cache and dangling image layers ──────────────────────────"
    just _prune-docker-cache

    echo ""
    echo "── Podman dangling image layers ──────────────────────────────────────────"
    if command -v podman &>/dev/null; then
        podman image prune -f
    else
        echo "  (podman not found)"
    fi

    echo ""
    echo "── Result ────────────────────────────────────────────────────────────────"
    df -h "$(pwd)"

# Runs shell check on all Bash scripts
[group('Quality')]
lint:
    #!/usr/bin/env bash
    set -eoux pipefail
    if ! command -v shellcheck &> /dev/null; then
        echo "shellcheck could not be found. Please install it."
        exit 1
    fi
    /usr/bin/find . -iname "*.sh" -type f -exec shellcheck "{}" ';'

# Runs shfmt on all Bash scripts
[group('Quality')]
format:
    #!/usr/bin/env bash
    set -eoux pipefail
    if ! command -v shfmt &> /dev/null; then
        echo "shfmt could not be found. Please install it."
        exit 1
    fi
    /usr/bin/find . -iname "*.sh" -type f -exec shfmt --write "{}" ';'

# Set up a local venv to run System Hub outside the image (handles read-only $HOME overlay).
[group('Utility')]
setup-hub:
    #!/usr/bin/env bash
    set -euo pipefail
    python3 -m venv .venv
    .venv/bin/pip install --disable-pip-version-check PySide6
    .venv/bin/pip install --disable-pip-version-check -e build_files/kyth_shared -e build_files/kyth-welcome
    echo "Hub venv ready: .venv/bin/kyth-welcome"

# Run System Hub locally from the checkout (uses .venv if present).
[group('Utility')]
run-hub *args:
    #!/usr/bin/env bash
    set -euo pipefail
    if [[ -x .venv/bin/kyth-welcome ]]; then
        exec .venv/bin/kyth-welcome {{ args }}
    fi
    if /usr/bin/python3 -c "import PySide6" 2>/dev/null || /usr/bin/python3 -c "import PyQt6" 2>/dev/null; then
        exec env PYTHONPATH=build_files/kyth_shared:build_files/kyth-welcome /usr/bin/python3 build_files/kyth-welcome/kyth-welcome {{ args }}
    fi
    echo "No Qt binding found. Run: just setup-hub" >&2
    exit 1

# Health like cachy-doctor (probe + zram/btrfs/scx); no daemon.
[group('Utility')]
doctor:
    PYTHONPATH=build_files/kyth_shared python3 -m kyth_shared.doctor

# COPR/AUR-style opt-in (Endeavour-like vanilla base).
[group('Utility')]
enable-copr repo:
    #!/usr/bin/env bash
    set -euo pipefail
    echo "This enables a COPR repo on an installed system (opt-in):"
    echo "  sudo dnf5 copr enable {{ repo }}"
    echo "Run above on the host; base stays vanilla."

# Preview the installer UI in your browser (no disk changes — safe for dev)
[group('Utility')]
preview-installer:
    #!/usr/bin/env python3
    import sys, threading, time
    sys.path.insert(0, "build_files/kyth-installer")
    from kyth_installer.server import Handler, _Server
    server = _Server(("127.0.0.1", 7777), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print("Installer UI → http://127.0.0.1:7777  (Ctrl-C to stop)")
    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        pass
