# shellcheck shell=bash
# ── Bootc kernel arguments ────────────────────────────────────────────────────
# bootc reads kargs.d entries and adds them to the BLS boot entry at install time.
mkdir -p /usr/lib/bootc/kargs.d
cat >/usr/lib/bootc/kargs.d/99-kyth.toml <<'KARGSEOF'
kargs = ["quiet", "rhgb", "splash", "rd.plymouth=1", "plymouth.enable=1", "plymouth.ignore-serial-consoles", "systemd.show_status=false", "rd.systemd.show_status=false", "loglevel=3", "rd.udev.log_level=3", "vt.global_cursor_default=0", "threadirqs"]
KARGSEOF

# The early Plymouth layer runs before the daily dnf upgrade. Run the branding
# guard again here, after every package transaction, so upgraded Plymouth theme
# packages cannot restore upstream BGRT/spinner artwork into the final image.
install -Dm0755 /ctx/scripts/plymouth-branding-guard.sh \
	/usr/libexec/kyth-plymouth-branding-guard
/usr/libexec/kyth-plymouth-branding-guard \
	/ctx/branding/transparent-watermark.svg

mkdir -p /etc/dracut.conf.d
if [[ -f /etc/dracut.conf.d/99-kyth.conf ]]; then
	grep -q 'add_dracutmodules=.*kyth-plymouth' /etc/dracut.conf.d/99-kyth.conf ||
		printf '\nadd_dracutmodules+=" kyth-plymouth "\n' >>/etc/dracut.conf.d/99-kyth.conf
else
	cat >/etc/dracut.conf.d/99-kyth.conf <<'DRACUTEOF'
add_dracutmodules+=" ostree drm plymouth kyth-plymouth "
DRACUTEOF
fi
grep -q 'force_add_dracutmodules=.*kyth-plymouth' /etc/dracut.conf.d/99-kyth.conf ||
	printf 'force_add_dracutmodules+=" kyth-plymouth "\n' >>/etc/dracut.conf.d/99-kyth.conf

# Existing installs may still have older KythOS boot entries with serial/TTY
# console arguments that make Plymouth fall back to visible boot text. This
# one-shot migration fixes the bootloader entries after the updated image boots;
# the freshly staged deployment gets the clean kargs above at install/update time.
cat >/usr/lib/systemd/system/kyth-boot-splash-kargs.service <<'SPLASHKARGSEOF'
[Unit]
Description=KythOS boot splash kernel argument migration
ConditionPathExists=!/var/lib/kyth/boot-splash-kargs-v2
After=local-fs.target

[Service]
Type=oneshot
ExecStart=/usr/bin/bash -c 'set -e; mkdir -p /var/lib/kyth; if command -v grubby >/dev/null 2>&1; then grubby --update-kernel=ALL --remove-args="console=tty0 console=ttyS0,115200"; grubby --update-kernel=ALL --args="quiet rhgb splash rd.plymouth=1 plymouth.enable=1 plymouth.ignore-serial-consoles systemd.show_status=false rd.systemd.show_status=false loglevel=3 rd.udev.log_level=3 vt.global_cursor_default=0"; fi; touch /var/lib/kyth/boot-splash-kargs-v2'

[Install]
WantedBy=multi-user.target
SPLASHKARGSEOF
systemctl enable kyth-boot-splash-kargs.service 2>/dev/null || true

# Existing installs and newly staged bootc deployments can have bootloader
# metadata generated while the image still identified as Fedora. Keep visual
# boot classes and theme icons repaired so stale BLS grub_class=fedora entries
# cannot draw Fedora artwork during the handoff to Plymouth.
mkdir -p /usr/libexec
cat >/usr/libexec/kyth-boot-branding-guard <<'BOOTBRANDINGEOF'
#!/usr/bin/env bash
set -euo pipefail

boot_was_ro=0
cleanup() {
    if [[ "${boot_was_ro}" -eq 1 ]]; then
        mount -o remount,ro /boot || true
    fi
}
trap cleanup EXIT

if findmnt -no OPTIONS /boot 2>/dev/null | tr ',' '\n' | grep -qx ro; then
    if mount -o remount,rw /boot 2>/dev/null; then
        boot_was_ro=1
    else
        echo "WARNING: /boot is read-only; bootloader branding repair will skip unwritable entries" >&2
    fi
fi

