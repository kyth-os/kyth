#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

# Add rpmfusion free and nonfree repositories for Fedora 45.
# The release RPMs ship and install the GPG key themselves — this is the
# standard RPM Fusion bootstrap pattern; there is no separately hosted key
# URL to pre-import (unlike Brave/Negativo17).
#
# SECURITY: the bootstrap RPMs are fetched over TLS and then verified against
# pinned SHA256 hashes before install. A compromised bootstrap could otherwise
# point `gpgkey` at an attacker key, subverting all later "verified" installs.
# These hashes are byte-stable per Fedora release; bump them on releasever
# change (verify against https://rpmfusion.org/Configuration).
#   rpmfusion-free-release-45.noarch.rpm
RPMFUSION_FREE_SHA256="a120c2a2c70ec2c8ad461908aacf316998b03f6b2156c143b772052972e80a95"
#   rpmfusion-nonfree-release-45.noarch.rpm
RPMFUSION_NONFREE_SHA256="0cb381899827136c92be41a068e6177982bda36ce594729c0bf6f4fa485a15a9"
# Fail loudly: later codec installs must not silently drop freeworld packages
# when RPM Fusion is missing.
fedora_release="$(rpm -E %fedora)"
tmp_rpmfusion="$(mktemp -d)"
# shellcheck disable=SC2064
trap "rm -rf '${tmp_rpmfusion}'" EXIT
curl -fsSL --retry 3 \
	"https://download1.rpmfusion.org/free/fedora/rpmfusion-free-release-${fedora_release}.noarch.rpm" \
	-o "${tmp_rpmfusion}/rpmfusion-free-release.rpm"
curl -fsSL --retry 3 \
	"https://download1.rpmfusion.org/nonfree/fedora/rpmfusion-nonfree-release-${fedora_release}.noarch.rpm" \
	-o "${tmp_rpmfusion}/rpmfusion-nonfree-release.rpm"
if [[ "${fedora_release}" == "45" ]]; then
	echo "${RPMFUSION_FREE_SHA256}  ${tmp_rpmfusion}/rpmfusion-free-release.rpm" | sha256sum -c - \
		|| { echo "ERROR: rpmfusion-free-release checksum mismatch; refusing to install." >&2; exit 1; }
	echo "${RPMFUSION_NONFREE_SHA256}  ${tmp_rpmfusion}/rpmfusion-nonfree-release.rpm" | sha256sum -c - \
		|| { echo "ERROR: rpmfusion-nonfree-release checksum mismatch; refusing to install." >&2; exit 1; }
else
	echo "WARNING: no pinned checksum for Fedora ${fedora_release}; installing RPM Fusion bootstrap on TLS trust only." >&2
fi
dnf5 install -y \
	--setopt=retries=10 \
	--setopt=timeout=120 \
	"${tmp_rpmfusion}/rpmfusion-free-release.rpm" \
	"${tmp_rpmfusion}/rpmfusion-nonfree-release.rpm"
rpm -q rpmfusion-free-release rpmfusion-nonfree-release

# Fedora 45 transitions can leave debug/source repo metalinks unpublished or
# intermittently unavailable. We never install from those repos in image builds,
# so disable them up front to avoid noisy 404s and brittle solver behavior.
#
# Also disable negativo17's fedora-multimedia repo when it is inherited from an
# upstream base image. RPM Fusion supplies the codec stack we need, while
# negativo17's Mesa/ffmpeg builds have caused AMD VA-API failures and make
# gstreamer1-plugin-libav unsatisfiable against the split libav* layout.
python3 - <<'PY'
from pathlib import Path
import configparser

repo_dir = Path("/etc/yum.repos.d")
patterns = ("debug", "source")
disabled_repo_ids = {"fedora-multimedia"}
disabled_repo_tokens = ("negativo17", "fedora-multimedia")

for repo_file in sorted(repo_dir.glob("*.repo")):
    parser = configparser.RawConfigParser(strict=False)
    parser.optionxform = str
    try:
        with repo_file.open("r", encoding="utf-8") as fh:
            parser.read_file(fh)
    except OSError:
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

# Belt-and-suspenders: dnf config-manager + drop leftover multimedia repo files
# so a later fragment cannot re-enable via cached metadata alone.
if command -v dnf5 >/dev/null 2>&1; then
	dnf5 -y config-manager setopt fedora-multimedia.enabled=0 2>/dev/null || true
fi
# Remove any leftover multimedia .repo files from the image (ublue/negativo inherit).
shopt -s nullglob
for repo_file in /etc/yum.repos.d/*multimedia*.repo /etc/yum.repos.d/*negativo*.repo; do
	echo "Removing conflicting repo file: ${repo_file}"
	rm -f "${repo_file}"
done
shopt -u nullglob
