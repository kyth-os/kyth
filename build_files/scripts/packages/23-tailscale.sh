#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

# ── Tailscale repo bootstrap ──────────────────────────────────────────────────
# WireGuard-based mesh VPN with no port forwarding required. Useful for LAN party
# gaming over the internet and remote desktop access.
# Not installed at build time — the package itself is fetched on demand via
# `ujust setup-tailscale`, which enables this repo just-in-time. Vendoring the
# repo config here (rather than fetching it at first use) keeps a transient
# CDN blip from being able to break `ujust setup-tailscale` on a fresh install,
# and disabling it immediately keeps it from persisting as an active package
# source in images that never opt in.
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
dnf5 config-manager setopt tailscale-stable.enabled=0
