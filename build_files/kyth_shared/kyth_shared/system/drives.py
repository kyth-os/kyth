"""Shared utilities for managing system storage drives and NTFS compatibility links."""
from __future__ import annotations

import os
import shutil

from ..commands import run as run_command
from ..runtime_output import parse_ntfs_devices
import time
from pathlib import Path


def get_ntfs_devices() -> list[dict]:
    """Retrieve details of all NTFS partitions connected to the system using lsblk."""
    try:
        res = run_command(
            ["lsblk", "-J", "-o", "NAME,FSTYPE,LABEL,UUID,MOUNTPOINT"],
            capture_output=True,
            text=True,
            check=True,
        )
    except Exception:
        return []
    return parse_ntfs_devices(res.stdout)


def repair_ntfs_drives() -> None:
    """Scan all NTFS partitions, ensure they are mounted, and symlink steamapps/compatdata to native storage."""
    home = Path.home()
    native_compatdata = home / ".local/share/Steam/steamapps/compatdata"
    flatpak_compatdata = home / ".var/app/com.valvesoftware.Steam" / "data" / "Steam" / "steamapps" / "compatdata"

    # Ensure native directories exist
    try:
        native_compatdata.mkdir(parents=True, exist_ok=True)
        if (home / ".var/app/com.valvesoftware.Steam").is_dir():
            flatpak_compatdata.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass

    print("[kyth-ntfs-repair] Scanning for connected NTFS storage partitions...")
    partitions = get_ntfs_devices()

    if not partitions:
        print("[kyth-ntfs-repair] No NTFS partitions detected.")
        return

    print("[kyth-ntfs-repair] Found NTFS partition(s). Applying mount stabilization & Proton compatdata redirection...")

    user_uid = os.getuid()
    user_gid = os.getgid()
    opts = f"uid={user_uid},gid={user_gid},dmask=027,fmask=137,windows_names,rw"

    for dev in partitions:
        name = dev.get("name", "")
        label = dev.get("label") or "NTFS_Drive"
        uuid = dev.get("uuid") or ""
        mount = dev.get("mountpoint") or ""
        dev_path = f"/dev/{name}" if not name.startswith("/") else name

        print(f"[kyth-ntfs-repair] Processing partition: {dev_path} (UUID: {uuid or 'unknown'}, Label: {label})")

        # Mount if not already mounted
        if not mount:
            uuid_safe = uuid or name.replace("/", "_")
            mount = f"/var/mnt/ntfs_{uuid_safe}"
            print(f"[kyth-ntfs-repair] Drive not mounted. Mounting to {mount}...")
            try:
                run_command(["sudo", "mkdir", "-p", mount], check=False)
                # Try mounting with ntfs-3g
                res = run_command(
                    ["sudo", "mount", "-t", "ntfs-3g", "-o", opts, dev_path, mount],
                    capture_output=True,
                    check=False,
                )
                if res.returncode != 0:
                    # Fallback to generic mount
                    run_command(
                        ["sudo", "mount", "-o", opts, dev_path, mount],
                        capture_output=True,
                        check=False,
                    )
            except Exception as e:
                print(f"[kyth-ntfs-repair] Failed to mount {dev_path}: {e}")
                continue

        # Find Steam libraries up to 3 levels deep
        steam_dirs = []
        mount_path = Path(mount)
        if mount_path.is_dir():
            try:
                for p1 in mount_path.iterdir():
                    if p1.is_dir():
                        if p1.name.lower() == "steamapps":
                            steam_dirs.append(p1)
                            continue
                        for p2 in p1.iterdir():
                            if p2.is_dir():
                                if p2.name.lower() == "steamapps":
                                    steam_dirs.append(p2)
                                    continue
                                for p3 in p2.iterdir():
                                    if p3.is_dir():
                                        if p3.name.lower() == "steamapps":
                                            steam_dirs.append(p3)
            except Exception:
                pass

        if steam_dirs:
            for sdir in steam_dirs:
                print(f"[kyth-ntfs-repair] Found Steam library at: {sdir}")
                target_cd = sdir / "compatdata"

                if target_cd.is_symlink():
                    try:
                        resolved = target_cd.resolve()
                        print(f"  Compatdata is already symlinked to native storage: {resolved}")
                    except Exception:
                        pass
                else:
                    backup_path = None
                    if target_cd.is_dir():
                        print("  Moving existing NTFS compatdata folder to backup...")
                        backup_name = f"compatdata.bak.{int(time.time())}"
                        backup_path = target_cd.parent / backup_name
                        try:
                            # Atomic move via rename; backup restores on cancel/fail
                            target_cd.rename(backup_path)
                        except Exception:
                            try:
                                shutil.move(str(target_cd), str(backup_path))
                            except Exception as e:
                                print(f"  Failed to backup existing compatdata: {e}")
                                backup_path = None

                    # Check if native compatdata already has contents
                    try:
                        has_contents = any(native_compatdata.iterdir())
                    except Exception:
                        has_contents = False

                    if has_contents:
                        print(f"  NOTE: {native_compatdata} already holds Proton prefixes from another library.")
                        print("  Any App ID present in both will now share one Proton prefix instead of having separate ones.")

                    print(f"  Symlinking compatdata -> {native_compatdata}")
                    # Atomic symlink: tmp -> replace, fsync parent, restore backup on fail
                    tmp_link = target_cd.parent / f".compatdata.tmp.{os.getpid()}"
                    try:
                        if target_cd.exists() or target_cd.is_symlink():
                            try:
                                target_cd.unlink()
                            except Exception:
                                pass
                        tmp_link.symlink_to(native_compatdata)
                        os.replace(str(tmp_link), str(target_cd))
                        # fsync parent for power-loss safety
                        try:
                            dfd = os.open(str(target_cd.parent), os.O_DIRECTORY)
                            try:
                                os.fsync(dfd)
                            finally:
                                os.close(dfd)
                        except OSError:
                            pass
                    except Exception as e:
                        print(f"  Failed to create symlink: {e}")
                        try:
                            tmp_link.unlink()
                        except Exception:
                            pass
                        # Restore backup if we moved it
                        if backup_path is not None and backup_path.exists():
                            try:
                                if target_cd.is_symlink() or target_cd.exists():
                                    target_cd.unlink()
                            except Exception:
                                pass
                            try:
                                backup_path.rename(target_cd)
                            except Exception:
                                try:
                                    shutil.move(str(backup_path), str(target_cd))
                                except Exception:
                                    pass
        else:
            print(f"[kyth-ntfs-repair] No steamapps folder found on {mount}.")

    print("[kyth-ntfs-repair] NTFS repair complete. You can now launch Steam games directly from your NTFS drive!")
