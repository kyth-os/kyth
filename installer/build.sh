#!/usr/bin/bash
# Based directly on Bazzite's installer/build.sh
# Ref: https://github.com/ublue-os/bazzite/blob/main/installer/build.sh

set -exo pipefail

# Tools required by the live installer's NTFS shrink-and-install path.
if command -v dnf5 >/dev/null 2>&1; then
	dnf5 install -y ntfs-3g parted btrfs-progs
	dnf5 clean all
else
	dnf install -y ntfs-3g parted btrfs-progs
	dnf clean all
fi


SOURCE_TAG=${SOURCE_TAG:?}

# bwrap tries to write /proc/sys/user/max_user_namespaces which is mounted as ro
mount -o remount,rw /proc/sys

# ── KythOS installer binaries ─────────────────────────────────────────────────
install -Dm755 /src/build_files/kyth-installer /usr/bin/kyth-installer
install -Dm755 /src/build_files/kyth-launch-installer /usr/bin/kyth-launch-installer
install -Dm755 /src/build_files/kyth-partition-install.sh /usr/bin/kyth-partition-install
install -Dm755 /src/build_files/scripts/plymouth-branding-guard.sh \
	/usr/libexec/kyth-plymouth-branding-guard

cat >/usr/share/applications/kyth-install.desktop <<'EOF'
[Desktop Entry]
Name=Install KythOS
Comment=Install KythOS to this computer
Exec=/usr/bin/kyth-launch-installer
Icon=kyth
Terminal=false
Type=Application
Categories=System;
EOF

printf 'KYTH_SOURCE_IMAGE=ghcr.io/mrtrick37/kyth:%s\nKYTH_TARGET_IMAGE=ghcr.io/mrtrick37/kyth:%s\n' \
	"${SOURCE_TAG}" "${SOURCE_TAG}" >/etc/kyth-installer.env

# Install live-only packages in one transaction so dependency solving and
# repository metadata work happen once. Browsers from the installed image are
# intentionally deferred to Flatpak first-boot setup.
dnf install -y \
	chromium \
	dracut-live \
	grub2-efi-x64-cdboot \
	livesys-scripts

# ── Live desktop: installer shortcut + software rendering (via /etc/skel) ────
# The installed image seeds System Hub for a user's first login. The live
# session should open the installer instead and keep the desktop uncluttered.
rm -f \
	/etc/skel/Desktop/kyth-welcome.desktop \
	/etc/skel/Desktop/system-hub.desktop \
	/etc/skel/.config/autostart/kyth-welcome.desktop
mkdir -p /etc/skel/Desktop /etc/skel/.config/autostart
cat >/etc/skel/Desktop/install-kyth.desktop <<'EOF'
[Desktop Entry]
Name=Install KythOS
Comment=Install KythOS to this computer
Exec=/usr/bin/kyth-launch-installer
Icon=kyth
Terminal=false
Type=Application
Categories=System;
EOF
chmod +x /etc/skel/Desktop/install-kyth.desktop

# The live user is ephemeral, so do not interrupt Wi-Fi setup with KWallet's
# first-use encryption wizard. Installed users keep the normal encrypted wallet.
cat >/etc/skel/.config/kwalletrc <<'EOF'
[Wallet]
Enabled=false
First Use=false
EOF

# Plasma normally starts the PAM wallet bridge during login. The live account
# has no persistent secrets, so keep that bridge out of its autologin session.
for pam_file in /etc/pam.d/sddm-autologin /usr/lib/pam.d/plasmalogin-autologin; do
	[ -f "${pam_file}" ] && sed -i '/pam_kwallet/d' "${pam_file}"
done
mkdir -p /etc/xdg/autostart /etc/systemd/user
cat >/etc/xdg/autostart/pam_kwallet_init.desktop <<'EOF'
[Desktop Entry]
Type=Application
Hidden=true
EOF
ln -sf /dev/null /etc/systemd/user/plasma-kwallet-pam.service

install -Dm755 /dev/stdin /usr/libexec/kyth-live-owe-wifi-setup <<'EOF'
#!/usr/bin/bash
set -euo pipefail

if ! grep -qw 'kyth.live=1' /proc/cmdline 2>/dev/null; then
    exit 0
fi

command -v nmcli >/dev/null 2>&1 || exit 0

LOG_FILE="/var/log/kyth-live-owe-wifi-setup.log"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >> "${LOG_FILE}"
}

