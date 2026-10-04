#!/usr/bin/bash
# Based directly on Bazzite's installer/build.sh
# Ref: https://github.com/ublue-os/bazzite/blob/main/installer/build.sh

set -euxo pipefail

# shellcheck source=build_files/scripts/lib/plymouth-initrd-checks.sh disable=SC1091
source /src/build_files/scripts/lib/plymouth-initrd-checks.sh
# shellcheck source=build_files/scripts/lib/dracut-modules.sh disable=SC1091
source /src/build_files/scripts/lib/dracut-modules.sh

# Tools required by the live installer's NTFS shrink-and-install path.
if command -v dnf5 >/dev/null 2>&1; then
	dnf5 install -y ntfs-3g parted btrfs-progs gdisk
	dnf5 clean all
else
	dnf install -y ntfs-3g parted btrfs-progs gdisk
	dnf clean all
fi
# Reproducibility anchor: these payload tools float on upstream (no EVR
# pins — old Fedora builds are dropped, so pins would rot). Record exactly
# what resolved so an NTFS-shrink behavior change bisects to a NEVRA.
rpm -q --queryformat '%{NAME}-%{EPOCH}:%{VERSION}-%{RELEASE}.%{ARCH}\n' ntfs-3g parted btrfs-progs gdisk

SOURCE_TAG=${SOURCE_TAG:?}
BASE_IMAGE=${BASE_IMAGE:?}
INSTALL_SOURCE_IMAGE=${INSTALL_SOURCE_IMAGE:-${BASE_IMAGE}}

# bwrap tries to write /proc/sys/user/max_user_namespaces which is mounted as ro
mount -o remount,rw /proc/sys

# ── Native installer runtime ──────────────────────────────────────────────────
# The Containerfile supplies the Rust shell, daemon, and typed execution
# helper. No Python installer package is installed into the live image.
install -Dm755 /src/build_files/kyth-launch-installer /usr/bin/kyth-launch-installer
install -Dm644 /src/build_files/kyth-installerd.service /usr/lib/systemd/system/kyth-installerd.service
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

# Keep the live ISO small: the installer image is about 8.5 GiB compressed and
# must be fetched from its signed registry source during installation. Never
# copy its layers into the ISO payload.
source_imgref="${INSTALL_SOURCE_IMAGE}"
case "${source_imgref}" in
	docker://*)
		source_imgref="docker://${source_imgref#docker://}"
		;;
	containers-storage:*|oci:*|dir:*|ostree:*)
		echo "ERROR: live ISO installer source must be a registry image reference." >&2
		exit 1
		;;
	*)
		source_imgref="docker://${source_imgref}"
		;;
esac
registry_image="${source_imgref#docker://}"
case "${source_imgref#docker://}" in
	localhost:*|127.0.0.1:*|\[::1\]:*)
		echo "ERROR: live ISO installer source must be reachable from the booted live system; loopback registries are not supported." >&2
		exit 1
		;;
esac
source_digest="$(skopeo inspect --format '{{.Digest}}' "${source_imgref}")"
case "${source_digest}" in
	sha256:[0-9a-f][0-9a-f]*) ;;
	*)
		echo "ERROR: registry installer image has no valid sha256 digest: ${source_digest}" >&2
		exit 1
		;;
esac
expected_digest="${INSTALL_SOURCE_IMAGE##*@}"
if [[ "${expected_digest}" != sha256:* ]]; then
	echo "ERROR: live ISO installer source must be pinned by digest: ${INSTALL_SOURCE_IMAGE}" >&2
	exit 1
fi
if [[ "${expected_digest}" != "${source_digest}" ]]; then
	echo "ERROR: installer source digest mismatch: expected ${expected_digest}, registry reports ${source_digest}" >&2
	exit 1
fi
release_digest="${source_digest}"
target_image="ghcr.io/kyth-os/kyth:${SOURCE_TAG}"

