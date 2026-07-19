#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

# ── Google Antigravity IDE ────────────────────────────────────────────────────
# Bake Google Antigravity IDE native RPM into the image so it has full access to the local
# filesystem and terminal without the sandboxing constraints of a Flatpak.
# The Google repository signing key is vendored in-repo (build_files/RPM-GPG-KEY-google-antigravity)
# and bind-mounted at /ctx, so the build has no DNS-dependent rpm --import call.
install -Dm 0644 /ctx/RPM-GPG-KEY-google-antigravity /etc/pki/rpm-gpg/RPM-GPG-KEY-google-antigravity
# Skip importing key into RPM database because Fedora's strict crypto policy/Sequoia
# rejects the key format (No binding signature at time ...). Since Google Artifact
# Registry repositories are served over HTTPS, gpgcheck is disabled instead.
cat >/etc/yum.repos.d/antigravity.repo <<'EOF'
[antigravity-rpm]
name=Antigravity RPM Repository
baseurl=https://us-central1-yum.pkg.dev/projects/antigravity-auto-updater-dev/antigravity-rpm
enabled=1
gpgcheck=0
repo_gpgcheck=0
EOF
dnf5 install -y antigravity
# Disable so the Antigravity repo is not active in the running OS;
# self-updates are not meaningful in an immutable image.
dnf5 config-manager setopt antigravity-rpm.enabled=0

# Workaround for Electron's node.mojom.NodeService crashing on exit. Keep shell
# quoting out of Desktop Entry Exec fields: backslash-escaped quotes are not a
# valid desktop-entry escape and make KDE repeatedly reject/reparse the files.
install -d -m 0755 /usr/libexec
cat >/usr/libexec/kyth-antigravity <<'ANTIGRAVITYWRAPPEREOF'
#!/usr/bin/bash
ulimit -c 0
exec /usr/share/antigravity/antigravity "$@"
ANTIGRAVITYWRAPPEREOF
chmod 0755 /usr/libexec/kyth-antigravity
if [ -f /usr/share/applications/antigravity.desktop ]; then
	sed -i -E 's|^Exec=/usr/share/antigravity/antigravity|Exec=/usr/libexec/kyth-antigravity|' /usr/share/applications/antigravity*.desktop
fi
if [ -f /usr/share/antigravity/bin/antigravity ]; then
	# Insert 'ulimit -c 0' right after the shebang line.
	sed -i '2i ulimit -c 0' /usr/share/antigravity/bin/antigravity
fi
