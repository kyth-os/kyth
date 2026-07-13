#!/usr/bin/env bash
# Install KythOS alongside an existing Fedora install from the running Fedora system.
#
# This script uses partition-table unallocated space only. It does not shrink,
# resize, or use unused filesystem space inside any existing Fedora partition.
# It creates one new partition in the largest unallocated region on a disk,
# formats only that new partition as Btrfs, reuses the existing EFI System
# Partition, and installs KythOS with bootc.
#
# Usage:
#   sudo ./install-kyth-from-fedora-free-space.sh
#   sudo ./install-kyth-from-fedora-free-space.sh /dev/nvme0n1

set -euo pipefail

DISK="${1:-}"
SOURCE_IMAGE="ghcr.io/mrtrick37/kyth:latest"
TARGET_IMAGE="$SOURCE_IMAGE"
ROOT_MNT="/var/tmp/kyth-root"
DEFAULT_HOSTNAME="${KYTH_HOSTNAME:-kyth}"
DEFAULT_TIMEZONE="${KYTH_TIMEZONE:-$(timedatectl show -P Timezone 2>/dev/null || echo UTC)}"

die() {
	echo "ERROR: $*" >&2
	exit 1
}

need_root() {
	[[ ${EUID} -eq 0 ]] || die "Run with sudo."
}