# ── Registry signature gate: cosign-verify at ISO build time ─────────────────
# The installer daemon re-verifies this digest and signature bundle before
# any bootc install.
signature_bundle="/usr/share/kyth/image.sig.bundle.json"
signature_state="local"
signature_digest=""
cosign_registry_ref="${registry_image%@*}"
if [ -n "${cosign_registry_ref}" ]; then
	# The signer (supply-chain.yml via setup-cosign) uses cosign v2.6.1,
	# which stores signatures as .sig tags. The verifier must speak the
	# same format: distro-packaged cosign is v3 (bundle/referrers only),
	# which cannot see v2 .sig tags, so a distro install fails
	# every build at this gate. Keep the pinned v2 binary in /tmp and invoke
	# it by absolute path: some base images have a non-directory /usr/local.
	cosign_transient="yes"
	cosign_version="2.6.1"
	cosign_sha256="064954c5d8c7e3b28188eee5b1727b31c411550bc5fefd41aa672d3c761d103a"
	cosign_bin="/tmp/kyth-cosign"
	curl -sfL "https://github.com/sigstore/cosign/releases/download/v${cosign_version}/cosign-linux-amd64" -o "${cosign_bin}"
	echo "${cosign_sha256}  ${cosign_bin}" | sha256sum -c -
	chmod 0755 "${cosign_bin}"
	cosign_identity="${KYTH_COSIGN_IDENTITY:-^https://github.com/.+/\.github/workflows/supply-chain\.yml@refs/heads/(main|testing)$}"
	cosign_issuer="https://token.actions.githubusercontent.com"
	# cosign's TUF client bootstraps its cache with a plain mkdir of the
	# cache root: with HOME=/root (which already exists in bootc payload
	# images) that fatals as "mkdir /root: file exists" before any network
	# happens, so no ISO build could ever pass this gate. Point TUF at a
	# fresh directory; verification itself is unchanged.
	export TUF_ROOT="${TUF_ROOT:-/tmp/kyth-sigstore-tuf}"
	mkdir -p "${TUF_ROOT}"
	# The TUF root refresh and registry reads flake on shared runners; retry a
	# few times before failing. The gate itself stays hard — after retries it
	# still exits 1, never records "verified" without a real verification.
	cosign_verified=""
	for cosign_attempt in 1 2 3; do
		if "${cosign_bin}" verify \
			--certificate-identity-regexp "${cosign_identity}" \
			--certificate-oidc-issuer "${cosign_issuer}" \
			"${cosign_registry_ref}@${source_digest}"; then
			cosign_verified="yes"
			break
		fi
		echo "WARNING: cosign verification attempt ${cosign_attempt}/3 failed; retrying in 15s" >&2
		sleep 15
	done
	[ -n "${cosign_verified}" ] \
		|| { echo "ERROR: cosign verification failed for ${cosign_registry_ref}@${source_digest} after 3 attempts" >&2; exit 1; }
	signatures=""
	for cosign_attempt in 1 2 3; do
		if signatures="$("${cosign_bin}" download signature "${cosign_registry_ref}@${source_digest}")" && [ -n "${signatures}" ]; then
			break
		fi
		echo "WARNING: signature bundle download attempt ${cosign_attempt}/3 failed or empty; retrying in 15s" >&2
		sleep 15
	done
	[ -n "${signatures}" ] \
		|| { echo "ERROR: could not download signature bundle for ${cosign_registry_ref}@${source_digest} after 3 attempts" >&2; exit 1; }
	signatures_json="$(printf '%s\n' "${signatures}" | sed -e 's/^/"/' -e 's/$/"/' | paste -sd, -)"
	printf '{"schema_version":1,"digest":"%s","release_digest":"%s","source_image":"%s","identity":"%s","issuer":"%s","signatures":[%s]}\n' \
		"${source_digest}" "${release_digest}" "${INSTALL_SOURCE_IMAGE}" \
		"${cosign_identity}" "${cosign_issuer}" "${signatures_json}" \
		>"${signature_bundle}"
	chmod 0644 "${signature_bundle}"
	signature_digest="sha256:$(sha256sum "${signature_bundle}" | awk '{print $1}')"
	signature_state="verified"
	if [ -n "${cosign_transient}" ]; then
		rm -f "${cosign_bin}"
	fi
