"""Windows migration domain services (storage, bookmarks, extras, HW sanity)."""
from .bookmarks import (
    _read_chromium_bookmarks,
    _read_firefox_bookmarks,
    _scan_windows_bookmarks,
    _write_bookmarks_html,
    read_chromium_bookmarks,
    read_firefox_bookmarks,
    scan_windows_bookmarks,
    write_bookmarks_html,
)
from .extras import (
    _best_profile_wallpaper,
    _copy_game_saves,
    _copy_windows_fonts,
    _dir_contains_saves,
    _export_sticky_notes,
    _image_extension,
    _import_rdp_bookmarks,
    _parse_rdp_file,
    _read_sticky_notes,
    _scan_profile_game_saves,
    _scan_windows_extras,
    best_profile_wallpaper,
    copy_game_saves,
    copy_windows_fonts,
    dir_contains_saves,
    export_sticky_notes,
    image_extension,
    import_rdp_bookmarks,
    parse_rdp_file,
    read_sticky_notes,
    scan_profile_game_saves,
    scan_windows_extras,
)
from .hardware_sanity import (
    _collect_hw_sanity,
    _hw_display_row,
    collect_hw_sanity,
    hw_display_row,
)
from .storage import (
    _folder_sizes_calc,
    _unlock_bitlocker_drive,
    _windows_folder_dest,
    folder_sizes_calc,
    unlock_bitlocker_drive,
    windows_folder_dest,
)
from .takeout import (
    enrich_with_extras,
    summarize_takeout,
    takeout_checklist,
)

# pylint: disable=undefined-all-variable
# UserFilesCopyWorker/WindowsLibraryWorker resolve lazily via __getattr__
# below (Qt-free import path) — pylint's static __all__ checker doesn't
# follow PEP 562 module __getattr__.
__all__ = [
    "UserFilesCopyWorker",
    "WindowsLibraryWorker",
    "_best_profile_wallpaper",
    "_collect_hw_sanity",
    "_copy_game_saves",
    "_copy_windows_fonts",
    "_dir_contains_saves",
    "_export_sticky_notes",
    "_folder_sizes_calc",
    "_hw_display_row",
    "_image_extension",
    "_import_rdp_bookmarks",
    "_parse_rdp_file",
    "_read_chromium_bookmarks",
    "_read_firefox_bookmarks",
    "_read_sticky_notes",
    "_scan_profile_game_saves",
    "_scan_windows_bookmarks",
    "_scan_windows_extras",
    "_unlock_bitlocker_drive",
    "_windows_folder_dest",
    "_write_bookmarks_html",
    "best_profile_wallpaper",
    "collect_hw_sanity",
    "copy_game_saves",
    "copy_windows_fonts",
    "dir_contains_saves",
    "enrich_with_extras",
    "export_sticky_notes",
    "folder_sizes_calc",
    "hw_display_row",
    "image_extension",
    "import_rdp_bookmarks",
    "parse_rdp_file",
    "read_chromium_bookmarks",
    "read_firefox_bookmarks",
    "read_sticky_notes",
    "scan_profile_game_saves",
    "scan_windows_bookmarks",
    "scan_windows_extras",
    "summarize_takeout",
    "takeout_checklist",
    "unlock_bitlocker_drive",
    "windows_folder_dest",
    "write_bookmarks_html",
]
# pylint: enable=undefined-all-variable


def __getattr__(name: str):
    """Lazy re-export of Qt workers (pure package import stays Qt-free)."""
    if name in {"WindowsLibraryWorker", "UserFilesCopyWorker"}:
        from ..workers.windows_migration import UserFilesCopyWorker, WindowsLibraryWorker
        return {
            "WindowsLibraryWorker": WindowsLibraryWorker,
            "UserFilesCopyWorker": UserFilesCopyWorker,
        }[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
