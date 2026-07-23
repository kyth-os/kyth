#!/usr/bin/env bash
# kyth-partition-install.sh — install KythOS into an existing blank partition.
#
# This is the safer dual-boot path when you have already created a blank
# partition with another tool. It formats only TARGET_PARTITION, reuses an
# existing EFI System Partition when one is available, and leaves neighboring
# partitions alone.
#
# Usage:
#   sudo kyth-partition-install.sh TARGET_PARTITION [EFI_PARTITION]
#
# Examples:
#   sudo kyth-partition-install.sh /dev/nvme0n1p5
#   sudo kyth-partition-install.sh /dev/sda4 /dev/sda1

set -euo pipefail

SOURCE_IMAGE="${KYTH_SOURCE_IMAGE:-ghcr.io/mrtrick37/kyth:latest}"
TARGET_IMAGE="${KYTH_TARGET_IMAGE:-${SOURCE_IMAGE}}"
TARGET_PART="${1:-}"
EFI_PART="${2:-}"
ROOT_MNT="/var/tmp/kyth-partition-root"
DEFAULT_HOSTNAME="${KYTH_HOSTNAME:-kyth}"
DEFAULT_TIMEZONE="${KYTH_TIMEZONE:-UTC}"

die() {
	echo "ERROR: $*" >&2
	exit 1
}

as_root() {
	if [[ ${EUID} -eq 0 ]]; then
		"$@"
	else
		sudo -n "$@"
	fi
}

human_size() {
	lsblk -dnpo SIZE "$1" 2>/dev/null || echo "unknown size"
}

partition_parent_disk() {
	lsblk -no PKNAME "$1" | head -n1 | sed 's#^#/dev/#'
}

find_efi_partition() {
	local disk="$1"
	lsblk -lnpo NAME,FSTYPE,SIZE,PARTTYPE "$disk" |
		awk '
			tolower($2) == "vfat" && $4 == "c12a7328-f81f-11d2-ba4b-00a0c93ec93b" {
				print $1
				exit
			}
		'
}

find_deploy_etc() {
	local root="$1"
	find "$root/ostree/deploy/default/deploy" -mindepth 2 -maxdepth 2 -type d -name etc 2>/dev/null |
		sort |
		tail -n1
}

write_target_file() {
	local path="$1"
	local contents="$2"
	as_root tee "$path" >/dev/null <<<"$contents"
}

# The graphical kyth-installer applies this exact same repair to a target
# tree's account databases; both call the shared implementation in
# kyth_shared.accounts (installed system-wide alongside this script) instead
# of keeping two independently-drifting reimplementations in sync by hand.
ensure_system_accounts() {
	local deploy_root="$1"
	as_root python3 -m kyth_shared.accounts "$deploy_root"
}

create_user() {
	local root_mnt="$1"
	local deploy_etc="$2"
	local username="$3"
	local password="$4"
	local deploy_root shadow_path pw_hash uid gid var_home skel tmp_shadow

	[[ -n "$username" && -n "$password" ]] || return 0

	deploy_root="$(dirname "$deploy_etc")"
	as_root useradd --root "$deploy_root" \
		-M \
		-G wheel,video,audio,render \
		-s /bin/bash \
		"$username"

	pw_hash="$(openssl passwd -6 -stdin <<<"$password")"
	shadow_path="$deploy_etc/shadow"
	tmp_shadow="$(mktemp)"
	# shellcheck disable=SC2016
	as_root awk -F: -v OFS=: -v user="$username" -v hash="$pw_hash" '
		$1 == user { $2 = hash; found = 1 }
		{ print }
		END { if (!found) exit 42 }
	' "$shadow_path" >"$tmp_shadow" ||
		{
			rm -f "$tmp_shadow"
			die "Failed to update password hash for ${username}"
		}
	as_root tee "$shadow_path" >/dev/null <"$tmp_shadow"
	rm -f "$tmp_shadow"

	uid="1000"
	gid="1000"
	while IFS=: read -r name _ pass_uid pass_gid _; do
		if [[ "$name" == "$username" ]]; then
			uid="$pass_uid"
			gid="$pass_gid"
			break
		fi
	done < <(as_root cat "$deploy_etc/passwd")

	var_home="$root_mnt/ostree/deploy/default/var/home/$username"
	as_root mkdir -p "$var_home"
	as_root chown "$uid:$gid" "$var_home"
	as_root chmod 700 "$var_home"

	skel="$deploy_root/etc/skel"
	if [[ -d "$skel" ]]; then
		as_root cp -rT "$skel" "$var_home"
		as_root chown -R "$uid:$gid" "$var_home"
	fi
}

usage() {
	sed -n '2,15p' "$0" | sed 's/^# \{0,1\}//'
}

[[ ${EUID} -eq 0 ]] || die "Run as root with sudo."
[[ -n "$TARGET_PART" ]] || {
	usage
	exit 2
}
[[ -b "$TARGET_PART" ]] || die "$TARGET_PART is not a block device."

for cmd in bootc lsblk mkfs.btrfs mount umount findmnt blkid python3; do
	command -v "$cmd" >/dev/null 2>&1 || die "Required command not found: $cmd"
done

if findmnt -rn --source "$TARGET_PART" >/dev/null 2>&1; then
	die "$TARGET_PART is mounted. Unmount it before installing."