for bls_dir in /boot/loader/entries /boot/efi/loader/entries; do
    [[ -d "${bls_dir}" ]] || continue
    while IFS= read -r -d '' entry; do
        [[ -w "${entry}" ]] || continue
        sed -i \
            -e 's/^title[[:space:]]Fedora Linux/title KythOS/' \
            -e 's/^title[[:space:]]Fedora/title KythOS/' \
            -e 's/^grub_class[[:space:]].*/grub_class kythos/' \
            -e 's/^sort-key[[:space:]]fedora$/sort-key kythos/' \
            "${entry}"
        grep -q '^grub_class[[:space:]]' "${entry}" || printf 'grub_class kythos\n' >> "${entry}"
    done < <(find "${bls_dir}" -maxdepth 1 -type f -name '*.conf' -print0)
done

mkdir -p /etc/default
if [[ -f /etc/default/grub ]]; then
    if grep -q '^GRUB_DISTRIBUTOR=' /etc/default/grub; then
        sed -i 's/^GRUB_DISTRIBUTOR=.*/GRUB_DISTRIBUTOR="KythOS"/' /etc/default/grub
    else
        printf '\nGRUB_DISTRIBUTOR="KythOS"\n' >> /etc/default/grub
    fi
else
    printf 'GRUB_DISTRIBUTOR="KythOS"\n' > /etc/default/grub
fi

for grub_icon_dir in \
    /boot/grub2/themes/system/icons \
    /boot/grub2/themes/starfield/icons \
    /usr/share/grub/themes/system/icons \
    /usr/share/grub/themes/starfield/icons; do
    [[ -d "${grub_icon_dir}" ]] || continue
    [[ -w "${grub_icon_dir}" ]] || continue
    if [[ -r /usr/share/pixmaps/kythos.png ]]; then
        for icon in kyth kythos fedora gnu-linux linux; do
            install -m 0644 /usr/share/pixmaps/kythos.png "${grub_icon_dir}/${icon}.png"
        done
    fi
done

if command -v grub2-mkconfig >/dev/null 2>&1 && [[ -d /boot/grub2 ]]; then
    grub2-mkconfig -o /boot/grub2/grub.cfg >/dev/null 2>&1 || true
fi
BOOTBRANDINGEOF
chmod 0755 /usr/libexec/kyth-boot-branding-guard

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

# Existing deployments already have an initramfs in /boot. Keep it aligned with
# the current KythOS Plymouth module and repair any fallback-theme leaks.
cat >/usr/libexec/kyth-refresh-boot-splash-initramfs <<'SPLASHINITRDSCRIPTEOF'
#!/usr/bin/env bash
set -euo pipefail

state_dir=/var/lib/kyth
fingerprint_file="${state_dir}/boot-splash-initramfs.sha256"
migration_marker="${state_dir}/boot-splash-initramfs-v17"
mkdir -p "${state_dir}"

if command -v plymouth-set-default-theme >/dev/null 2>&1; then
    plymouth-set-default-theme kyth || true
fi

if [[ -x /usr/libexec/kyth-boot-branding-guard ]]; then
    /usr/libexec/kyth-boot-branding-guard || true
fi

# On deployed ostree/bootc systems /usr is normally immutable. Only refresh
# fallback assets when the filesystem is writable; the image build already
# installs the Kyth Plymouth theme and dracut module into /usr.
if [[ -w /usr/share/plymouth && -x /usr/libexec/kyth-plymouth-branding-guard ]]; then
    /usr/libexec/kyth-plymouth-branding-guard || true
fi

if [[ ! -d /etc/dracut.conf.d && -w /etc ]]; then
    mkdir -p /etc/dracut.conf.d
fi
if [[ -w /etc/dracut.conf.d ]]; then
    if [[ -f /etc/dracut.conf.d/99-kyth.conf ]]; then
        grep -q 'add_dracutmodules=.*kyth-plymouth' /etc/dracut.conf.d/99-kyth.conf || \
            printf '\nadd_dracutmodules+=" kyth-plymouth "\n' >> /etc/dracut.conf.d/99-kyth.conf
    else
        cat > /etc/dracut.conf.d/99-kyth.conf <<'DRACUTEOF'
add_dracutmodules+=" ostree drm plymouth kyth-plymouth "
DRACUTEOF
    fi
    grep -q 'force_add_dracutmodules=.*kyth-plymouth' /etc/dracut.conf.d/99-kyth.conf || \
        printf 'force_add_dracutmodules+=" kyth-plymouth "\n' >> /etc/dracut.conf.d/99-kyth.conf
fi

