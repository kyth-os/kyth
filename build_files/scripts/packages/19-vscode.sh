#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

# ── VS Code ───────────────────────────────────────────────────────────────────
# Bake VS Code native RPM into the image so it has full access to the local
# filesystem and terminal without the sandboxing constraints of a Flatpak.
# The Microsoft signing key is vendored in-repo (build_files/RPM-GPG-KEY-microsoft,
# fingerprint BC528686B50D79E339D3721CEB3E94ADBE1229CF) and bind-mounted at /ctx,
# so the build has no DNS-dependent rpm --import call.
install -Dm 0644 /ctx/RPM-GPG-KEY-microsoft /etc/pki/rpm-gpg/RPM-GPG-KEY-microsoft
rpm --import /etc/pki/rpm-gpg/RPM-GPG-KEY-microsoft
cat >/etc/yum.repos.d/vscode.repo <<'EOF'
[code]
name=Visual Studio Code
baseurl=https://packages.microsoft.com/yumrepos/vscode
enabled=1
gpgcheck=1
gpgkey=file:///etc/pki/rpm-gpg/RPM-GPG-KEY-microsoft
EOF
dnf5 install -y code
# Disable so the Microsoft repo is not active in the running OS;
# VS Code self-updates are not meaningful in an immutable image.
dnf5 config-manager setopt code.enabled=0
