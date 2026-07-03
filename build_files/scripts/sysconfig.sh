#!/bin/bash

set -euo pipefail

# ── Kernel sysctl parameters ──────────────────────────────────────────────────
mkdir -p /etc/sysctl.d
cat >/etc/sysctl.d/99-kyth.conf <<'SYSCTLEOF'
# Memory
# swappiness=180: with zram present the kernel should aggressively swap to the
# fast compressed device rather than drop clean pages. The Fedora zram-generator
# project, CachyOS, and Bazzite all recommend 180 for zram systems. The old value
# of 10 caused the kernel to almost never use the zram swap it had set up,
# defeating its purpose and increasing OOM frequency under gaming load.
vm.swappiness = 180
# Keep a larger free-memory reserve so reclaim starts earlier and avoids sudden
# multi-second stall spikes during shader compilation or map loads.
vm.watermark_scale_factor = 125
vm.compaction_proactiveness = 0
# Absolute dirty limits instead of ratios. At 10% ratio a 32 GB machine allows
# 3.2 GB of dirty pages before writeback starts — too much buffering, causes
# visible stutter when the flush finally hits. 256 MB / 64 MB matches
# Bazzite/Nobara and keeps writeback incremental throughout gameplay.
vm.dirty_bytes = 268435456
vm.dirty_background_bytes = 67108864
vm.page_lock_unfairness = 1
# Disable swap read-ahead — on SSDs random I/O is fast; prefetching neighbours
# wastes bandwidth and causes micro-stutter under memory pressure
vm.page-cluster = 0
# Disable watermark boost — prevents burst memory reclaim spikes that cause stutter
vm.watermark_boost_factor = 0
# Reduce VFS cache reclaim aggressiveness — keeps game asset dentries/inodes
# in cache longer (default 100; 50 = half as eager to evict)
vm.vfs_cache_pressure = 50
# Raise memory map limit for games with large numbers of mappings (Star Citizen, etc.)
# 16M is still very high for gaming workloads while avoiding near-INT_MAX values.
vm.max_map_count = 16777216

# Writeback timing — flush dirty pages after 5 s instead of the kernel default
# 30 s. Paired with the absolute dirty_bytes limits above this keeps write bursts
# short and predictable during shader compilation / asset loading.
vm.dirty_expire_centisecs = 500
vm.dirty_writeback_centisecs = 500

# Network — use BBR when available; Fedora falls back if the module is absent.
net.core.default_qdisc = fq
net.ipv4.tcp_congestion_control = bbr

# Network socket buffers — raise caps for high-throughput workloads and gaming
net.core.rmem_max = 67108864
net.core.wmem_max = 67108864
net.ipv4.tcp_rmem = 4096 87380 67108864
net.ipv4.tcp_wmem = 4096 65536 67108864
# TCP Fast Open — reduce connection latency for repeat destinations
net.ipv4.tcp_fastopen = 3

# inotify — raise watch/instance limits for game clients and Electron launchers
# (EA App, Battle.net, etc. watch large directory trees and hit the 8192 default)
fs.inotify.max_user_watches = 524288
fs.inotify.max_user_instances = 1024

# Disable NMI watchdog — reduces interrupt overhead on gaming desktops
kernel.nmi_watchdog = 0

# Scheduler
kernel.sched_autogroup_enabled = 1

# Disable split-lock mitigation system-wide. Some Windows games running via Proton
# trigger split locks, and the kernel's default 10 ms throttling penalty causes
# severe stutters/fps drops. Safe to disable on gaming desktops as modern CPUs
# handle split locks gracefully without hardware lockup risks.
kernel.split_lock_mitigate = 0

# MTU probing — detect and recover from MTU black holes that can cause online
# game connections to stall silently on some ISPs and VPN paths with BBR.
net.ipv4.tcp_mtu_probing = 1

# Allow unprivileged access to CPU perf counters.
# Fedora defaults to 2 (kernel-only). Setting 1 lets MangoHud report accurate
# CPU frame times, enables GameMode's SCHED_FIFO eligibility checks, and
# allows sysprof/perf without root. Setting 0 would expose raw kernel addresses;
# 1 is the safe middle ground used by most gaming-focused distros.
kernel.perf_event_paranoid = 1

# Let the kernel choose the memory hog when userspace oomd does not act first.
# Killing the allocating task can take out an unrelated desktop service that
# happened to request memory while a game or browser was consuming the RAM.
vm.oom_kill_allocating_task = 0

# RT throttle — allow real-time threads ~98% of CPU time instead of the default
# 95%. GameMode elevates game threads to SCHED_FIFO; the 5% headroom reserves
# 50 ms/s for the kernel watchdog and IRQs. Raising to 2% headroom still protects
# the system while letting audio and render threads hit their deadlines under load.
kernel.sched_rt_runtime_us = 980000

# Reduce VM statistics update interval — less overhead on CPUs pinned to gaming
# workloads. Default is 1 s; 10 s cuts vm_stat_work CPU cost without hiding
# meaningful memory pressure information.
vm.stat_interval = 10

# Disable cross-CPU timer migration — timers fire on the CPU that set them
# rather than migrating to an "idle" core. Eliminates a class of inter-core
# wakeup latency jitter that shows up as micro-stutter on NUMA and CCD-split
# (Ryzen X3D) CPUs.
kernel.timer_migration = 0

# TIME_WAIT socket reuse — allow a new outgoing connection to reuse a socket
# in TIME_WAIT if the remote endpoint differs. Prevents ephemeral port exhaustion
# during matchmaking and launcher batch downloads (hundreds of short-lived
# TCP connections to CDN servers).
net.ipv4.tcp_tw_reuse = 1

# UDP tuning for online gaming
# netdev_max_backlog: how many packets the kernel queues per CPU before dropping.
# Default 1000 is too low for high-frequency online games (Valorant, CS2, etc.)
# sending and receiving hundreds of packets per second in burst.
net.core.netdev_max_backlog = 16384
# Raise the minimum UDP socket buffer floor so small-buffer sockets (game engines
# that do not call setsockopt) still get a usable baseline. Default 4096 B can
# cause silent packet loss on burst-heavy UDP game protocols.
net.ipv4.udp_rmem_min = 8192
net.ipv4.udp_wmem_min = 8192
SYSCTLEOF