fingerprint_current() {
    local input
    local inputs=(
        /usr/lib/dracut/modules.d/99kyth-plymouth/module-setup.sh
        /usr/libexec/kyth-plymouth-branding-guard
        /etc/dracut.conf.d/99-kyth.conf
        /etc/plymouth/plymouthd.conf
        /usr/share/plymouth/plymouthd.defaults
        /usr/share/kyth/branding/transparent-watermark.png
        /usr/share/pixmaps/system-logo-white.png
        /usr/share/plymouth/themes/kyth/kyth.plymouth
        /usr/share/plymouth/themes/kyth/kyth.script
        /usr/share/plymouth/themes/kyth/kyth-logo.png
    )
    {
        for input in "${inputs[@]}"; do
            if [[ -r "${input}" ]]; then
                sha256sum "${input}"
            else
                printf 'MISSING  %s\n' "${input}"
            fi
        done
    } | sha256sum | awk '{print $1}'
}

collect_images() {
    images=()
    local image kernel existing seen
    shopt -s nullglob
    for image in /boot/ostree/*/initramfs-*.img /boot/initramfs-*.img; do
        kernel="${image##*/initramfs-}"
        kernel="${kernel%.img}"
        [[ -d "/usr/lib/modules/${kernel}" ]] || continue

        seen=0
        for existing in "${images[@]}"; do
            if [[ "${existing}" == "${image}" ]]; then
                seen=1
                break
            fi
        done
        [[ "${seen}" -eq 0 ]] && images+=("${image}")
    done
    shopt -u nullglob
}

image_needs_refresh() {
    local image=$1
    local defaults listing logo ok

    command -v lsinitrd >/dev/null 2>&1 || return 0
    defaults="$(mktemp /tmp/kyth-plymouth-defaults.XXXXXX)"
    listing="$(mktemp /tmp/kyth-plymouth-listing.XXXXXX)"
    logo="$(mktemp /tmp/kyth-plymouth-logo.XXXXXX)"
    ok=1

    lsinitrd -f /usr/share/plymouth/plymouthd.defaults "${image}" > "${defaults}" 2>/dev/null || ok=0
    lsinitrd -f /usr/share/pixmaps/system-logo-white.png "${image}" > "${logo}" 2>/dev/null || ok=0
    lsinitrd "${image}" > "${listing}" 2>/dev/null || ok=0
    grep -q 'usr/share/plymouth/themes/kyth/kyth.plymouth' "${listing}" || ok=0
    grep -q 'usr/share/plymouth/themes/kyth/kyth.script' "${listing}" || ok=0
    grep -q 'usr/share/plymouth/themes/kyth/kyth-logo.png' "${listing}" || ok=0
    grep -q 'usr/share/plymouth/themes/default.plymouth' "${listing}" || ok=0
    [[ -r /usr/share/kyth/branding/transparent-watermark.png ]] || ok=0
    cmp -s "${logo}" /usr/share/kyth/branding/transparent-watermark.png || ok=0
    grep -q '^Theme=kyth$' "${defaults}" || ok=0
    grep -q '^ShowDelay=0$' "${defaults}" || ok=0
    grep -q '^DeviceTimeout=8$' "${defaults}" || ok=0
    if grep -Ei 'usr/share/plymouth/themes/(bgrt-fedora|bgrt|spinner)(/|$)' "${listing}" >&2; then
        ok=0
    fi
    rm -f "${defaults}" "${listing}" "${logo}"

    [[ "${ok}" -eq 1 ]] && return 1
    return 0
}