log "Starting OWE Wi-Fi profile setup"

# Wait for NetworkManager to be fully operational
for _try in 1 2 3 4 5 6 7 8 9 10; do
    if nmcli general status 2>/dev/null | grep -q 'connected\|disconnected'; then
        log "NetworkManager is ready (attempt $_try/10)"
        break
    fi
    if [[ $_try -eq 10 ]]; then
        log "ERROR: NetworkManager did not become ready after 10 attempts (20 seconds)"
        exit 1
    fi
    sleep 2
done

# OWE/OWE transition-mode networks can look like plain open Wi-Fi in Plasma.
# Seed explicit Enhanced Open profiles in the ephemeral live session so guest
# networks of this type can be activated correctly.
if ! nmcli radio wifi on 2>/dev/null; then
    log "WARNING: nmcli radio wifi on failed"
fi
sleep 1

# Scan for OWE networks
declare -A owe_ssids=()
for _try in 1 2 3 4 5 6; do
    log "Scan attempt $_try/6"
    while IFS=: read -r ssid security; do
        [[ -n "${ssid}" && "${ssid}" != "--" ]] || continue
        [[ "${security}" == *OWE* ]] || continue
        owe_ssids["${ssid}"]=1
        log "Found OWE network: ${ssid}"
    done < <(nmcli --escape no -t -f SSID,SECURITY device wifi list --rescan yes 2>/dev/null || true)

    if [[ "${#owe_ssids[@]}" -gt 0 ]]; then
        log "Found OWE networks on attempt $_try/6, proceeding"
        break
    fi
    sleep 2
done

if [[ "${#owe_ssids[@]}" -eq 0 ]]; then
    log "No OWE networks found after 6 scans, exiting"
    exit 0
fi

log "Found ${#owe_ssids[@]} OWE network(s), setting up profiles"

for ssid in "${!owe_ssids[@]}"; do
    con_name="Kyth OWE ${ssid}"
    log "Processing SSID: ${ssid} (connection: ${con_name})"
    
    # Always delete and recreate to avoid state corruption on reboot
    if nmcli connection delete "${con_name}" 2>/dev/null; then
        log "Deleted existing connection: ${con_name}"
    fi

    # Create the OWE profile with all required settings
    if nmcli connection add \
        type wifi \
        ifname "*" \
        con-name "${con_name}" \
        ssid "${ssid}" \
        wifi-sec.key-mgmt owe \
        ipv4.method auto \
        ipv4.dhcp-send-hostname yes \
        ipv4.ignore-auto-dns no \
        connection.autoconnect no \
        connection.permissions "" \
        2>/tmp/kyth-owe-error.log; then
        
        # Validate the profile was created with correct settings
        key_mgmt=$(nmcli -g 802-11-wireless-security.key-mgmt connection show "${con_name}" 2>/dev/null || echo "ERROR")
        ipv4_method=$(nmcli -g ipv4.method connection show "${con_name}" 2>/dev/null || echo "ERROR")
        
        if [[ "${key_mgmt}" == "owe" && "${ipv4_method}" == "auto" ]]; then
            log "✓ Profile created successfully: ${con_name}"
        else
            log "ERROR: Profile validation failed for ${con_name}"
            log "  key-mgmt: ${key_mgmt}"
            log "  ipv4.method: ${ipv4_method}"
        fi
    else
        log "ERROR: Failed to create connection ${con_name}"
        cat /tmp/kyth-owe-error.log >> "${LOG_FILE}" 2>/dev/null || true
    fi
done

# Auto-connect if exactly one OWE network and no WiFi connected
wifi_connected=$(nmcli -t -f DEVICE,TYPE,STATE device status 2>/dev/null | grep -c ':wifi:connected' || echo 0)
if [[ "${#owe_ssids[@]}" -eq 1 && "${wifi_connected}" -eq 0 ]]; then
    for ssid in "${!owe_ssids[@]}"; do
        con_name="Kyth OWE ${ssid}"
        log "Single OWE network with no WiFi connected, attempting auto-connect: ${con_name}"
        if nmcli connection up "${con_name}" 2>/tmp/kyth-owe-error.log; then
            log "✓ Successfully brought up connection: ${con_name}"
        else
            log "ERROR: Failed to bring up ${con_name}"
            cat /tmp/kyth-owe-error.log >> "${LOG_FILE}" 2>/dev/null || true
        fi
    done