# Load tcp_bbr module at boot so the BBRv3 sysctl takes effect
echo 'tcp_bbr' >/etc/modules-load.d/bbr.conf

# ── OpenRGB — i2c bus access ──────────────────────────────────────────────────
# i2c-dev: exposes /dev/i2c-* devices to userspace so OpenRGB can talk to
# DRAM, motherboard, and GPU RGB controllers directly.
# i2c-piix4: provides the SMBus (i2c) controller driver that covers the AMD
# FCH/SB southbridge found on virtually all Ryzen gaming motherboards and many
# Intel boards. Without it OpenRGB cannot enumerate most onboard RGB zones.
printf 'i2c-dev\ni2c-piix4\n' >/etc/modules-load.d/openrgb.conf

# ── systemd-oomd hardening ────────────────────────────────────────────────────
# By default systemd-oomd runs but monitors nothing — cgroups must explicitly
# opt in with ManagedOOMSwap/ManagedOOMMemoryPressure. Without these, oomd sits
# idle while the kernel OOM killer fires, which kills whatever happened to
# trigger the allocation (often dbus-broker, Xwayland, or plasmashell) rather
# than the actual memory hog — causing instant black screens.
#
# Thresholds are tuned for a gaming workload on a low-RAM system (≤16 GB):
# - 50% pressure / 15 s (old defaults) fires during every game loading screen
#   because shader compilation and asset streaming routinely sustain high
#   pressure for 20–40 s. That caused premature browser tab and app kills that
#   look like "memory crashes" but aren't OOM — just oomd misfiring.
# - 65% pressure / 40 s gives games room to burst through loading spikes while
#   still catching genuine runaway processes well before the kernel OOM killer.
# - SwapUsedLimit raised to 85%: zram compresses at ~3:1, so 85% of 14 GB of
#   zram logical capacity still leaves physical RAM available for decompression.
mkdir -p /etc/systemd/oomd.conf.d
cat >/etc/systemd/oomd.conf.d/99-kyth.conf <<'OOMDEOF'
[OOM]
SwapUsedLimit=85%
DefaultMemoryPressureLimit=65%
DefaultMemoryPressureDurationSec=40s
OOMDEOF

# Opt the user session slice into oomd monitoring. oomd will select and kill
# the highest-OOM-score process inside user.slice when thresholds are breached,
# sparing session-critical processes like dbus-broker and plasmashell.
mkdir -p /etc/systemd/system/user.slice.d
cat >/etc/systemd/system/user.slice.d/10-oomd-user.conf <<'OOMDSLICEEOF'
[Slice]
ManagedOOMSwap=kill
ManagedOOMMemoryPressure=kill
ManagedOOMMemoryPressureLimit=65%
OOMDSLICEEOF

# ── Locale defaults ─────────────────────────────────────────────────────────
# Force a 12-hour AM/PM clock by default on installed systems.
# LANG keeps the desktop in US English; LC_TIME specifically controls date/time
# formatting for Plasma, Qt, and libc-aware apps.
cat >/etc/locale.conf <<'LOCALEEOF'
LANG=en_US.UTF-8
LC_TIME=en_US.UTF-8
LOCALEEOF

# ── Transparent Huge Pages → madvise ─────────────────────────────────────────
# 'always' (kernel default) forces THP on all allocations and causes stutter.
# 'madvise' lets apps that benefit (e.g. JVMs, some game engines) opt in.
mkdir -p /etc/tmpfiles.d
cat >/etc/tmpfiles.d/kyth-thp.conf <<'THPEOF'
w! /sys/kernel/mm/transparent_hugepage/enabled - - - - madvise
w! /sys/kernel/mm/transparent_hugepage/defrag  - - - - defer+madvise
THPEOF

# D-Bus socket activation needs the parent runtime directory before
# dbus.socket binds /run/dbus/system_bus_socket. The Fedora dbus tmpfiles entry
# in the bootc base only creates /var/lib/dbus, and /run is empty at every boot.
# Without this, dbus.socket fails, which then takes down logind, polkit,
# NetworkManager, and the SDDM greeter.
cat >/etc/tmpfiles.d/kyth-dbus.conf <<'DBUSTMPFILEEOF'
d /run/dbus 0755 root root -
DBUSTMPFILEEOF

# bootc/ostree images keep several package-owned system accounts in
# /usr/lib/passwd and /usr/lib/group, while booted installations and useradd
# operate against the mutable /etc databases. If the installed /etc lacks those
# accounts, dbus-broker cannot build its NSS cache and SDDM cannot resolve the
# sddm greeter user, leaving QEMU at a black cursor after X starts.
cat >/usr/lib/systemd/system/kyth-system-accounts.service <<'SYSACCOUNTUNITEOF'
[Unit]
Description=Ensure KythOS system accounts are visible in /etc
DefaultDependencies=no
After=local-fs.target
Before=dbus.socket dbus-broker.service sockets.target sddm.service

[Service]
Type=oneshot
ExecStart=/usr/libexec/kyth-fix-system-accounts
RemainAfterExit=yes

[Install]
WantedBy=sysinit.target
SYSACCOUNTUNITEOF

install -d -m 0755 /usr/libexec
cat >/usr/libexec/kyth-fix-system-accounts <<'SYSACCOUNTSCRIPTEOF'
#!/usr/bin/bash
set -euo pipefail

append_missing_name() {
    local src="$1"
    local dest="$2"
    local name

    [ -r "$src" ] || return 0
    touch "$dest"
    while IFS= read -r line || [ -n "$line" ]; do
        [ -n "$line" ] || continue
        name="${line%%:*}"
        [ -n "$name" ] || continue
        if ! grep -q "^${name}:" "$dest"; then
            printf '%s\n' "$line" >> "$dest"
        fi
    done < "$src"
}

ensure_group_line() {
    local name="$1"
    local line="$2"
    if ! grep -q "^${name}:" /etc/group; then
        printf '%s\n' "$line" >> /etc/group
    fi
}

ensure_passwd_line() {
    local name="$1"
    local line="$2"
    if ! grep -q "^${name}:" /etc/passwd; then
        printf '%s\n' "$line" >> /etc/passwd
    fi
    if [ -e /etc/shadow ] && ! grep -q "^${name}:" /etc/shadow; then
        printf '%s:!*:19700:0:99999:7:::\n' "$name" >> /etc/shadow
    fi
}