verify_image() {
    local image=$1
    local defaults listing logo

    command -v lsinitrd >/dev/null 2>&1 || return 0
    defaults="$(mktemp /tmp/kyth-plymouth-defaults.XXXXXX)"
    listing="$(mktemp /tmp/kyth-plymouth-listing.XXXXXX)"
    logo="$(mktemp /tmp/kyth-plymouth-logo.XXXXXX)"

    lsinitrd -f /usr/share/plymouth/plymouthd.defaults "${image}" > "${defaults}" || {
        echo "ERROR: refreshed initramfs is missing Plymouth defaults: ${image}" >&2
        rm -f "${defaults}" "${listing}" "${logo}"
        return 1
    }
    lsinitrd -f /usr/share/pixmaps/system-logo-white.png "${image}" > "${logo}" || {
        echo "ERROR: refreshed initramfs is missing transparent Plymouth system logo: ${image}" >&2
        rm -f "${defaults}" "${listing}" "${logo}"
        return 1
    }
    lsinitrd "${image}" > "${listing}" || {
        echo "ERROR: unable to inspect refreshed initramfs: ${image}" >&2
        rm -f "${defaults}" "${listing}" "${logo}"
        return 1
    }
    grep -q 'usr/share/plymouth/themes/kyth/kyth.plymouth' "${listing}" || {
        echo "ERROR: refreshed initramfs does not contain KythOS Plymouth theme: ${image}" >&2
        rm -f "${defaults}" "${listing}" "${logo}"
        return 1
    }
    grep -q 'usr/share/plymouth/themes/kyth/kyth.script' "${listing}" || {
        echo "ERROR: refreshed initramfs does not contain KythOS Plymouth script: ${image}" >&2
        rm -f "${defaults}" "${listing}" "${logo}"
        return 1
    }
    grep -q 'usr/share/plymouth/themes/kyth/kyth-logo.png' "${listing}" || {
        echo "ERROR: refreshed initramfs does not contain KythOS Plymouth logo: ${image}" >&2
        rm -f "${defaults}" "${listing}" "${logo}"
        return 1
    }
    grep -q 'usr/share/plymouth/themes/default.plymouth' "${listing}" || {
        echo "ERROR: refreshed initramfs does not force KythOS as the default Plymouth theme: ${image}" >&2
        rm -f "${defaults}" "${listing}" "${logo}"
        return 1
    }
    cmp -s "${logo}" /usr/share/kyth/branding/transparent-watermark.png || {
        echo "ERROR: refreshed initramfs still contains distro Plymouth system logo: ${image}" >&2
        rm -f "${defaults}" "${listing}" "${logo}"
        return 1
    }
    grep -q '^Theme=kyth$' "${defaults}" || {
        echo "ERROR: refreshed initramfs Plymouth defaults do not force Theme=kyth: ${image}" >&2
        rm -f "${defaults}" "${listing}" "${logo}"
        return 1
    }
    grep -q '^ShowDelay=0$' "${defaults}" || {
        echo "ERROR: refreshed initramfs Plymouth defaults do not draw immediately: ${image}" >&2
        rm -f "${defaults}" "${listing}" "${logo}"
        return 1
    }
    grep -q '^DeviceTimeout=8$' "${defaults}" || {
        echo "ERROR: refreshed initramfs Plymouth defaults are missing DeviceTimeout=8: ${image}" >&2
        rm -f "${defaults}" "${listing}" "${logo}"
        return 1
    }
    if grep -Ei 'usr/share/plymouth/themes/(bgrt-fedora|bgrt|spinner)(/|$)' "${listing}" >&2; then
        echo "ERROR: Plymouth fallback theme leaked into refreshed initramfs: ${image}" >&2
        rm -f "${defaults}" "${listing}" "${logo}"
        return 1
    fi

    rm -f "${defaults}" "${listing}" "${logo}"
}

current_fingerprint="$(fingerprint_current)"
collect_images

needs_refresh=0
if [[ ! -e "${migration_marker}" ]]; then
    needs_refresh=1
fi
if [[ -r "${fingerprint_file}" && "$(cat "${fingerprint_file}")" != "${current_fingerprint}" ]]; then
    needs_refresh=1
fi
if [[ "${#images[@]}" -eq 0 ]]; then
    needs_refresh=1
fi
for image in "${images[@]}"; do
    if image_needs_refresh "${image}"; then
        needs_refresh=1
    fi
done

if [[ "${needs_refresh}" -eq 0 ]]; then
    printf '%s\n' "${current_fingerprint}" > "${fingerprint_file}"
    touch "${migration_marker}"
    exit 0
fi

include_root="$(mktemp -d /tmp/kyth-plymouth-initramfs.XXXXXX)"
boot_was_ro=0
cleanup() {
    rm -rf "${include_root}"
    if [[ "${boot_was_ro}" -eq 1 ]]; then
        mount -o remount,ro /boot || true
    fi
}
trap cleanup EXIT

if findmnt -no OPTIONS /boot 2>/dev/null | tr ',' '\n' | grep -qx ro; then
    if mount -o remount,rw /boot 2>/dev/null; then
        boot_was_ro=1
    else
        echo "WARNING: /boot is read-only and could not be remounted; skipping initramfs refresh" >&2
        exit 0
    fi
fi

mkdir -p \
    "${include_root}/etc/plymouth" \
    "${include_root}/usr/share/plymouth" \
    "${include_root}/usr/share/pixmaps" \
    "${include_root}/usr/share/plymouth/themes"
