# ── VM / QEMU recipes ───────────────────────────────────────────────────────
# Imported by Justfile.
import "_vars.just"

# Run a virtual machine with the specified image type and configuration
[private]
_run-vm $target_image $tag $type $config:
    #!/usr/bin/bash
    set -eoux pipefail

    image_file="output/${type}/disk.${type}"
    if [[ $type == iso ]]; then
        image_file="output/bootiso/kyth-installer.iso"
    fi

    if [[ ! -f "${image_file}" ]]; then
        just "build-${type}" "$target_image" "$tag"
    fi

    port=$(just _find-free-port 8006)
    echo "Using Port: ${port}"
    echo "Connect to http://localhost:${port}"

    run_args=()
    run_args+=(--rm --privileged)
    run_args+=(--pull=newer)
    run_args+=(--publish "127.0.0.1:${port}:8006")
    run_args+=(--env "CPU_CORES=4")
    run_args+=(--env "RAM_SIZE=8G")
    run_args+=(--env "DISK_SIZE=64G")
    run_args+=(--env "TPM=Y")
    run_args+=(--env "GPU=Y")
    run_args+=(--device=/dev/kvm)
    run_args+=(--volume "${PWD}/${image_file}":"/boot.${type}")
    run_args+=(docker.io/qemux/qemu)

    (sleep 30 && xdg-open http://localhost:"$port") &
    docker run "${run_args[@]}"

# Run a virtual machine from a QCOW2 image
[group('Run Virtual Machine')]
run-vm-qcow2 $target_image=("localhost/" + image_name) $tag=default_tag: && (_run-vm target_image tag "qcow2" "disk_config/disk.toml")

# Run a virtual machine from a RAW image
[group('Run Virtual Machine')]
run-vm-raw $target_image=("localhost/" + image_name) $tag=default_tag: && (_run-vm target_image tag "raw" "disk_config/disk.toml")

# Run a virtual machine from an ISO
[group('Run Virtual Machine')]
run-vm-iso $target_image=("localhost/" + image_name) $tag=default_tag: && (_run-vm target_image tag "iso" "disk_config/iso.toml")

# Boot the live ISO in a VM (BIOS, web UI at http://localhost:PORT).
[group('Run Virtual Machine')]
run-live-iso source_tag="latest":
    #!/usr/bin/bash
    set -eoux pipefail

    image_file="output/live-iso/kyth-live-{{ source_tag }}.iso"
    if [[ ! -f "${image_file}" ]]; then
        just build-live-iso {{ source_tag }}
    fi

    port=$(just _find-free-port 8006)
    echo "Using Port: ${port}"
    echo "Connect to http://localhost:${port}"

    (sleep 30 && xdg-open http://localhost:"$port") &
    docker run \
        --rm --privileged \
        --pull missing \
        --publish "127.0.0.1:${port}:8006" \
        --env "CPU_CORES=4" \
        --env "RAM_SIZE=8G" \
        --env "DISK_SIZE=64G" \
        --env "GPU=Y" \
        --device=/dev/kvm \
        --volume "${PWD}/${image_file}:/boot.iso" \
        docker.io/qemux/qemu

# Boot the live ISO directly in native QEMU (SPICE window, better clipboard).
[group('Run Virtual Machine')]
run-live-iso-native source_tag="latest" legacy="0":
    #!/usr/bin/bash
    set -eoux pipefail

    image_file="output/live-iso/kyth-live-{{ source_tag }}.iso"
    if [[ ! -f "${image_file}" ]]; then
        just build-live-iso {{ source_tag }}
    fi

    disk_dir="/var/tmp/kyth-vm-disks-${USER}"
    mkdir -p "${disk_dir}"
    disk_img="${disk_dir}/kyth-live-test.qcow2"
    ovmf_vars="${disk_dir}/ovmf_vars.fd"

    if [[ "${LIVE_ISO_VM_RESET:-0}" == "1" ]]; then
        rm -f "${disk_img}" "${ovmf_vars}"
    fi

    avail_bytes=$(df --output=avail -B1 "${disk_dir}" | tail -n 1 | tr -d '[:space:]')
    min_bytes=$((30 * 1024 * 1024 * 1024))
    if [[ "${avail_bytes}" -lt "${min_bytes}" ]]; then
        echo "Insufficient free space for live ISO VM disk writes on $(df --output=target "${disk_dir}" | tail -n 1)."
        echo "Need >= 30 GiB free, found $((avail_bytes / 1024 / 1024 / 1024)) GiB."
        echo "Run: just prune-live-dev"
        exit 1
    fi

    if [[ ! -f "${disk_img}" ]]; then
        qemu-img create -f qcow2 -o preallocation=metadata,lazy_refcounts=on "${disk_img}" 64G
    fi

    _ovmf_args=()
    for _ovmf_code in \
        /usr/share/edk2/ovmf/OVMF_CODE.fd \
        /usr/share/OVMF/OVMF_CODE.fd; do
        if [[ -f "${_ovmf_code}" ]]; then
            if [[ ! -f "${ovmf_vars}" ]]; then
                _ovmf_tmpl="${_ovmf_code/CODE/VARS}"
                [[ -f "${_ovmf_tmpl}" ]] && cp "${_ovmf_tmpl}" "${ovmf_vars}"
            fi
            if [[ -f "${ovmf_vars}" ]]; then
                _ovmf_args=(
                    -drive "if=pflash,format=raw,unit=0,readonly=on,file=${_ovmf_code}"
                    -drive "if=pflash,format=raw,unit=1,file=${ovmf_vars}"
                )
                echo "==> UEFI boot: ${_ovmf_code}  NVRAM: ${ovmf_vars}"
            fi
            break
        fi
    done
    [[ ${#_ovmf_args[@]} -eq 0 ]] && echo "==> BIOS boot (install edk2-ovmf for UEFI)"

    share_dir="/var/tmp/kyth-vm-share-${USER}"
    mkdir -p "${share_dir}"
    serial_log="${share_dir}/qemu-serial.log"
    qemu_log="${share_dir}/qemu-debug.log"
    rm -f "${serial_log}" "${qemu_log}"
    echo "Host shared folder: ${share_dir}"
    echo "Serial log on host: ${serial_log}"
    echo "QEMU debug log on host: ${qemu_log}"
    echo "In VM, run: sudo mkdir -p /var/mnt/hostshare && sudo mount -t 9p -o trans=virtio,version=9p2000.L,cache=none hostshare /var/mnt/hostshare"

    _qemu_devices="$(qemu-system-x86_64 -device help 2>/dev/null || true)"
    if [[ "${_qemu_devices}" == *'name "qxl-vga"'* ]]; then
        _video_args=(-device qxl-vga)
        echo "==> QEMU video: qxl-vga"
    else
        _video_args=(-device virtio-vga)
        echo "==> QEMU video: virtio-vga (qxl-vga unavailable)"
    fi

    if [[ "{{ legacy }}" == "1" ]]; then
        _spice_port=5932
        _ssh_port=2224
        _qemu_boot_args=(-no-reboot -no-shutdown -cdrom "${image_file}" -boot order=d)
        _qemu_disk_args=(-drive "file=${disk_img},if=virtio,format=qcow2")
    else
        _spice_port=5931
        _ssh_port=2223
        _qemu_boot_args=(
            -device ich9-ahci,id=ahci
            -drive "if=none,id=liveiso,format=raw,media=cdrom,readonly=on,file=${image_file}"
            -device ide-cd,bus=ahci.0,drive=liveiso,bootindex=2
        )
        _qemu_disk_args=(
            -drive "if=none,id=systemdisk,file=${disk_img},format=qcow2"
            -device virtio-blk-pci,drive=systemdisk,bootindex=1
        )
    fi

    qemu-system-x86_64 \
        -enable-kvm \
        -cpu host \
        -smp 4 \
        -m 8G \
        -machine q35 \
        "${_ovmf_args[@]}" \
        "${_qemu_boot_args[@]}" \
        "${_qemu_disk_args[@]}" \
        "${_video_args[@]}" \
        -display none \
        -spice "port=${_spice_port},disable-ticketing=on,disable-copy-paste=off,disable-agent-file-xfer=off" \
        -device virtio-serial \
        -chardev spicevmc,id=vdagent,name=vdagent \
        -device virtserialport,chardev=vdagent,name=com.redhat.spice.0 \
        -device virtio-net-pci,netdev=net0 \
        -netdev "user,id=net0,hostfwd=tcp::${_ssh_port}-:22" \
        -device virtio-rng-pci \
        -device qemu-xhci \
        -device usb-tablet \
        -d guest_errors \
        -serial "file:${serial_log}" \
        -D "${qemu_log}" \
        -virtfs local,path="${share_dir}",mount_tag=hostshare,security_model=mapped-xattr,id=hostshare \
        &
    QEMU_PID=$!
    sleep 2
    rv_cache="/var/tmp/kyth-remote-viewer-${USER}"
    mkdir -p "${rv_cache}"
    env XDG_CACHE_HOME="${rv_cache}" TMPDIR="/var/tmp" remote-viewer "spice://localhost:${_spice_port}" &
    wait "${QEMU_PID}"

# Build the local embedded ISO and boot it in native QEMU with a fresh disk.
[group('Run Virtual Machine')]
run-live-iso-native-local:
    #!/usr/bin/env bash
    set -euo pipefail
    just rebuild-live-iso-local
    LIVE_ISO_VM_RESET=1 just run-live-iso-native local

# Unattended live boot, install, and installed-boot acceptance. Supply a second
# image ref to additionally prove update activation and rollback across reboots.
[group('Run Virtual Machine')]
accept-live-iso iso="output/live-iso/kyth-live-testing.iso" update_ref="":
    #!/usr/bin/env bash
    set -euo pipefail
    args=(--iso "{{ iso }}" --artifacts "output/vm-acceptance")
    if [[ -n "{{ update_ref }}" ]]; then
        args+=(--update-ref "{{ update_ref }}")
    fi
    build_files/scripts/vm-acceptance.sh "${args[@]}"

# Run a virtual machine using systemd-vmspawn
[group('Run Virtual Machine')]
spawn-vm rebuild="0" type="qcow2" ram="6G":
    #!/usr/bin/env bash
    set -euo pipefail

    [ "{{ rebuild }}" -eq 1 ] && echo "Rebuilding the {{ type }} image" && just build-{{ type }}

    systemd-vmspawn \
      -M "bootc-image" \
      --console=gui \
      --cpus=2 \
      --ram=$(echo {{ ram }}| /usr/bin/numfmt --from=iec) \
      --network-user-mode \
      --vsock=false --pass-ssh-key=false \
      -i ./output/**/*.{{ type }}