append_missing_name /usr/lib/group /etc/group
append_missing_name /usr/lib/passwd /etc/passwd

# SDDM is commonly created by package scriptlets into /etc rather than shipped
# in /usr/lib/passwd, so keep an explicit fallback for installed deployments.
ensure_group_line sddm "sddm:x:959:"
ensure_passwd_line sddm "sddm:x:959:959:SDDM Greeter Account:/var/lib/sddm:/usr/sbin/nologin"

chmod 0644 /etc/passwd /etc/group
if [ -e /etc/shadow ]; then
    chmod 0000 /etc/shadow 2>/dev/null || chmod 0600 /etc/shadow
fi
mkdir -p /var/lib/sddm
chown sddm:sddm /var/lib/sddm 2>/dev/null || true
if command -v restorecon >/dev/null 2>&1; then
    restorecon /etc/passwd /etc/group /etc/shadow /var/lib/sddm 2>/dev/null || true
fi
SYSACCOUNTSCRIPTEOF
chmod 0755 /usr/libexec/kyth-fix-system-accounts
systemctl enable kyth-system-accounts.service 2>/dev/null || true

mkdir -p /etc/asusd

cat >/usr/lib/systemd/system/kyth-dbus-runtime-dir.service <<'DBUSRUNDIREOF'
[Unit]
Description=Create D-Bus runtime directory
DefaultDependencies=no
Before=sockets.target dbus.socket
After=kyth-system-accounts.service local-fs.target
Requires=kyth-system-accounts.service

[Service]
Type=oneshot
ExecStart=/usr/bin/mkdir -p /run/dbus
ExecStart=/usr/bin/chmod 0755 /run/dbus

[Install]
WantedBy=sysinit.target
DBUSRUNDIREOF
systemctl enable kyth-dbus-runtime-dir.service 2>/dev/null || true

# The system bus is foundational for logind, polkit, NetworkManager, and SDDM.
# On local QEMU boots dbus-broker repeatedly failed before the greeter started;
# remove audit integration from broker launch so lack of usable audit plumbing
# cannot take down the desktop.
mkdir -p /etc/systemd/system/dbus-broker.service.d
cat >/etc/systemd/system/dbus-broker.service.d/10-kyth-no-audit.conf <<'DBUSBROKEREOF'
[Service]
ExecStart=
ExecStart=/usr/bin/dbus-broker-launch --scope system
DBUSBROKEREOF

# ── AMD GPU kernel module options ────────────────────────────────────────────
# ppfeaturemask=0xffffffff: enables all PowerPlay features including fine-grained
# GPU/memory clock and voltage control. Required for gamemode's amd_performance_level
# switch to actually take full effect on RDNA APUs; without it some power states
# are locked out and the GPU stays in a lower-performance tier during gameplay.
#
# gttsize: GTT (Graphics Translation Table) is system RAM the GPU maps for overflow
# VRAM and DMA transfers. On a 14 GB APU the default is auto-sized but uncapped —
# the GPU can claim most of system RAM as GTT under sustained gaming load, starving
# CPU-side processes. Capping at 4096 MB leaves ≥10 GB reliably available for the
# CPU without starving games that need GPU memory bandwidth.
cat >/etc/modprobe.d/amdgpu-kyth.conf <<'AMDGPUEOF'
options amdgpu ppfeaturemask=0xffffffff
options amdgpu gttsize=4096
# noretry=0: allow the GPU to retry faulting memory accesses instead of
# immediately raising a fault signal. Prevents crashes in DX12 titles that
# access partially-mapped resources (common in games using tiled/sparse
# textures). The retry adds a small latency penalty on actual fault paths,
# which are rare during normal rendering.
options amdgpu noretry=0
AMDGPUEOF

# ── NVIDIA kernel module options ─────────────────────────────────────────────
# nvidia-drm.modeset=1  — required for Wayland/SDDM to use the NVIDIA KMS driver
#   instead of falling back to fbdev; without it KDE Plasma on Wayland will not
#   start on NVIDIA hardware.
# NVreg_PreserveVideoMemoryAllocations=1 — keeps VRAM contents across suspend/
#   resume cycles, preventing a black screen after wake on NVIDIA systems.
# nouveau is NOT blacklisted: the proprietary NVIDIA driver is not installed in
#   this image, so nouveau must remain loadable to provide KMS/display output on
#   NVIDIA hardware. If a user layers the proprietary driver via rpm-ostree they
#   should add their own blacklist via /etc/modprobe.d/blacklist-nouveau.conf.
cat >/etc/modprobe.d/nvidia-kyth.conf <<'NVEOF'
options nvidia-drm modeset=1
options nvidia NVreg_PreserveVideoMemoryAllocations=1
NVEOF

# ── Intel GPU kernel module options ─────────────────────────────────────────
# enable_guc=3: enables GuC firmware submission (command scheduling) and HuC
#   loading on Gen 9+ hardware. Without this, H.264/HEVC VA-API decode falls
#   back to software on many Intel iGPUs, and power management is degraded.
# enable_huc=2: forces HuC firmware load even when GuC submission is active.
#   Required on some Gen 9/10 parts where HuC would otherwise be skipped.
# These options are safe no-ops on Intel GPUs that use the xe driver (Arc /
#   Meteor Lake+), which manages GuC/HuC independently of i915.
cat >/etc/modprobe.d/i915-kyth.conf <<'I915EOF'
options i915 enable_guc=3 enable_huc=2
I915EOF

# ── NTSYNC ───────────────────────────────────────────────────────────
# Custom kernels may ship ntsync. The udev rule gives the 'users' group access
# to /dev/ntsync so Wine/Proton can use NT synchronization primitives when the
# module is available.
mkdir -p /usr/lib/modules-load.d
echo 'ntsync' >/usr/lib/modules-load.d/kyth-ntsync.conf
echo 'KERNEL=="ntsync", GROUP="users", MODE="0660"' \
	>/usr/lib/udev/rules.d/99-ntsync.rules

