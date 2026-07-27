"""disk inspection package"""

from __future__ import annotations

import subprocess  # noqa: F401 -- compatibility re-export used by callers/tests

from ..config import EFI_PART_GUID, MIN_KYTHOS_BYTES, _IS_LIVE_SESSION  # noqa: F401
from ..runner import run_command  # noqa: F401

from ._util import (  # noqa: F401
    _safe_int,
    _normal_device_path,
    _lsblk_text,
    _lsblk_blockdevices,
    _findmnt_source,
    _device_type,
    _block_size_bytes,
)

from ._probe import (  # noqa: F401
    _running_system_disk,
    _get_live_usb_disk,
    _parent_disk,
    _mount_sources,
    _protected_install_disks,
    _disk_path_is_safe,
    partition_has_active_mount,
)

from ._query import (  # noqa: F401
    _partition_mountpoints,
    _is_active_mount,
    _descendant_mountpoints,
    list_disks,
    list_partitions,
    list_free_space,
    _partition_number,
    _partition_size_bytes,
    _partition_start_bytes,
    _partitions_after,
    _latest_partition_on_disk,
    list_filesystems,
)

from ._lookup import (  # noqa: F401
    find_efi_partition,
    get_root_partition,
)

from kyth_shared import human_bytes as _human_size  # noqa: F401
