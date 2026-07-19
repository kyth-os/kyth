#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

# ── Tailscale zero-config VPN ─────────────────────────────────────────────────
# WireGuard-based mesh VPN with no port forwarding required. Useful for LAN party
# gaming over the internet and remote desktop access.
# Disabled by default — opt-in via `ujust setup-tailscale`.
# Vendor the repo config inline rather than fetching from Tailscale's CDN at
# build time — a transient CDN blip would otherwise fail the entire build.
mkdir -p /etc/yum.repos.d
cat >/etc/yum.repos.d/tailscale-stable.repo <<'TAILSCALEREPOEOF'
[tailscale-stable]
name=Tailscale stable
baseurl=https://pkgs.tailscale.com/stable/fedora/$releasever/$basearch
enabled=1
type=rpm
repo_gpgcheck=1
gpgcheck=0
gpgkey=https://pkgs.tailscale.com/stable/fedora/repo.gpg
TAILSCALEREPOEOF
dnf5 install -y tailscale
systemctl disable tailscaled.service 2>/dev/null || true
dnf5 config-manager setopt tailscale-stable.enabled=0