# zram-size = ram: logical size equals physical RAM.
# With zram present, the logical size is not static physical overhead; it grows
# lazily. Compressed pages at ~3:1 zstd ratio mean a full zram swap uses only
# ~1/3 of its capacity in physical RAM, offering a massive buffer that prevents
# lockups/OOM-kills during heavy compilation or AAA gaming.
# swap-priority=100 ensures zram is always chosen over any disk swap.
cat >/etc/systemd/zram-generator.conf <<'ZRAMEOF'
[zram0]
zram-size = ram
compression-algorithm = zstd
swap-priority = 100
ZRAMEOF

# ── gamemode configuration ────────────────────────────────────────────────────
# Applied when a game calls gamemoderun or uses the gamemode SDL hook.
# renice/ioprio: game process gets higher CPU + I/O scheduling priority.
# gpu: switches AMD GPU to high-performance power profile during gameplay.
cat >/etc/gamemode.ini <<'GAMEMODEEOF'
[general]
renice = 10
ioprio = 0
# Inhibit screensaver during gameplay — prevents blanking during cutscenes/loads
inhibit_screensaver = 1
# Older ports may issue split locks. Relax the mitigation only while GameMode is
# active, then restore the secure system-wide default when the game exits.
disable_splitlock = 1
# Promote game threads to SCHED_FIFO via rtkit when conditions allow.
# 'auto' only engages when the system is not under memory pressure.
softrealtime = auto
# Switch to the gaming performance profile automatically when a game launches
# via GameMode, and restore the previous state on exit.
# kyth-performance-mode: saves current powerprofile + KWin blur/animation state,
# switches to performance power profile + reduced animations, then restores on exit.
# GameMode runs startscript/endscript via /bin/sh -c as the game user.
# DBUS_SESSION_BUS_ADDRESS may not be inherited (depends on how the game was
# launched), so we set it explicitly via the logind socket path as a fallback.
# unix:path=/run/user/UID/bus is guaranteed present for any logged-in user.
startscript=export DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-unix:path=/run/user/$(id -u)/bus}"; /usr/bin/kyth-performance-mode save && /usr/bin/kyth-performance-mode gaming
endscript=DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-unix:path=/run/user/$(id -u)/bus}" /usr/bin/kyth-performance-mode restore

[cpu]
park_cores = no
pin_cores = yes

[gpu]
apply_gpu_optimisations = accept-responsibility
amd_performance_level = high
nv_perf_level = 5
GAMEMODEEOF

# ── Bluetooth — enable adapter on every boot ────────────────────────────────
# BlueZ ships with AutoEnable commented out (value is 'false' in modern versions).
# Replace any commented AutoEnable line with the enabled form; append to [Policy]
# if the line is missing entirely. AutoEnable handles newly-seen controllers, while
# kyth-bluetooth-enable.service corrects persisted rfkill / controller power state
# on every boot.
mkdir -p /etc/bluetooth
touch /etc/bluetooth/main.conf
sed -i -E 's/^[#[:space:]]*AutoEnable=.*/AutoEnable=true/' /etc/bluetooth/main.conf
grep -q '^AutoEnable=' /etc/bluetooth/main.conf ||
	printf '\n[Policy]\nAutoEnable=true\n' >>/etc/bluetooth/main.conf

# Udev rule: unblock Bluetooth the moment any rfkill device of type bluetooth
# appears. This covers HP WMI and other drivers (common on HP ZBook) that expose
# their rfkill device asynchronously — AFTER kyth-bluetooth-enable.service has
# already run at boot. Without this rule those adapters boot soft-blocked and
# nothing subsequently unblocks them until the user toggles Bluetooth manually.
mkdir -p /etc/udev/rules.d
cat >/etc/udev/rules.d/69-kyth-bluetooth.rules <<'BTUDEVEOF'
# Unblock Bluetooth immediately when any rfkill bluetooth device appears.
# Handles HP WMI and similar drivers that load their rfkill entry after the
# kyth-bluetooth-enable systemd service has already executed.
#
# Use %s{index} (the numeric rfkill index) rather than the type-wide
# "rfkill unblock bluetooth" to send RFKILL_OP_CHANGE to only this device.
# This avoids triggering shared-rfkill hardware (e.g. HP WMI combined
# wireless kill-switch) which would also unblock Wi-Fi and cause NM to
# re-enable Wi-Fi even if the user had intentionally turned it off.
ACTION=="add", SUBSYSTEM=="rfkill", ATTR{type}=="bluetooth", RUN+="/usr/sbin/rfkill unblock %s{index}"
BTUDEVEOF

cat >/usr/libexec/kyth-enable-bluetooth <<'BTENABLEEOF'
#!/usr/bin/bash
set -uo pipefail

# Clear any saved soft-block state that systemd-rfkill would restore on the
# next boot.  The files are named after the rfkill index (e.g. "platform-xxx:bluetooth").
# Removing them prevents systemd-rfkill from overriding our unblock on next boot.
find /var/lib/systemd/rfkill -name "*bluetooth*" -delete 2>/dev/null || true

# Snapshot Wi-Fi software state before unblocking Bluetooth. On systems with a
# shared hardware kill-switch (e.g. HP WMI), rfkill unblock bluetooth can also
# clear the Wi-Fi hard-block, which causes NetworkManager to re-enable Wi-Fi
# even if the user had intentionally disabled it last session.
_wifi_was_soft_blocked=0
if rfkill list wifi 2>/dev/null | grep -q 'Soft blocked: yes'; then
    _wifi_was_soft_blocked=1
fi

if command -v rfkill >/dev/null 2>&1; then
    rfkill unblock bluetooth >/dev/null 2>&1 || true
fi

# Restore Wi-Fi soft-block if it was user-disabled before we ran.
if [[ "${_wifi_was_soft_blocked}" -eq 1 ]]; then
    rfkill block wifi >/dev/null 2>&1 || true
fi

if command -v bluetoothctl >/dev/null 2>&1; then
    bluetoothctl power on >/dev/null 2>&1 || true
fi

exit 0
BTENABLEEOF
chmod 0755 /usr/libexec/kyth-enable-bluetooth

cat >/usr/lib/systemd/system/kyth-bluetooth-enable.service <<'BTENABLEUNITEOF'
[Unit]
Description=Enable Bluetooth adapters at boot
Documentation=https://github.com/mrtrick37/kyth
# Run after systemd-rfkill has restored saved state so we can override it.
After=bluetooth.service systemd-rfkill.service
Wants=bluetooth.service