install_deps() {
	local missing=()

	for cmd in bootc parted mkfs.btrfs lsblk findmnt blkid partprobe udevadm openssl useradd; do
		command -v "$cmd" >/dev/null 2>&1 || missing+=("$cmd")
	done

	if ((${#missing[@]} == 0)); then
		return 0
	fi

	echo "Installing required Fedora packages..."
	dnf install -y bootc parted btrfs-progs util-linux systemd openssl shadow-utils
}

human_size() {
	lsblk -dnpo SIZE "$1" 2>/dev/null || echo "unknown size"
}

find_efi_partition() {
	local disk="$1"

	lsblk -lnpo NAME,FSTYPE,PARTTYPE "$disk" |
		awk '
			tolower($2) == "vfat" && tolower($3) == "c12a7328-f81f-11d2-ba4b-00a0c93ec93b" {
				print $1
				exit
			}
		'
}

largest_unallocated_region_mib() {
	local disk="$1"

	parted -m "$disk" unit MiB print free |
		awk -F: '
			{
				is_free = 0;
				for (i = 1; i <= NF; i++) {
					gsub(";", "", $i);
					if ($i == "free") {
						is_free = 1;
					}
				}
			}
			is_free {
				start=$2; end=$3; size=$4;
				gsub("MiB","",start);
				gsub("MiB","",end);
				gsub("MiB","",size);
				if (size > best_size) {
					best_start=start;
					best_end=end;
					best_size=size;
				}
			}
			END {
				if (best_size >= 20000) {
					printf "%.0f %.0f %.0f\n", best_start, best_end, best_size;
				}
			}
		'
}

choose_disk_with_unallocated_space() {
	local disk line best_disk best_start best_end best_size start end size

	while read -r disk; do
		line="$(largest_unallocated_region_mib "$disk" || true)"
		[[ -n "$line" ]] || continue

		read -r start end size <<<"$line"
		if [[ -z "${best_size:-}" || "$size" -gt "$best_size" ]]; then
			best_disk="$disk"
			best_start="$start"
			best_end="$end"
			best_size="$size"
		fi
	done < <(lsblk -dnpo NAME,TYPE | awk '$2 == "disk" { print $1 }')

	if [[ -n "${best_disk:-}" ]]; then
		printf "%s %s %s %s\n" "$best_disk" "$best_start" "$best_end" "$best_size"
	fi
}

list_disk_partitions() {
	local disk="$1"

	lsblk -lnpo NAME,TYPE "$disk" |
		awk '$2 == "part" { print $1 }' |
		sort
}

find_existing_kyth_partition() {
	local disk="$1"

	lsblk -lnpo NAME,LABEL,PARTLABEL "$disk" |
		awk '$2 == "kyth-root" || $2 == "KythOS" || $3 == "kyth-root" || $3 == "KythOS" { print $1 }' |
		tail -n1
}

choose_existing_kyth_partition() {
	local disk part

	while read -r disk; do
		part="$(find_existing_kyth_partition "$disk")"
		[[ -n "$part" ]] || continue
		printf "%s %s\n" "$disk" "$part"
		return 0
	done < <(lsblk -dnpo NAME,TYPE | awk '$2 == "disk" { print $1 }')
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

	tee "$path" >/dev/null <<<"$contents"
}

ensure_prepare_root_conf() {
	if [[ -f /usr/lib/ostree/prepare-root.conf || -f /etc/ostree/prepare-root.conf ]]; then
		return 0
	fi

	echo "Creating missing /etc/ostree/prepare-root.conf required by bootc..."
	mkdir -p /etc/ostree

	if [[ -f /usr/share/doc/bootc/baseimage/base/usr/lib/ostree/prepare-root.conf ]]; then
		cp /usr/share/doc/bootc/baseimage/base/usr/lib/ostree/prepare-root.conf /etc/ostree/prepare-root.conf
	else
		tee /etc/ostree/prepare-root.conf >/dev/null <<'EOF'
[composefs]
enabled = true
EOF
	fi
}

append_missing_records() {
	local source="$1"
	local dest="$2"
	local line name

	[[ -r "$source" ]] || return 0
	touch "$dest"
	while IFS= read -r line || [[ -n "$line" ]]; do
		[[ -n "$line" ]] || continue
		name="${line%%:*}"
		[[ -n "$name" ]] || continue
		if ! grep -q "^${name}:" "$dest"; then
			printf '%s\n' "$line" | tee -a "$dest" >/dev/null
		fi
	done < <(cat "$source")
}

ensure_line_by_name() {
	local name="$1"
	local line="$2"
	local dest="$3"

	if ! grep -q "^${name}:" "$dest"; then
		printf '%s\n' "$line" | tee -a "$dest" >/dev/null
	fi
}

ensure_system_accounts() {
	local deploy_root="$1"
	local passwd_path="$deploy_root/etc/passwd"
	local group_path="$deploy_root/etc/group"
	local shadow_path="$deploy_root/etc/shadow"
	local name

	append_missing_records "$deploy_root/usr/lib/group" "$group_path"
	append_missing_records "$deploy_root/usr/lib/passwd" "$passwd_path"

	ensure_line_by_name sddm "sddm:x:959:" "$group_path"
	ensure_line_by_name sddm \
		"sddm:x:959:959:SDDM Greeter Account:/var/lib/sddm:/usr/sbin/nologin" \
		"$passwd_path"

	if [[ -e "$shadow_path" ]]; then
		while IFS=: read -r name _; do
			[[ -n "$name" && "$name" != "root" ]] || continue
			if ! grep -q "^${name}:" "$shadow_path"; then
				printf '%s:!*:19700:0:99999:7:::\n' "$name" |
					tee -a "$shadow_path" >/dev/null
			fi
		done < <(cat "$passwd_path")
	fi

	chmod 0644 "$passwd_path" "$group_path"
	[[ ! -e "$shadow_path" ]] || chmod 0000 "$shadow_path" || true
	mkdir -p "$deploy_root/var/lib/sddm"
	chown sddm:sddm "$deploy_root/var/lib/sddm" || true
	restorecon "$passwd_path" "$group_path" "$shadow_path" "$deploy_root/var/lib/sddm" || true
}

create_user() {
	local root_mnt="$1"
	local deploy_etc="$2"
	local username="$3"
	local password="$4"
	local deploy_root shadow_path pw_hash uid gid var_home skel tmp_shadow

	[[ -n "$username" && -n "$password" ]] || return 0

	deploy_root="$(dirname "$deploy_etc")"
	useradd --root "$deploy_root" \
		-M \
		-G wheel,video,audio,render \
		-s /bin/bash \
		"$username"

	pw_hash="$(openssl passwd -6 -stdin <<<"$password")"
	shadow_path="$deploy_etc/shadow"
	tmp_shadow="$(mktemp)"

	awk -F: -v OFS=: -v user="$username" -v hash="$pw_hash" '
		$1 == user { $2 = hash; found = 1 }
		{ print }
		END { if (!found) exit 42 }
	' "$shadow_path" >"$tmp_shadow" || {
		rm -f "$tmp_shadow"
		die "Failed to update password hash for $username"
	}
	tee "$shadow_path" >/dev/null <"$tmp_shadow"
	rm -f "$tmp_shadow"

	uid="1000"
	gid="1000"
	while IFS=: read -r name _ pass_uid pass_gid _; do
		if [[ "$name" == "$username" ]]; then
			uid="$pass_uid"
			gid="$pass_gid"
			break
		fi
	done <"$deploy_etc/passwd"

	var_home="$root_mnt/ostree/deploy/default/var/home/$username"
	mkdir -p "$var_home"
	chown "$uid:$gid" "$var_home"
	chmod 700 "$var_home"

	skel="$deploy_root/etc/skel"
	if [[ -d "$skel" ]]; then
		cp -rT "$skel" "$var_home"
		chown -R "$uid:$gid" "$var_home"
	fi
}

cleanup() {
	set +e
	sync
	if mountpoint -q "$ROOT_MNT/boot/efi"; then
		umount "$ROOT_MNT/boot/efi"
	fi
	if mountpoint -q "$ROOT_MNT"; then
		umount "$ROOT_MNT"
	fi
}

need_root
install_deps
[[ "$DISK" != *:* ]] || die "Image arguments are no longer supported. This script pulls $SOURCE_IMAGE from GHCR."
[[ "${2:-}" == "" ]] || die "Unexpected extra argument: ${2}"

if [[ -z "$DISK" ]]; then
	CHOICE="$(choose_disk_with_unallocated_space)"
	if [[ -n "$CHOICE" ]]; then
		read -r DISK FREE_START FREE_END FREE_SIZE <<<"$CHOICE"
	else
		EXISTING_CHOICE="$(choose_existing_kyth_partition)"
		[[ -n "$EXISTING_CHOICE" ]] || die "No disk with unallocated partition-table space of at least 20 GiB and no existing kyth-root partition was found."
		read -r DISK TARGET_PART <<<"$EXISTING_CHOICE"
		FREE_START=""
		FREE_END=""
		FREE_SIZE=""
	fi
elif [[ -b "$DISK" ]]; then
	FREE_LINE="$(largest_unallocated_region_mib "$DISK")"
	if [[ -n "$FREE_LINE" ]]; then
		read -r FREE_START FREE_END FREE_SIZE <<<"$FREE_LINE"
	else
		TARGET_PART="$(find_existing_kyth_partition "$DISK")"
		[[ -n "$TARGET_PART" && -b "$TARGET_PART" ]] || {
			echo "No matching unallocated region or existing kyth-root partition was found on $DISK."
			echo
			echo "Here is what parted reports:"
			parted "$DISK" unit GiB print free
			exit 1
		}
		FREE_START=""
		FREE_END=""
		FREE_SIZE=""
	fi
else
	die "$DISK is not a block device."
fi

EFI_PART="$(find_efi_partition "$DISK" || true)"
[[ -n "$EFI_PART" && -b "$EFI_PART" ]] || die "No EFI System Partition found on $DISK."

echo
echo "=== KythOS Fedora-Side Alongside Installer ==="
echo
echo "  Disk           : $DISK ($(human_size "$DISK"))"
echo "  EFI partition  : $EFI_PART ($(human_size "$EFI_PART"))"
if [[ -n "${TARGET_PART:-}" ]]; then
	echo "  Target partition : $TARGET_PART ($(human_size "$TARGET_PART"))"
	echo "  Mode             : reuse existing kyth-root partition"
else
	echo "  Unallocated      : ${FREE_SIZE} MiB, from ${FREE_START}MiB to ${FREE_END}MiB"
	echo "  Mode             : create a new kyth-root partition"
fi
echo "  Source image     : docker://$SOURCE_IMAGE"
echo "  Installed ref    : $TARGET_IMAGE"
echo
if [[ -n "${TARGET_PART:-}" ]]; then
	echo "This will reformat only $TARGET_PART as Btrfs and install KythOS there."
else
	echo "This will create ONE new partition in partition-table unallocated space, format only"
	echo "that new partition as Btrfs, and install KythOS there."
fi
echo
echo "Your existing Fedora partitions will not be resized, mounted, or formatted."
echo "Back up anything important before continuing."
echo
lsblk -o NAME,SIZE,FSTYPE,PARTLABEL,TYPE,MOUNTPOINTS "$DISK"
echo
read -r -p "Type 'install kyth alongside fedora' to continue: " CONFIRM
[[ "$CONFIRM" == "install kyth alongside fedora" ]] || {
	echo "Aborted."
	exit 0
}

read -r -p "Hostname [$DEFAULT_HOSTNAME]: " HOSTNAME
HOSTNAME="${HOSTNAME:-$DEFAULT_HOSTNAME}"
[[ "$HOSTNAME" =~ ^[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?$ ]] || die "Invalid hostname: $HOSTNAME"

read -r -p "Timezone [$DEFAULT_TIMEZONE]: " TIMEZONE
TIMEZONE="${TIMEZONE:-$DEFAULT_TIMEZONE}"
[[ "$TIMEZONE" != *..* && "$TIMEZONE" != /* && -f "/usr/share/zoneinfo/$TIMEZONE" ]] || die "Invalid timezone: $TIMEZONE"

read -r -p "Create Kyth admin username: " USERNAME
[[ "$USERNAME" =~ ^[a-z_][a-z0-9_-]{0,30}$ ]] || die "Invalid username: $USERNAME"
read -r -s -p "Password for $USERNAME: " PASSWORD
echo
read -r -s -p "Confirm password: " PASSWORD_CONFIRM
echo
[[ "$PASSWORD" == "$PASSWORD_CONFIRM" ]] || die "Passwords do not match."
[[ -n "$PASSWORD" ]] || die "Password cannot be empty."

if [[ -z "${TARGET_PART:-}" ]]; then
	echo
	echo "Creating Kyth partition..."
	PARTS_BEFORE="$(list_disk_partitions "$DISK")"
	parted -s "$DISK" mkpart kyth-root btrfs "${FREE_START}MiB" "${FREE_END}MiB"
	partprobe "$DISK"
	udevadm settle

	# Identify the new partition by diffing the partition list around mkpart.
	# Looking it up by PARTLABEL could match a stale kyth-root partition from
	# an earlier install and format the wrong device.
	TARGET_PART="$(comm -13 <(printf '%s\n' "$PARTS_BEFORE") <(list_disk_partitions "$DISK"))"
	[[ -n "$TARGET_PART" && "$TARGET_PART" != *$'\n'* && -b "$TARGET_PART" ]] ||
		die "Could not identify the newly-created kyth-root partition (found: '${TARGET_PART:-none}')."
else
	echo
	echo "Reusing existing $TARGET_PART."
fi

if findmnt -rn --source "$TARGET_PART" >/dev/null 2>&1; then
	die "$TARGET_PART is mounted unexpectedly. Refusing to format it."
fi

trap cleanup EXIT

echo "Formatting $TARGET_PART as Btrfs..."
mkfs.btrfs -f -L kyth-root "$TARGET_PART"

echo "Mounting target filesystem..."
mkdir -p "$ROOT_MNT"
mount "$TARGET_PART" "$ROOT_MNT"

echo "Mounting existing EFI System Partition..."
mkdir -p "$ROOT_MNT/boot/efi"
mount "$EFI_PART" "$ROOT_MNT/boot/efi"

echo "Installing KythOS..."
ensure_prepare_root_conf
bootc install to-filesystem \
	--source-imgref "docker://$SOURCE_IMAGE" \
	--target-imgref "$TARGET_IMAGE" \
	--skip-fetch-check \
	--generic-image \
	--acknowledge-destructive \
	"$ROOT_MNT"

echo "Applying first-boot configuration..."
DEPLOY_ETC="$(find_deploy_etc "$ROOT_MNT")"
if [[ -z "$DEPLOY_ETC" ]]; then
	echo "Warning: deployed /etc not found; skipping hostname, timezone, and user setup."
else
	write_target_file "$DEPLOY_ETC/hostname" "$HOSTNAME"
	ln -snf "/usr/share/zoneinfo/$TIMEZONE" "$DEPLOY_ETC/localtime"
	ensure_system_accounts "$(dirname "$DEPLOY_ETC")"
	create_user "$ROOT_MNT" "$DEPLOY_ETC" "$USERNAME" "$PASSWORD"
	ensure_system_accounts "$(dirname "$DEPLOY_ETC")"
fi

echo "Syncing and unmounting..."
cleanup
trap - EXIT

echo
echo "KythOS install complete."
echo "Reboot, then choose KythOS from your firmware boot menu or GRUB menu."
