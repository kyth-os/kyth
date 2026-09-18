# shellcheck shell=bash
# Bootc kernel arguments are written in build_base/build.sh.
# This script handles post-upgrade Plymouth guard only.

install -Dm0755 /ctx/scripts/plymouth-branding-guard.sh \
	/usr/libexec/kyth-plymouth-branding-guard
/usr/libexec/kyth-plymouth-branding-guard \
	/ctx/branding/transparent-watermark.svg

# Pre-existing installs predate the image kargs.d drop-in, so converge them
# with a helper that writes the same splash set to /etc/bootc/kargs.d (the
# local-override layer bootc merges with /usr/lib/bootc/kargs.d at deployment
# time; /usr is read-only on ostree, so the image path cannot be written from
# here). It takes effect on the next staged update, not the running boot —
# that is fine, the running BLS entries already carry these args or predate
# the splash.
#
# Deliberately additive-only: this never invokes the bootloader editor to
# remove args. GPU and power tuning (amdgpu.ppfeaturemask, pcie_aspm, ...)
# now live in the versioned hardware policy and user tunables, and a blanket
# removal would also wipe flags the USER set deliberately. Never strip user kargs.
#
# NOTE: keep the kargs list below in sync with /usr/lib/bootc/kargs.d/99-kyth.toml
# in build_base/build.sh.
write_config /usr/libexec/kyth-boot-splash-kargs-apply 0755 <<'KARGSAPPLYEOF'
#!/usr/bin/bash
set -e
mkdir -p /var/lib/kyth /etc/bootc/kargs.d
/usr/libexec/kyth-finalize-staged prepare-boot >/dev/null 2>&1 || true
cat >/etc/bootc/kargs.d/99-kyth-splash.toml <<'TOMLEOF'
kargs = ["quiet", "rhgb", "splash", "rd.plymouth=1", "plymouth.enable=1", "plymouth.ignore-serial-consoles", "systemd.show_status=false", "rd.systemd.show_status=false", "loglevel=3", "rd.udev.log_level=3", "vt.global_cursor_default=0", "threadirqs", "split_lock_detect=off", "rootflags=noatime,compress=zstd:1,ssd,discard=async"]
TOMLEOF
touch /var/lib/kyth/boot-splash-kargs-v4
KARGSAPPLYEOF

write_config /usr/lib/systemd/system/kyth-boot-splash-kargs.service <<'SPLASHKARGSEOF'
[Unit]
Description=KythOS boot splash kernel arguments via bootc kargs.d
ConditionPathExists=!/var/lib/kyth/boot-splash-kargs-v4
After=local-fs.target kyth-boot-rw.service

[Service]
Type=oneshot
RemainAfterExit=yes
TimeoutStartSec=60
ExecStart=/usr/libexec/kyth-boot-splash-kargs-apply

[Install]
WantedBy=multi-user.target
SPLASHKARGSEOF
systemctl enable kyth-boot-splash-kargs.service 2>/dev/null || true

install -d -m 0755 /usr/libexec
install -m 0755 /ctx/kyth-boot-branding-guard /usr/libexec/kyth-boot-branding-guard

write_config /usr/lib/systemd/system/kyth-boot-branding.service <<'BOOTBRANDINGSERVICEEOF'
[Unit]
Description=Refresh KythOS bootloader branding
After=local-fs.target kyth-boot-rw.service

[Service]
Type=oneshot
RemainAfterExit=yes
TimeoutStartSec=60
ExecStart=/usr/libexec/kyth-boot-branding-guard

[Install]
WantedBy=multi-user.target
BOOTBRANDINGSERVICEEOF
systemctl enable kyth-boot-branding.service 2>/dev/null || true

write_config /usr/lib/systemd/system/kyth-boot-branding.path <<'BOOTBRANDINGPATHEOF'
[Unit]
Description=Watch bootloader entries for KythOS branding repairs

[Path]
PathModified=/boot/loader/entries
PathModified=/boot/efi/loader/entries
Unit=kyth-boot-branding.service
TriggerLimitIntervalSec=10
TriggerLimitBurst=5

[Install]
WantedBy=multi-user.target
BOOTBRANDINGPATHEOF
systemctl enable kyth-boot-branding.path 2>/dev/null || true

# kyth-refresh-boot-splash-initramfs is the native Rust binary copied from
# the hub-web-builder stage; no Python launcher remains in the source tree.

write_config /usr/lib/systemd/system/kyth-boot-splash-initramfs.service <<'SPLASHINITRDEOF'
[Unit]
Description=Refresh KythOS boot splash initramfs
After=local-fs.target ostree-remount.service kyth-boot-rw.service
DefaultDependencies=no

[Service]
Type=oneshot
RemainAfterExit=yes
TimeoutStartSec=300
# '-' so a dracut/inspect failure cannot list this unit as failed every
# boot. refresh() already no-ops when /boot stays read-only.
ExecStart=-/usr/libexec/kyth-refresh-boot-splash-initramfs

[Install]
WantedBy=multi-user.target
SPLASHINITRDEOF
systemctl enable kyth-boot-splash-initramfs.service 2>/dev/null || true