[Service]
Type=oneshot
ExecStart=/usr/libexec/kyth-enable-bluetooth
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
BTENABLEUNITEOF

systemctl enable bluetooth.service 2>/dev/null || true
systemctl enable kyth-bluetooth-enable.service 2>/dev/null || true
systemctl enable cups-browsed.service 2>/dev/null || true
# input-remapper.service is enabled later in this script alongside rtkit-daemon

# ── WiFi — disable power management ──────────────────────────────────────────
# Linux WiFi power-save throttles the radio when idle, reducing signal
# sensitivity and causing apparent "weak signal" even close to the AP.
# NetworkManager powersave=2 disables it at the connection level (all adapters).
mkdir -p /etc/NetworkManager/conf.d
cat >/etc/NetworkManager/conf.d/wifi-powersave-off.conf <<'NMEOF'
[connection]
wifi.powersave = 2
NMEOF

# ── WiFi driver tweaks ───────────────────────────────────────────────────────
mkdir -p /etc/modprobe.d

cat >/etc/modprobe.d/cfg80211-kyth.conf <<'CFG80211EOF'
options cfg80211 ieee80211_regdom=US
CFG80211EOF

# MT7921/MT7925 PCIe (MediaTek Filogic): disable Active State Power Management.
# ASPM puts the PCIe device into a low-power state it may not reliably wake
# from, causing sudden disconnects, intermittent scan results, and sometimes
# requiring a driver reload or reboot. mt7925e (Wi-Fi 7 parts, e.g. HP ZBook)
# is a separate module from mt7921e and needs its own options line.
cat >/etc/modprobe.d/mt7921-kyth.conf <<'MT76EOF'
options mt7921e disable_aspm=1
options mt7925e disable_aspm=1
MT76EOF

# iwlwifi/iwlmvm (Intel Wi-Fi): keep the radio in CAM/active mode and disable
# U-APSD. Several Intel AX-class adapters, including HP EliteBook CNVio parts,
# can scan successfully but fail or stall during WPA association when firmware
# power-save enters the handshake. Keep Bluetooth coexistence enabled; it is
# the safer default for mixed 2.4 GHz Wi-Fi plus Bluetooth office environments.
cat >/etc/modprobe.d/iwlwifi-kyth.conf <<'IWLEOF'
options iwlwifi power_save=0 uapsd_disable=3 bt_coex_active=1
IWLEOF

cat >/etc/modprobe.d/iwlmvm-kyth.conf <<'IWLMVMEOF'
options iwlmvm power_scheme=1
IWLMVMEOF

# btusb (USB Bluetooth, incl. MediaTek MT7922/MT7925 combo radios): disable
# USB autosuspend. The CachyOS kernel builds btusb with autosuspend enabled,
# which suspends the adapter after 2 s idle. USB remote wakeup is unreliable
# on these parts, so a suspended adapter misses traffic from low-bandwidth BLE
# peripherals — mice silently drop every few minutes and only reconnect on
# user input, and reconnect after boot/login is slow for the same reason.
cat >/etc/modprobe.d/btusb-kyth.conf <<'BTUSBEOF'
options btusb enable_autosuspend=0
BTUSBEOF

# ── I/O schedulers ─────────────────────────────────────────────────────────
# Keep NVMe on kernel defaults. Testers can opt into the experimental KythOS
# profile with `ujust nvme-tuning kyth` and compare it against a clean reboot
# after `ujust nvme-tuning default`.
# 'mq-deadline' on SATA SSD — adds deadline fairness with minimal latency.
# 'bfq' on rotational — budget fair queuing prevents seek storms.
mkdir -p /etc/udev/rules.d
cat >/etc/udev/rules.d/60-ioschedulers.rules <<'IOEOF'
# SATA SSDs (non-rotational): deadline with low latency + 1 MB read-ahead
ACTION=="add|change", KERNEL=="sd[a-z]*", ATTR{queue/rotational}=="0", ATTR{queue/scheduler}="mq-deadline"
ACTION=="add|change", KERNEL=="sd[a-z]*", ATTR{queue/rotational}=="0", ATTR{queue/read_ahead_kb}="1024"
# HDDs: BFQ to avoid seek storms
ACTION=="add|change", KERNEL=="sd[a-z]*", ATTR{queue/rotational}=="1", ATTR{queue/scheduler}="bfq"
# VirtIO block (QEMU/KVM VMs): mq-deadline — BFQ can stall under heavy sequential I/O
ACTION=="add|change", KERNEL=="vd[a-z]*", ATTR{queue/scheduler}="mq-deadline"
IOEOF

# ── PipeWire low-latency audio ─────────────────────────────────────────────────
# 128 samples at 48 kHz = ~2.7 ms latency — low enough to eliminate perceptible
# audio lag in games while staying stable on typical hardware.
# min-quantum=32 lets pro-audio apps request sub-1 ms when needed.
# Apps that need higher buffering (e.g. Bluetooth) negotiate up automatically.
mkdir -p /etc/pipewire/pipewire.conf.d
cat >/etc/pipewire/pipewire.conf.d/99-kyth.conf <<'PWEOF'
context.properties = {
    default.clock.rate          = 48000
    default.clock.quantum       = 128
    default.clock.min-quantum   = 32
    default.clock.max-quantum   = 8192
    # Allow PipeWire to switch between 44100 and 48000 Hz rather than resampling.
    # Without this, a game or app that outputs at 44100 Hz forces the entire graph
    # (mic, desktop audio, etc.) through a sample-rate converter — adding CPU
    # overhead and latency. With it, PipeWire renegotiates the clock rate instead.
    default.clock.allowed-rates = [ 44100 48000 ]
}
PWEOF