fi
printf 'KYTH_SOURCE_IMAGE=%s@%s\nKYTH_TARGET_IMAGE=%s\nKYTH_SOURCE_DIGEST=%s\nKYTH_INSTALLER_SOCKET=/run/kyth-installer/api.sock\nKYTH_INSTALLER_SOCKET_GROUP=liveuser\nKYTH_INSTALLER_TOKEN_FILE=/run/kyth-installer/session-token\n' \
	"${registry_image%@*}" "${source_digest}" "${target_image}" "${source_digest}" >/etc/kyth-installer.env
printf '{"schema_version":1,"digest":"%s","release_digest":"%s","target_image":"%s","source_image":"%s","signature":"%s","signature_digest":"%s"}\n' \
	"${source_digest}" "${release_digest}" "${target_image}" "${INSTALL_SOURCE_IMAGE}" \
	"${signature_state}" "${signature_digest}" \
	>/usr/share/kyth/image-source.json

# Install live-only packages in one transaction so dependency solving and
# repository metadata work happen once. Browsers from the installed image are
# intentionally deferred to Flatpak first-boot setup.
dnf install -y \
	webkit2gtk4.1 \
	gtk3 \
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

# Plasma normally starts the PAM secrets-provider bridge during login. The live
# account has no persistent secrets, so keep both bridges (KWallet and the F45
# oo7 provider) out of its autologin session.
for pam_file in /etc/pam.d/sddm-autologin /etc/pam.d/plasmalogin-autologin /usr/lib/pam.d/plasmalogin-autologin; do
	[ -f "${pam_file}" ] && sed -i '/pam_kwallet/d; /pam_oo7/d' "${pam_file}"
done
mkdir -p /etc/xdg/autostart /etc/systemd/user
cat >/etc/xdg/autostart/pam_kwallet_init.desktop <<'EOF'
[Desktop Entry]
Type=Application
Hidden=true
EOF
ln -sf /dev/null /etc/systemd/user/plasma-kwallet-pam.service

install -Dm755 /src/build_files/scripts/kyth-live-owe-wifi-setup.sh \
	/usr/libexec/kyth-live-owe-wifi-setup

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
export KWIN_COMPOSE=Q
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
# Live-session ephemerality notice: the live desktop runs on an in-memory
# overlay, so files, settings, and installed apps vanish on reboot. This
# runs only on live boots (livesys-session-extra never executes on an
# installed system), so the notice cannot leak onto installed machines.
mkdir -p /etc/motd.d /etc/issue.d
cat > /etc/motd.d/kyth-live-session <<'MOTDEOF'
*******************************************************************************
 KythOS live session — everything here is ephemeral.
 Files, settings, and installed apps are lost on reboot.
 To keep anything, install KythOS to this computer first.
*******************************************************************************
MOTDEOF
printf '%s\n' '' 'KythOS live session — ephemeral: all changes are lost on reboot.' '' \
    > /etc/issue.d/kyth-live-session.conf
chmod 0644 /etc/motd.d/kyth-live-session /etc/issue.d/kyth-live-session.conf
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
	--add "${KYTH_DRACUT_MODULES} ${KYTH_DRACUT_LIVE_EXTRA}" \
	--include "${kyth_plymouth_include_root}" / \
	"/usr/lib/modules/${kernel}/initramfs.img" "${kernel}"
rm -rf "${kyth_plymouth_include_root}"