else
    log "Skipping auto-connect: ${#owe_ssids[@]} OWE networks, ${wifi_connected} WiFi connections active"
fi

log "OWE Wi-Fi profile setup complete"
EOF

cat >/etc/systemd/system/kyth-live-owe-wifi.service <<'EOF'
[Unit]
Description=Seed live ISO OWE Wi-Fi profiles
ConditionKernelCommandLine=kyth.live=1
Wants=NetworkManager.service
After=NetworkManager.service network-pre.target
Before=network.target network-online.target

[Service]
Type=oneshot
TimeoutStartSec=120
RemainAfterExit=yes
ExecStart=/usr/libexec/kyth-live-owe-wifi-setup

[Install]
WantedBy=network.target
EOF
systemctl enable kyth-live-owe-wifi.service

cat >/etc/skel/.config/autostart/kyth-installer.desktop <<'EOF'
[Desktop Entry]
Type=Application
Name=Install KythOS
Exec=/usr/bin/kyth-launch-installer
X-KDE-autostart-after=panel
Hidden=false
NoDisplay=true
EOF

mkdir -p /etc/skel/.config/plasma-workspace/env
cat >/etc/skel/.config/plasma-workspace/env/live.sh <<'EOF'
#!/bin/bash
export LIBGL_ALWAYS_SOFTWARE=1
export GALLIUM_DRIVER=llvmpipe
export MESA_LOADER_DRIVER_OVERRIDE=llvmpipe
export QT_QUICK_BACKEND=software
EOF
chmod +x /etc/skel/.config/plasma-workspace/env/live.sh

# livesys-session-extra: runs after livesys-kde sets up the KDE session
mkdir -p /var/lib/livesys
cat >/var/lib/livesys/livesys-session-extra <<'EOF'
#!/bin/sh
rm -f \
    /home/liveuser/Desktop/liveinst.desktop \
    /home/liveuser/Desktop/kyth-welcome.desktop \
    /home/liveuser/Desktop/system-hub.desktop \
    /home/liveuser/.config/autostart/kyth-welcome.desktop \
    2>/dev/null || true
mkdir -p /home/liveuser/.config
cat > /home/liveuser/.config/kwalletrc <<'WALLETRC'
[Wallet]
Enabled=false
First Use=false
WALLETRC
cat > /home/liveuser/.config/kscreenlockerrc <<'SCREENLOCKEOF'
[Daemon]
Autolock=false
LockOnResume=false
SCREENLOCKEOF
chown liveuser:liveuser \
    /home/liveuser/.config/kwalletrc \
    /home/liveuser/.config/kscreenlockerrc
[ -f /home/liveuser/Desktop/install-kyth.desktop ] && \
    chmod +x /home/liveuser/Desktop/install-kyth.desktop
EOF
chmod +x /var/lib/livesys/livesys-session-extra

# ── dracut-live + initramfs ───────────────────────────────────────────────────
# The live ISO must boot the signed Fedora kernel so it works under Secure Boot.
# CachyOS is opt-in: chosen during installation or from System Hub on the
# installed system (a bootc switch to the -cachy image), never in the live
# environment. So always pick the non-CachyOS (Fedora) kernel here, and refuse
# to build a live ISO from a CachyOS-only image rather than silently producing an
# unsignable one.
mapfile -t kernels < <(find /usr/lib/modules -mindepth 1 -maxdepth 1 -type d -printf '%f\n' | sort -V)
kernel=
for candidate in "${kernels[@]}"; do
	if [[ "${candidate}" != *cachyos* ]]; then
		kernel="${candidate}"
	fi
done
if [[ -z "${kernel}" ]]; then
	echo "ERROR: no signed Fedora kernel in /usr/lib/modules — the live ISO must use the Fedora kernel for Secure Boot. Build the ISO from the Fedora image variant, not the -cachy variant." >&2
	exit 1