# ── Proton / RADV environment variables ───────────────────────────────────────
# PROTON_FORCE_LARGE_ADDRESS_AWARE / WINE_LARGE_ADDRESS_AWARE:
#   Forces 32-bit Windows games to use the full 4 GB address space, reducing
#   OOM crashes in memory-heavy titles (e.g. Skyrim modded, DayZ).
# mesa_glthread=true:
#   Offloads OpenGL command submission to a second thread, improving CPU-bound
#   framerate in OpenGL games (Minecraft, older Source titles, etc.). Safe
#   system-wide; Vulkan/DXVK games are unaffected.
mkdir -p /etc/environment.d
cat >/etc/environment.d/proton-radv.conf <<'PROTONEOF'
PROTON_FORCE_LARGE_ADDRESS_AWARE=1
WINE_LARGE_ADDRESS_AWARE=1
PROTON_USE_NTSYNC=1
# esync/fsync: fallback sync primitives used when NTSYNC is unavailable (module
# not loaded, older kernel, or non-kyth install). Proton checks in priority order:
# NTSYNC → fsync → esync → default. Having both enabled costs nothing when NTSYNC
# is active, and keeps Wine/Proton fast on any system this image runs on.
WINEFSYNC=1
WINEESYNC=1
mesa_glthread=true
# FSR upscaling in fullscreen Wine/Proton games — lets older titles that don't
# run at native resolution get FidelityFX Super Resolution upscaling via Wine's
# built-in FSR pass. Works on AMD, NVIDIA, and Intel — it's a shader effect, not
# hardware. Strength 0 = sharpest, 5 = most blur; 2 is a good default balance.
WINE_FULLSCREEN_FSR=1
WINE_FULLSCREEN_FSR_STRENGTH=2
# Suppress the Windows-style crash/error dialog that pops up when a game
# exits unexpectedly via Wine's built-in error handler. On Linux the crash is
# already captured by the kernel and Proton's own logging; the dialog just
# forces the user to click through a meaningless "Application Error" popup.
PROTON_NO_WINDOWS_CRASH_DIALOG=1
# Silence DXVK verbose debug output. The default "info" level writes to disk
# on every DX9/10/11 draw call setup, adding measurable I/O overhead on
# titles with high draw call counts. "none" keeps only fatal errors.
DXVK_LOG_LEVEL=none
# Enable DirectX 12 ray tracing in VKD3D-Proton. dxr advertises Tier 1 RT;
# dxr11 adds DX11-style conservative RT fallback used by some titles. VKD3D
# won't expose RT to the game unless the GPU Vulkan driver actually supports the
# VK_KHR_ray_tracing_pipeline extension, so this is safe to set globally.
VKD3D_CONFIG=dxr11,dxr
# VKD3D-Proton logs at "warn" level by default — noisy in the journal.
# Matches DXVK_LOG_LEVEL=none above.
VKD3D_LOG_LEVEL=none
# MangoHud: fall back to dlsym hooking for older OpenGL games that dlopen libGL
# rather than linking it at load time. Safe to set globally; no-op for Vulkan.
MANGOHUD_DLSYM=1
# Prevent Steam from spawning a renderer subprocess for the built-in browser
# when it is not in use — saves ~100 MB of resident memory.
STEAM_DISABLE_BROWSER_SUBPROCESS=1
# Mesa Shader Cache size limit: raise to 10 GB to prevent shader eviction and
# stuttering on subsequent launches of shader-heavy games.
MESA_SHADER_CACHE_MAX_SIZE=10G
PROTONEOF


# ── NVIDIA NVAPI: detect at login, not at build time ─────────────────────────
# PROTON_ENABLE_NVAPI tells Proton to emulate NVIDIA's API layer.  It is only
# meaningful on systems with NVIDIA hardware; setting it on AMD/Intel causes
# games that check for NVAPI to try NVIDIA-specific paths and silently fail.
# A systemd user-environment generator runs at each login and outputs the
# variable only when an NVIDIA GPU is detected via lspci.
install -m 0755 /dev/stdin /usr/lib/systemd/user-environment-generators/80-kyth-nvapi.sh <<'NVAPIEOF'
#!/bin/bash
if lspci -d ::0300 2>/dev/null | grep -qi nvidia || \
   lspci -d ::0302 2>/dev/null | grep -qi nvidia; then
    # VKD3D-Proton (DX12) NVAPI: enables DLSS, Reflex, and NV-specific rendering
    # paths in DX12 games. Proton checks this before its own NVAPI detection.
    echo "PROTON_ENABLE_NVAPI=1"
    # DXVK (DX9/10/11) NVAPI: complementary to PROTON_ENABLE_NVAPI — DXVK has
    # its own NVAPI implementation used for DX11 games with NVAPI dependencies.
    echo "DXVK_ENABLE_NVAPI=1"
    # NVIDIA equivalent of mesa_glthread: offloads OpenGL command submission to
    # a second thread. Only meaningful on NVIDIA + OpenGL; Vulkan/DXVK unaffected.
    echo "__GL_THREADED_OPTIMIZATIONS=1"
    # Keep the NVIDIA OpenGL shader disk cache and prevent automatic pruning.
    # Without these, NVIDIA deletes cached shaders when the cache grows beyond
    # a threshold, forcing recompilation stutter every N launches.
    echo "__GL_SHADER_DISK_CACHE=1"
    echo "__GL_SHADER_DISK_CACHE_SKIP_CLEANUP=1"
    # nvidia-vaapi-driver: libva will not auto-detect the NVIDIA backend without
    # an explicit driver name. NVD_BACKEND=direct uses the NvDecode API directly
    # (avoids the deprecated CUDA path; works on Turing/Ampere/Ada without CUDA).
    echo "LIBVA_DRIVER_NAME=nvidia"
    echo "NVD_BACKEND=direct"
fi
NVAPIEOF

# ── Open file descriptor limit (esync / general compatibility) ────────────────
# esync requires a high open-file limit; even with NTSYNC some games fall back
# to it. 1048576 matches Bazzite and CachyOS defaults. Applied to both system
# services and user sessions.
mkdir -p /etc/systemd/system.conf.d /etc/systemd/user.conf.d
echo '[Manager]
DefaultLimitNOFILE=1048576' >/etc/systemd/system.conf.d/99-kyth-limits.conf
echo '[Manager]
DefaultLimitNOFILE=1048576' >/etc/systemd/user.conf.d/99-kyth-limits.conf

# ── VS Code / Brave: quiet local secret store ────────────────────────────────
# Seed new users with local password-store defaults so Code and Brave do not
# open KWallet on first launch.
HOME=/etc/skel /ctx/kyth-vscode-wallet