initrd_listing="$(mktemp)"
if command -v lsinitrd >/dev/null 2>&1; then
	initrd_img="/usr/lib/modules/${kernel}/initramfs.img"
	lsinitrd "${initrd_img}" >"${initrd_listing}"

	# Each entry is "pattern|message"; message is appended to the standard
	# "ERROR: live initramfs ..." prefix.
	listing_checks=(
		'usr/share/plymouth/themes/kyth/kyth.plymouth|does not contain KythOS Plymouth theme'
		'usr/share/plymouth/themes/kyth/kyth.script|does not contain KythOS Plymouth script'
		'usr/share/plymouth/themes/kyth/kyth-logo.png|does not contain KythOS Plymouth logo'
		'usr/share/plymouth/themes/default.plymouth|does not force the KythOS Plymouth default theme'
	)
	for entry in "${listing_checks[@]}"; do
		plymouth_require_pattern "${initrd_listing}" "${entry%%|*}" "live initramfs ${entry#*|}"
	done

	plymouth_require_match \
		<(lsinitrd -f /usr/share/pixmaps/system-logo-white.png "${initrd_img}") \
		/usr/share/kyth/branding/transparent-watermark.png \
		"live initramfs still contains distro Plymouth system logo"

	# Theme=kyth/ShowDelay=0/DeviceTimeout=8 must hold in both the Plymouth
	# defaults baked into the initramfs and the daemon config that overrides
	# them, so the same three patterns are checked against both sources.
	daemon_patterns=(
		'^Theme=kyth$|does not force Theme=kyth'
		'^ShowDelay=0$|does not draw immediately'
		'^DeviceTimeout=8$|is missing DeviceTimeout=8'
	)
	for entry in "${daemon_patterns[@]}"; do
		plymouth_require_pattern \
			<(lsinitrd -f /usr/share/plymouth/plymouthd.defaults "${initrd_img}") \
			"${entry%%|*}" "live initramfs Plymouth defaults ${entry#*|}"
	done

	initrd_extract="$(mktemp -d)"
	(cd "${initrd_extract}" && lsinitrd --unpack "${initrd_img}" etc/plymouth/plymouthd.conf)
	for entry in "${daemon_patterns[@]}"; do
		grep -q "${entry%%|*}" "${initrd_extract}/etc/plymouth/plymouthd.conf" || {
			echo "ERROR: live initramfs Plymouth daemon config ${entry#*|}" >&2
			rm -rf "${initrd_extract}"
			exit 1
		}
	done
	rm -rf "${initrd_extract}"

	plymouth_forbid_fallback_theme "${initrd_listing}" "Plymouth fallback theme leaked into live initramfs"
fi
rm -f "${initrd_listing}"

# ── livesys-scripts ───────────────────────────────────────────────────────────
sed -i 's/^livesys_session=.*/livesys_session="kde"/' /etc/sysconfig/livesys
systemctl enable livesys.service livesys-late.service

# ── Log straight into the live desktop ────────────────────────────────────────
# Live media boots on hardware that has never run this OS. Autologin follows
# DefaultSession (Plasma Wayland) plus live.sh llvmpipe/QPainter, including the
# ISO's nomodeset / Basic Graphics entry. Do not pin Session= here.
mkdir -p /etc/plasmalogin.conf.d
cat >/etc/plasmalogin.conf.d/20-kyth-live-autologin.conf <<'EOF'
[Autologin]
User=liveuser
Relogin=false
EOF

