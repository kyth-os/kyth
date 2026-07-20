"""probe — _running_system_disk, _get_live_usb_disk, _parent_disk, _mount_sources, _protected_install_disks, _disk_path_is_safe, partition_has_active_mount"""

from __future__ import annotations

import os
from typing import Optional

import kyth_installer.disk as _disk
subprocess = _disk.subprocess

from ..config import _IS_LIVE_SESSION

def _running_system_disk() -> str:
    # Returns the raw mount SOURCE for "/" (which may be a partition, an LVM
    # logical volume, or a LUKS dm-crypt mapping) — callers resolve this up
    # to the physical disk via _disk._parent_disk(), which walks every layer of
    # device-mapper indirection rather than assuming a single PKNAME hop.
    try:
        source = subprocess.check_output(
            ["findmnt", "-n", "-o", "SOURCE", "/"],
            text=True, stderr=subprocess.DEVNULL, timeout=5,
        ).strip()
    except Exception:
        return ""
    if not source or not source.startswith("/dev/"):
        return ""
    return source



def _get_live_usb_disk() -> Optional[str]:
    for path in ("/run/initramfs/live", "/run/initramfs/iso"):
        try:
            source = subprocess.check_output(
                ["findmnt", "-n", "-o", "SOURCE", path],
                text=True, stderr=subprocess.DEVNULL, timeout=5,
            ).strip()
            if not source or not source.startswith("/dev/"):
                continue
            try:
                pkname = subprocess.check_output(
                    ["lsblk", "-n", "-o", "PKNAME", source],
                    text=True, stderr=subprocess.DEVNULL, timeout=5,
                ).strip().splitlines()
                parent = next((line.strip() for line in pkname if line.strip()), "")
                if parent:
                    return f"/dev/{parent}"
            except Exception:
                pass
            try:
                disk = subprocess.check_output(
                    ["lsblk", "-n", "-o", "NAME,TYPE", source],
                    text=True, stderr=subprocess.DEVNULL, timeout=5,
                )
                for line in disk.splitlines():
                    parts = line.split()
                    if len(parts) >= 2 and parts[1] == "disk":
                        return f"/dev/{parts[0].lstrip('└─├─')}"
            except Exception:
                pass
            try:
                devtype = subprocess.check_output(
                    ["lsblk", "-n", "-o", "TYPE", source],
                    text=True, stderr=subprocess.DEVNULL, timeout=5,
                ).strip()
                if devtype == "disk":
                    return source
            except Exception:
                pass
        except Exception:
            pass
    return None



def _parent_disk(dev: str | None) -> str | None:
    # Walks every layer of indirection (partition, LVM LV/PV, LUKS mapper)
    # up to the underlying physical disk. A single PKNAME hop is not enough
    # for e.g. an LVM logical volume on a LUKS-encrypted partition, where
    # the immediate PKNAME is itself another non-disk device.
    dev = _disk._normal_device_path(dev)
    seen: set[str] = set()
    while dev and dev not in seen:
        seen.add(dev)
        if _disk._device_type(dev) == "disk":
            return dev
        parent = _disk._lsblk_text(["-n", "-o", "PKNAME", dev])
        if not parent:
            return None
        dev = _disk._normal_device_path(parent.splitlines()[0])
    return None



def _mount_sources(path: str, recursive: bool = False) -> set[str]:
    sources: set[str] = set()
    try:
        cmd = ["findmnt"]
        if recursive:
            cmd.append("-R")
        cmd.extend(["-n", "-o", "SOURCE", path])
        out = subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL, timeout=5)
    except Exception:
        out = ""
    for line in out.splitlines():
        source = line.strip()
        if source.startswith("/dev/"):
            sources.add(os.path.realpath(source))
    return sources



def _protected_install_disks() -> set[str]:
    protected: set[str] = set()
    for dev in {_disk._running_system_disk()}:
        disk = _disk._parent_disk(dev)
        if disk:
            protected.add(disk)
    for mount in ("/", "/boot", "/boot/efi", "/sysroot", "/run/initramfs/live", "/run/initramfs/iso"):
        for source in _disk._mount_sources(mount):
            disk = _disk._parent_disk(source)
            if disk:
                protected.add(disk)
    for source in _disk._mount_sources("/run/initramfs", recursive=True):
        disk = _disk._parent_disk(source)
        if disk:
            protected.add(disk)
    for source in _disk._mount_sources("/run/media", recursive=True):
        if _IS_LIVE_SESSION:
            disk = _disk._parent_disk(source)
            if disk:
                protected.add(disk)
    return protected



def _disk_path_is_safe(path: str) -> bool:
    base = os.path.basename(path)
    if base.startswith(("loop", "ram", "zram")):
        return False
    return path.startswith("/dev/")



def partition_has_active_mount(partition: str) -> bool:
    try:
        out = subprocess.check_output(
            ["findmnt", "-n", "-o", "TARGET", partition],
            text=True, stderr=subprocess.DEVNULL, timeout=5,
        )
        return bool(out.strip())
    except Exception:
        return False



