# shellcheck shell=bash
# ── Proton-CachyOS runtime update path ────────────────────────────────────────
# The weekly timer installs new Proton-CachyOS to /var/lib/kyth/proton-cachyos/
# (/var is writable on an immutable system). Tell Steam to check this path in
# addition to the build-time install in /usr/share/steam/compatibilitytools.d/.
# The directory must exist at first boot — Lutris (and Steam) call os.stat() on
# every path in STEAM_EXTRA_COMPAT_TOOLS_PATHS and crash with FileNotFoundError
# if any are missing, even before the update service has run for the first time.
mkdir -p /var/lib/kyth/proton-cachyos
chmod 1777 /var/lib/kyth/proton-cachyos
mkdir -p /usr/lib/tmpfiles.d
echo 'd /var/lib/kyth/proton-cachyos 1777 root root - -' >/usr/lib/tmpfiles.d/kyth-proton-cachyos.conf
echo 'STEAM_EXTRA_COMPAT_TOOLS_PATHS=/var/lib/kyth/proton-cachyos' >/etc/environment.d/proton-cachyos.conf
