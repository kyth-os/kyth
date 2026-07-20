# shellcheck shell=bash
# Bootc kernel arguments are written in build_base/build.sh.
# This script handles post-upgrade Plymouth guard only.

install -Dm0755 /ctx/scripts/plymouth-branding-guard.sh \
	/usr/libexec/kyth-plymouth-branding-guard
/usr/libexec/kyth-plymouth-branding-guard \
	/ctx/branding/transparent-watermark.svg

mkdir -p /etc/dracut.conf.d
if [[ -f /etc/dracut.conf.d/99-kyth.conf ]]; then
	grep -q 'add_dracutmodules+=.*kyth-plymouth' /etc/dracut.conf.d/99-kyth.conf ||
		printf '\nadd_dracutmodules+=" kyth-plymouth "\n' >>/etc/dracut.conf.d/99-kyth.conf
else
	cat >/etc/dracut.conf.d/99-kyth.conf <<'DRACUTEOF'
add_dracutmodules+=" ostree drm plymouth kyth-plymouth "
DRACUTEOF
fi
grep -q 'force_add_dracutmodules+=.*kyth-plymouth' /etc/dracut.conf.d/99-kyth.conf ||
	printf 'force_add_dracutmodules+=" kyth-plymouth "\n' >>/etc/dracut.conf.d/99-kyth.conf

cat >/usr/lib/systemd/system/kyth-boot-splash-kargs.service <<'SPLASHKARGSEOF'
[Unit]
Description=KythOS boot splash kernel argument migration
ConditionPathExists=!/var/lib/kyth/boot-splash-kargs-v2
After=local-fs.target

[Service]
Type=oneshot
ExecStart=/usr/bin/bash -c 'set -e; mkdir -p /var/lib/kyth; if command -v grubby >/dev/null 2>&1; then grubby --update-kernel=ALL --remove-args="console=tty0 console=ttyS0,115200"; grubby --update-kernel=ALL --args="quiet rhgb splash rd.plymouth=1 plymouth.enable=1 plymouth.ignore-serial-consoles systemd.show_status=false rd.systemd.show_status=false loglevel=3 rd.udev.log_level=3 vt.global_cursor_default=0 threadirqs split_lock_detect=off rootflags=noatime,compress=zstd:1,ssd,discard=async,commit=30 amdgpu.ppfeaturemask=0xffffffff pcie_aspm=performance"; fi; touch /var/lib/kyth/boot-splash-kargs-v2'

[Install]
WantedBy=multi-user.target
SPLASHKARGSEOF
systemctl enable kyth-boot-splash-kargs.service 2>/dev/null || true

install -d -m 0755 /usr/libexec
install -m 0755 /ctx/kyth-boot-branding-guard /usr/libexec/kyth-boot-branding-guard

cat >/usr/lib/systemd/system/kyth-boot-branding.service <<'BOOTBRANDINGSERVICEEOF'
[Unit]
Description=Refresh KythOS bootloader branding
After=local-fs.target

[Service]
Type=oneshot
ExecStart=/usr/libexec/kyth-boot-branding-guard

[Install]
WantedBy=multi-user.target
BOOTBRANDINGSERVICEEOF
systemctl enable kyth-boot-branding.service 2>/dev/null || true

cat >/usr/lib/systemd/system/kyth-boot-branding.path <<'BOOTBRANDINGPATHEOF'
[Unit]
Description=Watch bootloader entries for KythOS branding repairs

[Path]
PathModified=/boot/loader/entries
PathModified=/boot/efi/loader/entries
Unit=kyth-boot-branding.service

[Install]
WantedBy=multi-user.target
BOOTBRANDINGPATHEOF
systemctl enable kyth-boot-branding.path 2>/dev/null || true

install -m 0755 /ctx/kyth-refresh-boot-splash-initramfs /usr/libexec/kyth-refresh-boot-splash-initramfs

cat >/usr/lib/systemd/system/kyth-boot-splash-initramfs.service <<'SPLASHINITRDEOF'
[Unit]
Description=Refresh KythOS boot splash initramfs
After=local-fs.target ostree-remount.service
DefaultDependencies=no

[Service]
Type=oneshot
ExecStart=/usr/libexec/kyth-refresh-boot-splash-initramfs

[Install]
WantedBy=multi-user.target
SPLASHINITRDEOF
systemctl enable kyth-boot-splash-initramfs.service 2>/dev/null || true

cat >/usr/lib/systemd/system/kyth-firstboot-notice.service <<'FBOOTEOF'
[Unit]
Description=KythOS first-boot Plymouth notice
After=plymouth-start.service local-fs.target ostree-remount.service
Before=plymouth-quit.service
DefaultDependencies=no
ConditionPathExists=!/var/lib/kyth/first-boot-done

[Service]
Type=oneshot
ExecStart=/usr/bin/bash -c 'mkdir -p /var/lib/kyth && touch /var/lib/kyth/first-boot-done && plymouth message --text="After login, open the KythOS System Hub to finish installing your preferred software."'

[Install]
WantedBy=basic.target
FBOOTEOF
systemctl enable kyth-firstboot-notice.service 2>/dev/null || true