fi
/usr/libexec/kyth-plymouth-branding-guard
plymouth-set-default-theme kyth
mkdir -p /etc/plymouth /usr/share/plymouth
cat >/etc/plymouth/plymouthd.conf <<'EOF'
[Daemon]
Theme=kyth
ShowDelay=0
DeviceTimeout=8
UseFirmwareBackground=false
EOF
install -m 0644 /etc/plymouth/plymouthd.conf /usr/share/plymouth/plymouthd.conf
cat >/usr/share/plymouth/plymouthd.defaults <<'EOF'
[Daemon]
Theme=kyth
ShowDelay=0
DeviceTimeout=8
UseFirmwareBackground=false
EOF
kyth_plymouth_include_root="$(mktemp -d)"
mkdir -p \
	"${kyth_plymouth_include_root}/etc/plymouth" \
	"${kyth_plymouth_include_root}/usr/share/plymouth" \
	"${kyth_plymouth_include_root}/usr/share/pixmaps"
install -m 0644 /etc/plymouth/plymouthd.conf \
	"${kyth_plymouth_include_root}/etc/plymouth/plymouthd.conf"
install -m 0644 /usr/share/plymouth/plymouthd.defaults \
	"${kyth_plymouth_include_root}/usr/share/plymouth/plymouthd.defaults"
install -m 0644 /usr/share/kyth/branding/transparent-watermark.png \
	"${kyth_plymouth_include_root}/usr/share/pixmaps/system-logo-white.png"
DRACUT_NO_XATTR=1 dracut -v --force --zstd --no-hostonly \
	--add "kyth-plymouth plymouth dmsquash-live dmsquash-live-autooverlay" \
	--include "${kyth_plymouth_include_root}" / \
	"/usr/lib/modules/${kernel}/initramfs.img" "${kernel}"
rm -rf "${kyth_plymouth_include_root}"

initrd_listing="$(mktemp)"
if command -v lsinitrd >/dev/null 2>&1; then
	lsinitrd "/usr/lib/modules/${kernel}/initramfs.img" >"${initrd_listing}"
	grep -q 'usr/share/plymouth/themes/kyth/kyth.plymouth' "${initrd_listing}" || {
		echo "ERROR: live initramfs does not contain KythOS Plymouth theme" >&2
		exit 1
	}
	grep -q 'usr/share/plymouth/themes/kyth/kyth.script' "${initrd_listing}" || {
		echo "ERROR: live initramfs does not contain KythOS Plymouth script" >&2
		exit 1
	}
	grep -q 'usr/share/plymouth/themes/kyth/kyth-logo.png' "${initrd_listing}" || {
		echo "ERROR: live initramfs does not contain KythOS Plymouth logo" >&2
		exit 1
	}
	lsinitrd -f /usr/share/pixmaps/system-logo-white.png "/usr/lib/modules/${kernel}/initramfs.img" | cmp -s - /usr/share/kyth/branding/transparent-watermark.png || {
		echo "ERROR: live initramfs still contains distro Plymouth system logo" >&2
		exit 1
	}
	grep -q 'usr/share/plymouth/themes/default.plymouth' "${initrd_listing}" || {
		echo "ERROR: live initramfs does not force the KythOS Plymouth default theme" >&2
		exit 1
	}
	lsinitrd -f /usr/share/plymouth/plymouthd.defaults "/usr/lib/modules/${kernel}/initramfs.img" | grep -q '^Theme=kyth$' || {
		echo "ERROR: live initramfs Plymouth defaults do not force Theme=kyth" >&2
		exit 1
	}
	lsinitrd -f /usr/share/plymouth/plymouthd.defaults "/usr/lib/modules/${kernel}/initramfs.img" | grep -q '^ShowDelay=0$' || {
		echo "ERROR: live initramfs Plymouth defaults do not draw immediately" >&2
		exit 1
	}
	lsinitrd -f /usr/share/plymouth/plymouthd.defaults "/usr/lib/modules/${kernel}/initramfs.img" | grep -q '^DeviceTimeout=8$' || {
		echo "ERROR: live initramfs Plymouth defaults are missing DeviceTimeout=8" >&2
		exit 1
	}
	initrd_extract="$(mktemp -d)"
	(cd "${initrd_extract}" && lsinitrd --unpack "/usr/lib/modules/${kernel}/initramfs.img" etc/plymouth/plymouthd.conf)
	grep -q '^Theme=kyth$' "${initrd_extract}/etc/plymouth/plymouthd.conf" || {
		echo "ERROR: live initramfs Plymouth daemon config does not force Theme=kyth" >&2
		rm -rf "${initrd_extract}"
		exit 1
	}
	grep -q '^ShowDelay=0$' "${initrd_extract}/etc/plymouth/plymouthd.conf" || {
		echo "ERROR: live initramfs Plymouth daemon config does not draw immediately" >&2
		rm -rf "${initrd_extract}"
		exit 1
	}
	grep -q '^DeviceTimeout=8$' "${initrd_extract}/etc/plymouth/plymouthd.conf" || {
		echo "ERROR: live initramfs Plymouth daemon config is missing DeviceTimeout=8" >&2
		rm -rf "${initrd_extract}"
		exit 1
	}
	rm -rf "${initrd_extract}"
	if grep -Ei 'usr/share/plymouth/themes/(bgrt-fedora|bgrt|spinner)(/|$)' "${initrd_listing}" >&2; then
		echo "ERROR: Plymouth fallback theme leaked into live initramfs" >&2
		exit 1
	fi