# ── Disable services inappropriate for live ───────────────────────────────────
# Live-only differences are scoped to the live kernel cmdline (kyth.live=1,
# see installer/iso.yaml): the live payload image IS the installed system,
# so a hard mask (ln -sf /dev/null) would persist into installed systems and
# block those units there forever. Each unit instead gets a drop-in that
# skips it only on live boots; installed boots follow normal enablement.
# `disable` keeps them from auto-starting anywhere by default.
for unit in \
	ostree-remount.service \
	rpm-ostree-countme.service rpm-ostree-countme.timer \
	bootc-fetch-apply-updates.service bootc-fetch-apply-updates.timer \
	systemd-firstboot.service systemd-oomd.service \
	kyth-default-flatpaks.service kyth-flathub-setup.service \
	kyth-proton-cachyos-update.service kyth-proton-cachyos-update.timer \
	kyth-hw-setup.service kyth-local-bin-migrate.service \
	kyth-duperemove.service kyth-duperemove.timer \
	kyth-enroll-mok.service sddm.service akmods.service \
	plasma-setup.service scxd.service \
	fwupd.service fwupd-refresh.service fwupd-refresh.timer; do
	systemctl disable "${unit}" 2>/dev/null || true
	mkdir -p "/etc/systemd/system/${unit}.d"
	printf '%s\n' '[Unit]' 'ConditionKernelCommandLine=!kyth.live=1' \
		>"/etc/systemd/system/${unit}.d/kyth-live-only.conf"
done

# The acceptance unit is intentionally present in the installed image. Keep
# its enablement explicit after the live-image service masking above so the
# QEMU qualification guest starts automatically at graphical.target.
install -m 0644 /src/build_files/kyth-vm-acceptance.service \
	/usr/lib/systemd/system/kyth-vm-acceptance.service
systemctl enable kyth-vm-acceptance.service

# Live-session presets may remove target wants links at first boot. Tie the
# acceptance guest directly to the live-session late setup service as well,
# so QEMU qualification remains runnable without relying on those links.
mkdir -p /etc/systemd/system/livesys-late.service.d
cat >/etc/systemd/system/livesys-late.service.d/kyth-vm-acceptance.conf <<'EOF'
[Unit]
Wants=kyth-vm-acceptance.service
EOF

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

# ── Scoped sudo for liveuser (least-privilege) ───────────────────────────────
# The packaged installer is the sole privileged entry point. It validates the
# installation request before invoking partitioning/bootc tools as its own root
# children. Do not grant those general-purpose tools separately: many of them
# are direct arbitrary-file-write or command-execution primitives.
#
# The empty sudoers argument string means only an argument-free graphical
# launch is passwordless. Headless/answer-file invocations require normal sudo
# authentication. Preserve only the display and image-selection environment
# needed by the native Rust shell and root-owned daemon.
install -Dm440 /dev/stdin /etc/sudoers.d/liveuser-live <<'EOF'
Defaults:liveuser env_keep += "DISPLAY WAYLAND_DISPLAY XAUTHORITY XDG_RUNTIME_DIR DBUS_SESSION_BUS_ADDRESS XDG_SESSION_TYPE LIBGL_ALWAYS_SOFTWARE GALLIUM_DRIVER MESA_LOADER_DRIVER_OVERRIDE QT_QUICK_BACKEND"
liveuser ALL=(root) NOPASSWD: /usr/bin/kyth-launch-installer ""
EOF
# Validate sudoers syntax — fail the ISO build instead of shipping a broken file.
visudo -c -f /etc/sudoers.d/liveuser-live

# ── Timezone + machine-id (same as Bazzite) ───────────────────────────────────
rm -f /etc/localtime
ln -sf /usr/share/zoneinfo/UTC /etc/localtime
echo "uninitialized" >/etc/machine-id

# ── EFI binaries for ISO boot (exactly as Bazzite does it) ───────────────────
mkdir -p /boot/efi
cp -av /usr/lib/efi/*/*/EFI /boot/efi/
cp -v /boot/efi/EFI/fedora/grubx64.efi /boot/efi/EFI/BOOT/fbx64.efi || true

# ── iso.yaml for the GRUB menu ────────────────────────────────────────────────
mkdir -p /usr/lib/bootc-image-builder /etc/kyth
cp /src/installer/iso.yaml /usr/lib/bootc-image-builder/iso.yaml
cp /src/installer/iso.yaml /etc/kyth/iso.yaml

dnf clean all
