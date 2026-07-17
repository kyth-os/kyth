#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

# Add rpmfusion free and nonfree repositories for Fedora 44.
# The release RPMs ship and install the GPG key themselves — this is the
# standard RPM Fusion bootstrap pattern; there is no separately hosted key
# URL to pre-import (unlike Brave/Negativo17).
# Fail loudly: every later codec install uses --skip-unavailable, so a missing
# RPM Fusion repo would otherwise ship an image silently lacking the
# freeworld codec stack.
fedora_release="$(rpm -E %fedora)"
dnf5 install -y \
	--setopt=retries=10 \
	--setopt=timeout=120 \
	"https://download1.rpmfusion.org/free/fedora/rpmfusion-free-release-${fedora_release}.noarch.rpm" \
	"https://download1.rpmfusion.org/nonfree/fedora/rpmfusion-nonfree-release-${fedora_release}.noarch.rpm"
rpm -q rpmfusion-free-release rpmfusion-nonfree-release

# Fedora 44 transitions can leave debug/source repo metalinks unpublished or
# intermittently unavailable. We never install from those repos in image builds,
# so disable them up front to avoid noisy 404s and brittle solver behavior.
#
# Also disable negativo17's fedora-multimedia repo when it is inherited from an
# upstream base image. RPM Fusion supplies the codec stack we need, while
# negativo17's Mesa builds have caused AMD VA-API to fail initialization.
python3 - <<'PY'
from pathlib import Path
import configparser

repo_dir = Path("/etc/yum.repos.d")
patterns = ("debug", "source")
disabled_repo_ids = {"fedora-multimedia"}
disabled_repo_tokens = ("negativo17",)

for repo_file in repo_dir.glob("*.repo"):
    parser = configparser.RawConfigParser(strict=False)
    parser.optionxform = str
    try:
        with repo_file.open("r", encoding="utf-8") as fh:
            parser.read_file(fh)
    except Exception:
        continue

    changed = False
    for section in parser.sections():
        section_lower = section.lower()
        repo_name = parser.get(section, "name", fallback="").lower()
        repo_baseurl = parser.get(section, "baseurl", fallback="").lower()
        repo_metalink = parser.get(section, "metalink", fallback="").lower()
        repo_mirrorlist = parser.get(section, "mirrorlist", fallback="").lower()
        repo_text = "\n".join((section_lower, repo_name, repo_baseurl, repo_metalink, repo_mirrorlist))
        should_disable = (
            any(token in section_lower for token in patterns)
            or section_lower in disabled_repo_ids
            or any(token in repo_text for token in disabled_repo_tokens)
        )
        if should_disable:
            if parser.get(section, "enabled", fallback="1").strip() != "0":
                parser.set(section, "enabled", "0")
                changed = True

    if changed:
        with repo_file.open("w", encoding="utf-8") as fh:
            parser.write(fh, space_around_delimiters=False)
PY