printf '[Daemon]\nTheme=kyth\nShowDelay=0\nDeviceTimeout=8\nUseFirmwareBackground=false\n' \
    > "${include_root}/etc/plymouth/plymouthd.conf"
install -m 0644 \
    "${include_root}/etc/plymouth/plymouthd.conf" \
    "${include_root}/usr/share/plymouth/plymouthd.defaults"
if [[ -r /usr/share/kyth/branding/transparent-watermark.png ]]; then
    install -m 0644 /usr/share/kyth/branding/transparent-watermark.png \
        "${include_root}/usr/share/pixmaps/system-logo-white.png"
else
    printf '%s' 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNgYAAAAAMAASsJTYQAAAAASUVORK5CYII=' \
        | base64 -d > "${include_root}/usr/share/pixmaps/system-logo-white.png"
fi
cp -a /usr/share/plymouth/themes/kyth "${include_root}/usr/share/plymouth/themes/kyth"
ln -sfn kyth/kyth.plymouth "${include_root}/usr/share/plymouth/themes/default.plymouth"
rm -rf \
    "${include_root}/usr/share/plymouth/themes/bgrt-fedora" \
    "${include_root}/usr/share/plymouth/themes/bgrt" \
    "${include_root}/usr/share/plymouth/themes/spinner"

if [[ -w /etc/plymouth ]]; then
    install -m 0644 "${include_root}/etc/plymouth/plymouthd.conf" /etc/plymouth/plymouthd.conf
fi
if [[ -w /usr/share/plymouth ]]; then
    install -m 0644 "${include_root}/usr/share/plymouth/plymouthd.defaults" /usr/share/plymouth/plymouthd.defaults
fi
if [[ -w /usr/share/pixmaps ]]; then
    install -m 0644 "${include_root}/usr/share/pixmaps/system-logo-white.png" /usr/share/pixmaps/system-logo-white.png
fi

rebuilt=0
for image in "${images[@]}"; do
    kernel="${image##*/initramfs-}"
    kernel="${kernel%.img}"

    TMPDIR=/var/tmp dracut \
        --tmpdir /var/tmp \
        --no-hostonly \
        --kver "${kernel}" \
        --reproducible \
        --force \
        --add "drm plymouth ostree kyth-plymouth" \
        --include "${include_root}/etc/plymouth" /etc/plymouth \
        --include "${include_root}/usr/share/plymouth" /usr/share/plymouth \
        --include "${include_root}/usr/share/pixmaps/system-logo-white.png" /usr/share/pixmaps/system-logo-white.png \
        "${image}" \
        "${kernel}"
    verify_image "${image}"
    rebuilt=1
done

if [[ "${rebuilt}" -eq 0 ]]; then
    TMPDIR=/var/tmp dracut \
        --tmpdir /var/tmp \
        --regenerate-all \
        --force \
        --add "drm plymouth kyth-plymouth" \
        --include "${include_root}/etc/plymouth" /etc/plymouth \
        --include "${include_root}/usr/share/plymouth" /usr/share/plymouth \
        --include "${include_root}/usr/share/pixmaps/system-logo-white.png" /usr/share/pixmaps/system-logo-white.png
    collect_images
    for image in "${images[@]}"; do
        verify_image "${image}"
    done
fi

printf '%s\n' "${current_fingerprint}" > "${fingerprint_file}"
touch "${migration_marker}"
SPLASHINITRDSCRIPTEOF
chmod 0755 /usr/libexec/kyth-refresh-boot-splash-initramfs

cat >/usr/lib/systemd/system/kyth-boot-splash-initramfs.service <<'SPLASHINITRDEOF'
[Unit]
Description=Refresh KythOS boot splash initramfs
After=local-fs.target

[Service]
Type=oneshot
ExecStart=/usr/libexec/kyth-refresh-boot-splash-initramfs

[Install]
WantedBy=multi-user.target
SPLASHINITRDEOF
systemctl enable kyth-boot-splash-initramfs.service 2>/dev/null || true

# First-boot notice: shown once via Plymouth message_callback, then sentinel
# gates it so subsequent boots skip the message.
cat >/usr/lib/systemd/system/kyth-firstboot-notice.service <<'FBOOTEOF'
[Unit]
Description=KythOS first-boot Plymouth notice
# ostree-remount.service is what makes /var writable on ostree — with
# DefaultDependencies=no this unit otherwise races it and the sentinel
# mkdir fails with "Read-only file system".
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