# ── Baloo file indexer — disabled by default ─────────────────────────────────
# Baloo (KDE's file indexer) runs heavy I/O scans on first boot and after game
# downloads, causing stutter mid-session. Disable it in the skel so new users
# start with indexing off. Users can re-enable it from System Settings → Search.
mkdir -p /etc/skel/.config
cat >/etc/skel/.config/baloofilerc <<'BALOOEOF'
[Basic Settings]
Indexing-Enabled=false
BALOOEOF

# ── journald size cap ────────────────────────────────────────────────────────
# On a gaming desktop the journal can silently grow to multi-GB over time from
# verbose game/driver output. Cap persistent storage at 500 MB and the in-memory
# runtime journal (current boot) at 128 MB.
mkdir -p /etc/systemd/journald.conf.d
cat >/etc/systemd/journald.conf.d/99-kyth.conf <<'JOURNALDEOF'
[Journal]
SystemMaxUse=500M
RuntimeMaxUse=128M
JOURNALDEOF

# ── MangoHud default config ───────────────────────────────────────────────────
# Pre-configure a curated overlay: useful OOTB without being overwhelming.
# Users can override globally via ~/.config/MangoHud/MangoHud.conf or per-game
# via the MANGOHUD_CONFIG env var / Steam launch options.
mkdir -p /etc/skel/.config/MangoHud
cat >/etc/skel/.config/MangoHud/MangoHud.conf <<'MANGOHUDEOF'
# KythOS default MangoHud overlay — toggle with Shift_R+F12
# Full option reference: https://github.com/flightlessmango/MangoHud

toggle_hud=Shift_R+F12

# Position and style
position=top-left
background_alpha=0.5
font_size=20
text_color=FFFFFF
round_corners=4

# Frame metrics
fps
# Color-code FPS: green ≥60, yellow ≥30, red <30
fps_color_change=1
fps_value=60,30
# Show when an FPS cap/limit is active (Steam, MangoHud, or driver limiter)
show_fps_limit
frametime=1
frame_timing=1

# GPU
gpu_name
gpu_stats
gpu_temp
gpu_core_clock
gpu_mem_clock
vram
# GPU power draw — a sustained drop toward TDP indicates thermal throttling
gpu_power
# Active Vulkan driver (RADV, AMDVLK, ANV, etc.)
vulkan_driver

# CPU
cpu_stats
cpu_temp
cpu_mhz
# CPU package power — useful for spotting frequency boosts and throttle events
cpu_power

# System RAM
ram

# Battery (shown only on systems where a battery is present)
battery

# Presentation mode (FIFO=vsync, Immediate=tearing, Mailbox=triple-buffer)
present_mode

# Wine/Proton layer: show version and translation layer (DXVK/VKD3D) version
wine
engine_version
MANGOHUDEOF

# ── vkBasalt default config ───────────────────────────────────────────────────
# vkBasalt is only active when ENABLE_VKBASALT=1 is set (per-launch or globally).
# Pre-configure CAS sharpening so there's a sensible default when users opt in.
# casSharpness: 0.0 = maximum sharpening, 1.0 = no sharpening; 0.4 is a clean balance.
cat >/etc/vkBasalt.conf <<'VKBASALTEOF'
effects = cas
casSharpness = 0.4
# Toggle the effect on/off in-game
toggleKey = Home
VKBASALTEOF

# ── topgrade defaults — disable steps that don't apply or cause noise ─────────
# helix: grammar fetch fails when git picks up a stale VS Code credential-helper
#   socket (GIT_ASKPASS), producing spurious auth errors; Helix ships grammars
#   bundled with the binary so grammar fetching is not needed during routine updates.
# system/distrobox/containers/toolbx: managed separately by KythOS tooling.
mkdir -p /etc/skel/.config
cat >/etc/skel/.config/topgrade.toml <<'TOPGRADEEOF'
[misc]
disable = ["system", "distrobox", "containers", "toolbx", "helix"]
TOPGRADEEOF

# ── Font rendering — sharp LCD defaults ──────────────────────────────────────
# Linux freetype defaults vary by distro; Fedora's are conservative. hintfull
# snaps stems to pixel boundaries for maximum on-screen crispness (matches the
# sharpness of Windows ClearType on typical 1080p panels). autohint=false keeps
# FreeType using the font's own hinting tables rather than its generic engine.
# Users who prefer a different look can drop a file in ~/.config/fontconfig/.
mkdir -p /etc/fonts/conf.d
cat >/etc/fonts/local.conf <<'FONTCONFIGEOF'
<?xml version="1.0"?>
<!DOCTYPE fontconfig SYSTEM "fonts.dtd">
<fontconfig>
  <match target="font">
    <edit name="antialias"  mode="assign"><bool>true</bool></edit>
    <edit name="hinting"    mode="assign"><bool>true</bool></edit>
    <edit name="autohint"   mode="assign"><bool>false</bool></edit>
    <edit name="hintstyle"  mode="assign"><const>hintfull</const></edit>
    <edit name="rgba"       mode="assign"><const>rgb</const></edit>
    <edit name="lcdfilter"  mode="assign"><const>lcddefault</const></edit>
  </match>
</fontconfig>
FONTCONFIGEOF

# systemd-remount-fs tries to remount the root filesystem, which is immutable
# on bootc/ostree systems and always fails with exit status 32. Mask it.
systemctl mask systemd-remount-fs.service

# Re-enforce display-manager and default target symlinks here (layer 6).
# The dnf5 upgrade in layer 3 can re-apply systemd presets and reset the
# display-manager alias.  Use explicit symlinks — systemctl enable is a
# no-op in a container build (no running systemd bus, silently swallowed
# by 2>/dev/null || true).
ln -sf /usr/lib/systemd/system/sddm.service \
	/etc/systemd/system/display-manager.service
mkdir -p /etc/systemd/system/graphical.target.wants
ln -sf /etc/systemd/system/display-manager.service \
	/etc/systemd/system/graphical.target.wants/display-manager.service
ln -sf /usr/lib/systemd/system/graphical.target \
	/etc/systemd/system/default.target

