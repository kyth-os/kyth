"""probe — _running_system_disk, _get_live_usb_disk, _parent_disk, _mount_sources, _protected_install_disks, _disk_path_is_safe, partition_has_active_mount"""

from __future__ import annotations

import logging
import os
from typing import Optional

import kyth_installer.disk as _disk

from ..config import _IS_LIVE_SESSION

_logger = logging.getLogger(__name__)

def _running_system_disk() -> str:
    # Returns the raw mount SOURCE for "/" (which may be a partition, an LVM
    # logical volume, or a LUKS dm-crypt mapping) — callers resolve this up
    # to the physical disk via _disk._parent_disk(), which walks every layer of
    # device-mapper indirection rather than assuming a single PKNAME hop.
    try:
        return _disk._findmnt_source("/")
    except Exception:
        return ""



def _get_live_usb_disk() -> Optional[str]:
    for path in ("/run/initramfs/live", "/run/initramfs/iso"):
        try:
            source = _disk._findmnt_source(path)
            if not source:
                continue
            # Single JSON path — no silent text-mode fallbacks; fail-closed
            # rather than risk handing back the live USB as a wipe candidate.
            try:
                result = _disk.run_command(
                    ["lsblk", "-J", "-o", "NAME,PKNAME,TYPE", source],
                    capture_output=True, text=True, check=True, timeout=5,
                )
                import json as _json

                data = _json.loads(result.stdout or "{}")
                for dev in data.get("blockdevices") or []:
                    pkname = (dev.get("pkname") or "").strip()
                    if pkname:
                        return f"/dev/{pkname}"
                    name = (dev.get("name") or "").strip().lstrip("└─├")
                    devtype = (dev.get("type") or "").strip()
                    if devtype == "disk":
                        if name.startswith("/dev/"):
                            return name
                        return f"/dev/{name}" if name else source
                    for child in dev.get("children") or []:
                        if (child.get("type") or "").strip() == "disk":
                            cname = (child.get("name") or "").strip().lstrip("└─├")
                            if cname.startswith("/dev/"):
                                return cname
                            if cname:
                                return f"/dev/{cname}"
                _logger.debug("_get_live_usb_disk: JSON lookup for %s returned no disk", source)
            except Exception:
                _logger.debug("_get_live_usb_disk: JSON lookup for %s failed", source, exc_info=True)
        except Exception:
            _logger.debug("_get_live_usb_disk: findmnt probe of %s failed", path, exc_info=True)
        _logger.warning("_get_live_usb_disk: all lsblk fallbacks failed for %s — live USB may be exposed as wipe candidate", source)
    return None



def _parent_disk(dev: str | None, tree: dict | None = None) -> str | None:
    # Walks every layer of indirection (partition, LVM LV/PV, LUKS mapper)
    # up to the underlying physical disk. A single PKNAME hop is not enough
    # for e.g. an LVM logical volume on a LUKS-encrypted partition, where
    # the immediate PKNAME is itself another non-disk device.
    #
    # `tree` is an optional pre-fetched _disk._lsblk_tree() snapshot: callers
    # that resolve ancestry for several devices in one operation (e.g.
    # _protected_install_disks) fetch it once and pass it through so this
    # walk costs zero further subprocess spawns per level/per call. Without
    # one, a single fresh tree is fetched here (still just one lsblk
    # invocation regardless of chain depth, vs. the old two-calls-per-level
    # scheme).
    dev = _disk._normal_device_path(dev)
    if tree is None:
        tree = _disk._lsblk_tree()
    seen: set[str] = set()
    while dev and dev not in seen:
        seen.add(dev)
        info = tree.get(dev)
        if info is None:
            # Not in the batched snapshot (e.g. it went stale, or the device
            # is named unusually) — fail-safe by resolving just this hop the
            # old way rather than giving up on the whole walk.
            if _disk._device_type(dev) == "disk":
                return dev
            parent = _disk._lsblk_text(["-n", "-o", "PKNAME", dev])
            if not parent:
                return None
            dev = _disk._normal_device_path(parent.splitlines()[0])
            continue
        if info.get("type") == "disk":
            return dev
        parent = info.get("pkname")
        if not parent:
            return None
        dev = parent
    return None



def _mount_sources(path: str, recursive: bool = False) -> set[str]:
    sources: set[str] = set()
    try:
        cmd = ["findmnt"]
        if recursive:
            cmd.append("-R")
        cmd.extend(["-n", "-o", "SOURCE", path])
        result = _disk.run_command(
            cmd, capture_output=True, text=True, check=True, timeout=5,
        )
        out = result.stdout
    except Exception:
        out = ""
    for line in out.splitlines():
        source = line.strip()
        if source.startswith("/dev/"):
            sources.add(os.path.realpath(source))
    return sources



def _protected_install_disks(tree: dict | None = None, running_disk: str | None = None) -> set[str]:
    # Resolves ancestry for up to ~8 mount sources (running-system disk plus
    # every protected mountpoint). Fetching the device tree once up front
    # means every one of those _parent_disk() calls below is a dict walk,
    # not a fresh round of lsblk spawns.
    if tree is None:
        tree = _disk._lsblk_tree()
    if running_disk is None:
        running_disk = _disk._running_system_disk()
    protected: set[str] = set()
    for dev in {running_disk}:
        disk = _disk._parent_disk(dev, tree=tree)
        if disk:
            protected.add(disk)
    for mount in ("/", "/boot", "/boot/efi", "/sysroot", "/run/initramfs/live", "/run/initramfs/iso"):
        for source in _disk._mount_sources(mount):
            disk = _disk._parent_disk(source, tree=tree)
            if disk:
                protected.add(disk)
    for source in _disk._mount_sources("/run/initramfs", recursive=True):
        disk = _disk._parent_disk(source, tree=tree)
        if disk:
            protected.add(disk)
    for source in _disk._mount_sources("/run/media", recursive=True):
        if _IS_LIVE_SESSION:
            disk = _disk._parent_disk(source, tree=tree)
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
        result = _disk.run_command(
            ["findmnt", "-n", "-o", "TARGET", partition],
            capture_output=True, text=True, check=True, timeout=5,
        )
        out = result.stdout
        return bool(out.strip())
    except Exception:
        return False