fi

PARENT_DISK="$(partition_parent_disk "$TARGET_PART")"
[[ -b "$PARENT_DISK" ]] || die "Could not determine parent disk for $TARGET_PART."

if [[ -z "$EFI_PART" ]]; then
	EFI_PART="$(find_efi_partition "$PARENT_DISK" || true)"
fi
if [[ -n "$EFI_PART" && ! -b "$EFI_PART" ]]; then
	die "$EFI_PART is not a block device."
fi
if [[ "$EFI_PART" == "$TARGET_PART" ]]; then
	die "EFI partition and target partition must be different."
fi

echo ""
echo "=== KythOS Blank-Partition Installer ==="
echo ""
echo "  Target partition : $TARGET_PART ($(human_size "$TARGET_PART"))"
echo "  Parent disk      : $PARENT_DISK"
echo "  EFI partition    : ${EFI_PART:-none detected}"
echo "  Source image     : docker://$SOURCE_IMAGE"
echo "  Target ref       : $TARGET_IMAGE"
echo ""
echo "This will FORMAT ONLY $TARGET_PART as Btrfs and install KythOS there."
echo "Existing neighboring partitions will not be resized or deleted."
echo ""
echo "Back up important data before continuing. Bootloader changes may affect"
echo "the EFI System Partition when one is reused."
echo ""
read -r -p "Type 'install kythos' to continue: " CONFIRM
[[ "$CONFIRM" == "install kythos" ]] || {
	echo "Aborted."
	exit 0
}

echo ""
read -r -p "Hostname [$DEFAULT_HOSTNAME]: " HOSTNAME
HOSTNAME="${HOSTNAME:-$DEFAULT_HOSTNAME}"
if [[ ! "$HOSTNAME" =~ ^[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?$ ]]; then
	die "Invalid hostname: $HOSTNAME"
fi
read -r -p "Timezone [$DEFAULT_TIMEZONE]: " TIMEZONE
TIMEZONE="${TIMEZONE:-$DEFAULT_TIMEZONE}"
if [[ "$TIMEZONE" == *..* || "$TIMEZONE" == /* || ! -f "/usr/share/zoneinfo/$TIMEZONE" ]]; then
	die "Invalid timezone: $TIMEZONE"
fi
read -r -p "Create admin username (blank to skip): " USERNAME
PASSWORD=""
if [[ -n "$USERNAME" ]]; then
	if [[ ! "$USERNAME" =~ ^[a-z_][a-z0-9_-]{0,30}$ ]]; then
		die "Invalid username: $USERNAME"
	fi
	read -r -s -p "Password for $USERNAME: " PASSWORD
	echo ""
	read -r -s -p "Confirm password: " PASSWORD_CONFIRM
	echo ""
	[[ "$PASSWORD" == "$PASSWORD_CONFIRM" ]] || die "Passwords do not match."
fi

cleanup() {
	set +e
	as_root sync
	if mountpoint -q "$ROOT_MNT/boot/efi"; then
		as_root umount "$ROOT_MNT/boot/efi"
	fi
	if mountpoint -q "$ROOT_MNT"; then
		as_root umount "$ROOT_MNT"
	fi
}
trap cleanup EXIT

echo ""
echo "==> Formatting $TARGET_PART as Btrfs..."
as_root mkfs.btrfs -f -L kyth-root "$TARGET_PART"

echo "==> Mounting target partition..."
as_root mkdir -p "$ROOT_MNT"
as_root mount "$TARGET_PART" "$ROOT_MNT"

if [[ -n "$EFI_PART" ]]; then
	echo "==> Reusing EFI System Partition $EFI_PART..."
	as_root mkdir -p "$ROOT_MNT/boot/efi"
	as_root mount "$EFI_PART" "$ROOT_MNT/boot/efi"
else
	echo "==> No EFI System Partition detected; bootc will install without a mounted ESP."
fi

echo "==> Installing KythOS..."
as_root bootc install to-filesystem \
	--source-imgref "docker://$SOURCE_IMAGE" \
	--target-imgref "$TARGET_IMAGE" \
	--skip-fetch-check \
	--acknowledge-destructive \
	"$ROOT_MNT"

echo "==> Applying first-boot configuration..."
DEPLOY_ETC="$(find_deploy_etc "$ROOT_MNT")"
if [[ -z "$DEPLOY_ETC" ]]; then
	echo "Warning: deployed /etc not found; skipping hostname, timezone, and user setup."
else
	write_target_file "$DEPLOY_ETC/hostname" "$HOSTNAME"
	as_root ln -snf "/usr/share/zoneinfo/$TIMEZONE" "$DEPLOY_ETC/localtime"
	ensure_system_accounts "$(dirname "$DEPLOY_ETC")"
	if [[ -n "$USERNAME" ]]; then
		create_user "$ROOT_MNT" "$DEPLOY_ETC" "$USERNAME" "$PASSWORD"
		ensure_system_accounts "$(dirname "$DEPLOY_ETC")"
	fi
fi

echo "==> Syncing and unmounting..."
cleanup
trap - EXIT

echo ""
echo "Installation complete."
echo "Reboot and choose KythOS from your firmware or GRUB boot menu."
echo ""
