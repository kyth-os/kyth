# shellcheck shell=bash
# ── Proton-CachyOS runtime update path ────────────────────────────────────────
# The weekly kyth-proton-cachyos-update.timer installs Proton-CachyOS to
# /var/lib/kyth/proton-cachyos/ (/var is writable on an immutable system) and
# is the ONLY source of Proton-CachyOS on this image — there is no build-time
# install in /usr/share/steam/compatibilitytools.d/ (that RUN layer was
# removed from the Dockerfile). This means a fresh install has no
# Proton-CachyOS until the timer first succeeds over the network, and the live
# ISO never gets one at all (the timer is explicitly disabled there — see
# installer/build.sh's kyth-proton-cachyos-update.timer disable).
# The directory must exist at first boot regardless — Lutris (and Steam) call
# os.stat() on every path in STEAM_EXTRA_COMPAT_TOOLS_PATHS and crash with
# FileNotFoundError if any are missing, even before the update service has run
# for the first time.
mkdir -p /var/lib/kyth/proton-cachyos
chmod 1777 /var/lib/kyth/proton-cachyos
mkdir -p /usr/lib/tmpfiles.d
echo 'd /var/lib/kyth/proton-cachyos 1777 root root - -' >/usr/lib/tmpfiles.d/kyth-proton-cachyos.conf
echo 'STEAM_EXTRA_COMPAT_TOOLS_PATHS=/var/lib/kyth/proton-cachyos' >/etc/environment.d/proton-cachyos.conf