systemctl enable rtkit-daemon.service 2>/dev/null || true
systemctl enable input-remapper.service 2>/dev/null || true
# joycond: pairs left + right Joy-Cons into a single virtual controller.
# Only active when Joy-Con hardware is detected; no-op on other systems.
systemctl enable joycond.service 2>/dev/null || true
# Periodic SSD TRIM — reclaims blocks marked free by the filesystem. Safe on
# all modern SSDs and NVMe drives; the timer runs weekly by default.
systemctl enable fstrim.timer 2>/dev/null || true
# Distribute hardware IRQs across all CPU cores. Without this all IRQs land on
# cpu0, causing it to spike during heavy I/O or network activity mid-game.
systemctl enable irqbalance.service 2>/dev/null || true
# Fedora/libvirt can expose either legacy libvirtd or modular virtqemud units.
# Enable whichever socket exists so image builds stay portable across releases.
if systemctl list-unit-files --type=socket --no-legend 2>/dev/null | grep -q '^libvirtd\.socket'; then
	systemctl enable libvirtd.socket 2>/dev/null || true
elif systemctl list-unit-files --type=socket --no-legend 2>/dev/null | grep -q '^virtqemud\.socket'; then
	systemctl enable virtqemud.socket 2>/dev/null || true
else
	echo "libvirt socket unit not found; skipping enable."
fi
systemctl enable docker.socket 2>/dev/null || true
systemctl enable fwupd 2>/dev/null || true
systemctl enable pcscd.socket 2>/dev/null || true

# ── Automatic updates: use bootc, not rpm-ostree ──────────────────────────────
# rpm-ostreed-automatic conflicts with bootc over the sysroot lock.
# Disable it entirely — bootc-fetch-apply-updates.timer is also disabled because
# its default behaviour (bootc upgrade --apply) reboots the system automatically
# whenever a new image is available, causing unexpected reboots ~1h after boot.
# Users should update manually: sudo bootc upgrade && sudo systemctl reboot
systemctl disable rpm-ostreed-automatic.timer rpm-ostreed-automatic.service 2>/dev/null || true
systemctl disable bootc-fetch-apply-updates.timer bootc-fetch-apply-updates.service 2>/dev/null || true
# Keep Fedora's standalone CountMe timer enabled on installed atomic systems.
# bootc upgrades do not normally fetch RPM repository metadata, so DNF's
# countme=True setting alone is not enough to report active installed systems.
if systemctl list-unit-files --type=timer --no-legend 2>/dev/null | grep -q '^rpm-ostree-countme\.timer'; then
	systemctl enable rpm-ostree-countme.timer 2>/dev/null || true
fi
# Mask packagekitd so Plasma Discover cannot query it for RPM-level updates.
# plasma-discover-rpm-ostree is removed in packages.sh; this masks the generic
# DNF/PackageKit backend as a belt-and-suspenders measure.
systemctl mask packagekit.service 2>/dev/null || true

# Mask the Discover update notifier for all users. Discover's Flatpak backend
# bypasses PackageKit and would still surface its own update prompts.
# System Hub owns the update notification flow via kyth-update-watcher.
mkdir -p /etc/systemd/user
ln -sf /dev/null /etc/systemd/user/plasma-discover-notifier.service

# ── Boot-time noise reduction ─────────────────────────────────────────────────
# NetworkManager-wait-online blocks network-online.target (and thus multi-user
# and graphical targets) until the network is fully up — adds ~5s on every
# boot. Desktop systems don't need the network ready before the login screen;
# services that genuinely need network declare their own After=network-online.
systemctl disable NetworkManager-wait-online.service 2>/dev/null || true

# flatpak-system-update runs on every boot and takes 20+ seconds fetching
# Flatpak metadata. Flatpaks are updated explicitly via topgrade or ujust.
systemctl disable flatpak-system-update.service flatpak-system-update.timer 2>/dev/null || true

# fedora-atomic-desktop-appstream-cache-refresh regenerates the AppStream cache
# on every boot (~4s). Runs on-demand when the software center needs it.
systemctl disable fedora-atomic-desktop-appstream-cache-refresh.service 2>/dev/null || true

# serial-getty@ttyS0 waits 45s for a serial device that doesn't exist on this
# hardware before timing out. Mask it so the timeout doesn't hold up boot.
systemctl mask serial-getty@ttyS0.service 2>/dev/null || true

# Apply the same account repair in the image now so the deployed /etc starts
# correct, then keep the enabled service as a boot-time guardrail.
/usr/libexec/kyth-fix-system-accounts || true

# useradd only reads /etc/group, but Fedora system groups live in /usr/lib/group.
# Copy any missing groups into /etc/group; create with groupadd if absent entirely.
for grp in users video audio gamemode docker disk kvm tty clock kmem input render lp utmp plugdev dbus sddm polkitd; do
	if ! grep -q "^${grp}:" /etc/group; then
		if getent group "$grp" >/dev/null 2>&1; then
			getent group "$grp" >>/etc/group
		else
			groupadd "$grp"
		fi
	fi
done

# ── Homebrew Environment Auto-Bootstrapping ──────────────────────────────────
# Automate adding Homebrew to PATH and environment for bash, zsh, and fish shells.
mkdir -p /etc/profile.d /etc/fish/conf.d

cat >/etc/profile.d/brew.sh <<'BREWSHEOF'
# Add Homebrew to PATH and configure environment for sh/bash/zsh if it exists
for _brew_path in "/home/linuxbrew/.linuxbrew/bin/brew" "${HOME}/.linuxbrew/bin/brew"; do
    if [ -x "${_brew_path}" ]; then
        eval "$("${_brew_path}" shellenv)"
        break
    fi
done
BREWSHEOF

cat >/etc/fish/conf.d/brew.fish <<'BREWFISHEOF'
# Add Homebrew to PATH and configure environment for fish shell if it exists
for _brew_path in "/home/linuxbrew/.linuxbrew/bin/brew" "$HOME/.linuxbrew/bin/brew"
    if test -x $_brew_path
        eval ($_brew_path shellenv)
        break
    end
end
BREWFISHEOF

# ── OBS Studio VKCapture Override ────────────────────────────────────────────
# Pre-configure OBS Studio Flatpak to enable the Vulkan/OpenGL capture plugin
# system-wide by default.
mkdir -p /etc/flatpak/overrides
cat >/etc/flatpak/overrides/com.obsproject.Studio <<'OBSEOF'
[Environment]
OBS_VKCAPTURE=1
OBSEOF
