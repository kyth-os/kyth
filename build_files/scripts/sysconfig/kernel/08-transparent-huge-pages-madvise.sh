#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

source "../../lib/config-helpers.sh"

# ── Transparent Huge Pages → madvise ─────────────────────────────────────────
# 'always' (kernel default) forces THP on all allocations and causes stutter.
# 'madvise' lets apps that benefit (e.g. JVMs, some game engines) opt in.
write_config /etc/tmpfiles.d/kyth-thp.conf <<'THPEOF'
w! /sys/kernel/mm/transparent_hugepage/enabled - - - - madvise
w! /sys/kernel/mm/transparent_hugepage/defrag  - - - - defer+madvise
THPEOF

# D-Bus socket activation needs the parent runtime directory before
# dbus.socket binds /run/dbus/system_bus_socket. The Fedora dbus tmpfiles entry
# in the bootc base only creates /var/lib/dbus, and /run is empty at every boot.
# Without this, dbus.socket fails, which then takes down logind, polkit,
# NetworkManager, and the SDDM greeter.
write_config /etc/tmpfiles.d/kyth-dbus.conf <<'DBUSTMPFILEEOF'
d /run/dbus 0755 root root -
DBUSTMPFILEEOF

# plocate ships /var/lib/plocate in its RPM, but bootc only materializes image
# /var content on the initial install — systems that gained plocate via an
# upgrade never get the directory and plocate-updatedb.service fails daily
# with "/var/lib/plocate/: No such file or directory".
write_config /etc/tmpfiles.d/kyth-plocate.conf <<'PLOCATETMPFILEEOF'
d /var/lib/plocate 0755 root root -
PLOCATETMPFILEEOF

# ostree symlinks /home→var/home, /srv→var/srv, /root→var/roothome. systemd's
# stock tmpfiles entries declare them as directories, so every boot logs
# '"/home" already exists and is not a directory' (and the same for /srv and
# /root) at error level. Replace those entries with symlink-creating ones
# that match the ostree layout; L is a no-op when the symlink already exists.
write_config /usr/lib/tmpfiles.d/home.conf <<'HOMETMPFILEEOF'
# KythOS override — /home and /srv are ostree symlinks into /var.
L /home - - - - var/home
L /srv - - - - var/srv
HOMETMPFILEEOF
sed -i 's|^d- /root .*|d /var/roothome 0700 root root -\nL /root - - - - var/roothome|' /usr/lib/tmpfiles.d/provision.conf
grep -q '^L /root ' /usr/lib/tmpfiles.d/provision.conf