fi
rm -f "${initrd_listing}"

# ── livesys-scripts ───────────────────────────────────────────────────────────
sed -i 's/^livesys_session=.*/livesys_session="kde"/' /etc/sysconfig/livesys
systemctl enable livesys.service livesys-late.service

# ── Log straight into the live desktop ────────────────────────────────────────
# Unlike the installed system (kyth-configure-session picks Wayland on bare
# metal, X11 only inside VMs), the live session always forces X11 + llvmpipe
# software rendering (see the plasma-workspace/env/live.sh skel above). Live
# media boots on hardware that has never run this OS and whose GPU/DRM/KMS
# support is unverified, so we trade rendering performance/theme fidelity for
# a login that is guaranteed to come up everywhere. This is intentional, not
# an oversight.
mkdir -p /etc/sddm.conf.d
cat >/etc/sddm.conf.d/20-kyth-live-autologin.conf <<'EOF'
[Autologin]
User=liveuser
Session=plasmax11.desktop
Relogin=false
EOF

# ── Disable services inappropriate for live ───────────────────────────────────
for unit in \
	ostree-remount.service \
	rpm-ostree-countme.service rpm-ostree-countme.timer \
	bootc-fetch-apply-updates.service bootc-fetch-apply-updates.timer \
	systemd-firstboot.service systemd-oomd.service \
	kyth-default-flatpaks.service kyth-flathub-setup.service \
	kyth-ge-proton-update.service kyth-ge-proton-update.timer \
	kyth-hw-setup.service kyth-local-bin-migrate.service \
	kyth-topgrade-migrate.service kyth-duperemove.service kyth-duperemove.timer \
	kyth-enroll-mok.service plasmalogin.service akmods.service \
	plasma-setup.service com.system76.Scheduler.service \
	scxd.service ananicy-cpp.service \
	fwupd.service fwupd-refresh.service fwupd-refresh.timer; do
	systemctl disable "${unit}" 2>/dev/null || true
	ln -sf /dev/null "/etc/systemd/system/${unit}"
done

# ── Larger /var/tmp for bootc install to-disk ─────────────────────────────────
rm -rf /var/tmp
mkdir /var/tmp
cat >/etc/systemd/system/var-tmp.mount <<'EOF'
[Unit]
Description=Larger tmpfs for /var/tmp on live system

[Mount]
What=tmpfs
Where=/var/tmp
Type=tmpfs
Options=size=50%,nr_inodes=1m

[Install]
WantedBy=local-fs.target
EOF
systemctl enable var-tmp.mount

# ── Passwordless sudo for liveuser ────────────────────────────────────────────
install -Dm440 /dev/stdin /etc/sudoers.d/liveuser-live <<'EOF'
liveuser ALL=(ALL) NOPASSWD: ALL
EOF

# ── Timezone + machine-id (same as Bazzite) ───────────────────────────────────
rm -f /etc/localtime
ln -sf /usr/share/zoneinfo/UTC /etc/localtime
echo "uninitialized" >/etc/machine-id

# ── EFI binaries for ISO boot (exactly as Bazzite does it) ───────────────────
mkdir -p /boot/efi
cp -av /usr/lib/efi/*/*/EFI /boot/efi/
cp -v /boot/efi/EFI/fedora/grubx64.efi /boot/efi/EFI/BOOT/fbx64.efi || true

# ── iso.yaml for the GRUB menu ────────────────────────────────────────────────
mkdir -p /usr/lib/bootc-image-builder
cp /src/installer/iso.yaml /usr/lib/bootc-image-builder/iso.yaml

dnf clean all
