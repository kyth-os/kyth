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
check-dockerfile check_base_image="ghcr.io/ublue-os/kinoite-main:44":
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
    python3 -m unittest discover -s tests

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
    find output -name "*.iso" -o -name "*.qcow2" -o -name "*.raw" 2>/dev/null \
        | sort | xargs -r du -sh 2>/dev/null || echo "(none)"
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

# Refresh the auto-generated README project snapshot section.
[group('Utility')]
sync-readme:
    #!/usr/bin/env bash
    set -euo pipefail
    ./build_files/scripts/update-readme-snapshot.sh

# Install tracked git hooks for automatic README snapshot and commit message helpers.
[group('Utility')]
install-git-hooks:
    #!/usr/bin/env bash
    set -euo pipefail
    git config core.hooksPath .githooks
    chmod +x .githooks/pre-commit .githooks/pre-push .githooks/prepare-commit-msg build_files/scripts/update-readme-snapshot.sh build_files/scripts/install-validation-tools.sh build_files/scripts/validate.sh build_files/scripts/ci-preflight.sh
    echo "Git hooks installed via core.hooksPath=.githooks"

# Remove old output ISOs — keeps only the current live ISO and current BIB ISO.
[group('Utility')]
clean-output:
    #!/usr/bin/env bash
    set -euo pipefail
    echo "Cleaning stale output artefacts..."
    sudo rm -rf output/previous-built-iso output/archive 2>/dev/null || true
    sudo rm -f  output/manifest-iso.json.bak 2>/dev/null || true
    sudo chown -R "$(id -u):$(id -g)" output/ 2>/dev/null || true
    echo "Remaining output files:"
    find output -name "*.iso" -o -name "*.qcow2" -o -name "*.raw" 2>/dev/null \
        | sort | xargs -r du -sh 2>/dev/null || echo "(none)"

# Prune Docker build cache and dangling (unreferenced) image layers.
[group('Utility')]
clean-docker:
    #!/usr/bin/env bash
    set -euo pipefail
    echo "Pruning Docker build cache..."
    docker builder prune -f
    echo ""
    echo "Pruning dangling image layers..."
    docker image prune -f
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
    sudo find /var/tmp -maxdepth 1 -type d \( -name 'kyth-live.*' -o -name 'kyth-titanoboa.*' \) -exec rm -rf {} + || true

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
    if sudo find /var/tmp -maxdepth 1 \( -name "kyth-live.*" -o -name "kyth-titanoboa.*" \) -print -exec rm -rf {} + 2>/dev/null | grep -q .; then
        echo "  Done"
    else
        echo "  (none)"
    fi

    echo ""
    echo "── Old output artefacts (previous-built-iso, archive, manifest backups) ──"
    sudo rm -rf output/previous-built-iso output/archive 2>/dev/null || true
    sudo rm -f  output/manifest-iso.json.bak 2>/dev/null || true
    sudo chown -R "$(id -u):$(id -g)" output/ 2>/dev/null || true
    echo "  Done"

    echo ""
    echo "── Docker build cache ────────────────────────────────────────────────────"
    docker builder prune -f

    echo ""
    echo "── Docker dangling image layers ──────────────────────────────────────────"
    docker image prune -f

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
