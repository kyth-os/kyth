from dataclasses import dataclass, field
from importlib import import_module
from typing import Callable

from .qt import QWidget
PageFactory = Callable[[], QWidget]


@dataclass(frozen=True)
class PageDescriptor:
    key: str
    title: str
    section: str | None
    icon_names: tuple[str, ...]
    factory: PageFactory
    search_description: str = ""
    search_terms: tuple[str, ...] = field(default_factory=tuple)
    profile: str = "all"

    @property
    def searchable_text(self) -> str:
        return " ".join((self.key, self.title, self.search_description, *self.search_terms)).lower()


def _page_factory(module_name: str, class_name: str, *args, **kwargs) -> PageFactory:
    def factory() -> QWidget:
        module = import_module(f".{module_name}", __package__)
        page_class = getattr(module, class_name)
        return page_class(*args, **kwargs)

    return factory


def descriptor_from_nav_item(
    *,
    section: str | None,
    icon_names: tuple[str, ...],
    key: str,
    title: str,
    factory: PageFactory,
    search_metadata: tuple[str, str, list[str]] | None = None,
) -> PageDescriptor:
    if search_metadata is None:
        return PageDescriptor(
            key=key,
            title=title,
            section=section,
            icon_names=icon_names,
            factory=factory,
        )
    search_title, description, terms = search_metadata
    return PageDescriptor(
        key=key,
        title=search_title or title,
        section=section,
        icon_names=icon_names,
        factory=factory,
        search_description=description,
        search_terms=tuple(terms),
    )


def descriptors_from_nav_groups(nav_groups, search_metadata) -> list[PageDescriptor]:
    descriptors: list[PageDescriptor] = []
    for section, items in nav_groups:
        for icon_names, _glyph, title, key, factory in items:
            descriptors.append(
                descriptor_from_nav_item(
                    section=section,
                    icon_names=tuple(icon_names),
                    key=key,
                    title=title,
                    factory=factory,
                    search_metadata=search_metadata.get(key),
                )
            )
    return descriptors


def visible_for_profile(descriptor: PageDescriptor, profile: str) -> bool:
    if descriptor.profile == "gaming":
        return profile == "gaming"
    if descriptor.profile == "work":
        return profile == "work"
    return True


NavItem = tuple[tuple[str, ...], str, str, str, PageFactory]


SEARCH_ITEMS: dict[str, tuple[str, str, list[str]]] = {
    "Welcome": ("Home", "Review this PC, pick a preset, and jump into common setup tasks.", ["Control Panel", "PC focus", "Switch focus", "Everyday preset", "Gaming preset"]),
    "Gaming": ("Gaming", "Install launchers, scan game libraries, set up capture, saves, and migration helpers.", ["Steam", "Epic Games", "GOG", "Game Pass", "Xbox app", "Xbox Game Bar", "Game capture", "Instant replay", "Battle.net", "screen record", "record gameplay"]),
    "Performance": ("Performance", "Tune power, scheduler, and desktop performance behavior.", ["Task Manager", "Mission Center", "Performance mode", "slow game", "low FPS", "stutter", "lag", "fan noise", "battery life"]),
    "Compatibility": ("Compatibility", "Check known game support, ProtonDB context, and blocked anti-cheat titles.", ["Will my games work", "ProtonDB", "Anti-cheat", "game crashes", "game won't launch", "blocked game"]),
    "Controllers": ("Controllers", "Pair, test, and troubleshoot game controllers.", ["Xbox controller", "PlayStation controller", "Game controllers", "controller not working", "gamepad not detected"]),
    "App Store": ("App Store", "Install trusted Flatpaks, find familiar app alternatives, and manage AppImages.", ["Add or remove programs", "Apps & features", "Install apps", "Uninstall a program", "dnf install", "rpm", "exe installer", "downloaded installer", "Flathub"]),
    "Work Setup": ("Work Setup", "Set up office, mail, focus sessions, and workday conveniences.", ["Microsoft 365", "Office", "Outlook", "Focus Assist", "Pomodoro"]),
    "Move Files": ("Move Files", "Copy files, saves, libraries, bookmarks, fonts, and familiar workflows.", ["Transfer my files", "Copy game saves", "Snipping Tool", "PowerToys", "Phone Link", "Nearby Sharing", "LocalSend", "Remote Desktop", "WSL"]),
    "Update": ("Updates", "Check OS updates, staged images, rollback status, and auto-update settings.", ["System Update", "Check for updates", "Restart pending", "rollback", "undo update", "bad update"]),
    "Hardware": ("Hardware", "Inspect graphics, displays, audio, Bluetooth, storage, and device health.", ["Device Manager", "Display", "Sound", "Bluetooth", "no audio", "no sound", "speaker", "microphone", "wifi", "wi-fi", "printer", "monitor", "black screen"]),
    "Plasma Wayland": ("Plasma & Wayland", "Check portals, PipeWire capture, display settings, shortcuts, and Plasma session repair.", ["Wayland", "Plasma", "KDE", "Screen sharing", "PipeWire", "Portal", "Display settings", "Window rules", "Shortcuts", "screenshot", "screen shot", "screen capture", "blank screen share", "black screen", "display scale"]),
    "Diagnostics": ("Health Report", "Run system checks and gather useful troubleshooting information.", ["System information", "Diagnostics", "Security", "Sign-in options", "Fingerprint"]),
    "Repair": ("Repair", "Rollback, restore, collect logs, and open recovery tools when something feels off.", ["Troubleshoot", "Recovery", "Reset this PC", "terminal", "PowerShell", "Quick Assist", "Remote Assistance", "broken", "restore layout", "missing apps", "remote help"]),
    "VPN": ("VPN", "Connect to VPN profiles, including GlobalProtect-style work VPNs.", ["VPN settings", "GlobalProtect"]),
    "Network Shares": ("Network Shares", "Map SMB/CIFS shares and configure mount behavior.", ["Map network drive", "Shared folders"]),
    "Cloud Storage": ("Cloud Storage", "Set up cloud sync and copy workflows for common providers.", ["OneDrive", "Google Drive", "Dropbox"]),
    "NVIDIA": ("NVIDIA Drivers", "Check NVIDIA driver state and open driver actions.", ["Graphics drivers", "GeForce"]),
    "Kernel": ("Kernel", "Choose installed kernels and understand advanced boot options.", ["Advanced system settings"]),
    "Channels": ("Channels", "Choose stable or testing update channels.", ["Update channel", "Insider program"]),
    "Feedback": ("Feedback", "Send feedback or report a problem with optional system details.", ["Feedback Hub", "Send feedback"]),
}



SEARCH_ALIASES: dict[str, list[str]] = {
    "Welcome": ["Home", "Control Panel", "PC focus", "Everyday preset", "Gaming preset", "Switch focus"],
    "Gaming": ["Gaming", "Game launchers", "Steam", "Epic Games", "GOG", "Game Pass", "Xbox app", "Xbox Game Bar", "Game Bar", "Game capture", "Instant replay", "Battle.net", "Screen record", "Record gameplay"],
    "Performance": ["Performance", "Task Manager", "Mission Center", "Slow game", "Low FPS", "Stutter", "Lag", "Fan noise", "Battery life"],
    "Compatibility": ["Game compatibility", "Will my games work", "ProtonDB", "Game crashes", "Game won't launch", "Blocked game"],
    "Controllers": ["Controllers", "Game controllers", "Xbox controller", "PlayStation controller", "Controller not working", "Gamepad not detected"],
    "App Store": ["Add or remove programs", "Apps & features", "Install apps", "App store", "Uninstall a program", "dnf install", "rpm", "exe installer", "downloaded installer", "Flathub"],
    "Work Setup": ["Work setup", "Microsoft 365", "Office", "Outlook", "PST import", "Focus Assist", "Focus Sessions", "Do Not Disturb", "Pomodoro"],
    "Move Files": ["Move files", "Transfer my files", "PC migration", "Copy game saves", "Keyboard shortcuts", "Snipping Tool", "familiar shortcuts", "PowerToys", "PowerToys Run", "FancyZones", "PowerRename", "Always on Top", "Keyboard Manager", "Awake", "Color Picker", "Copy my files", "Import bookmarks", "Bookmarks", "Phone Link", "Connected Devices", "KDE Connect", "Dynamic Lock", "trusted phone", "cross-device clipboard", "ring phone", "SMS", "send text", "text messages", "Nearby Sharing", "Nearby Share", "Quick Share", "LocalSend", "Send to device", "Wallpaper", "Desktop background", "system fonts", "Segoe UI", "Calibri", "Rescue game saves", "Sticky Notes", "Remote Desktop connections", "RDP", "mstsc", "KRDC", "WSL", "Linux subsystem", "Ubuntu", "Distrobox"],
    "Update": ["Check for updates", "System Update", "Updates", "Rollback", "Undo update", "Bad update"],
    "Hardware": ["Hardware", "Device Manager", "Display", "Sound", "Bluetooth", "No audio", "No sound", "Speaker", "Microphone", "Wi-Fi", "Wifi", "Printer", "Monitor", "Black screen"],
    "Plasma Wayland": ["Plasma", "Wayland", "KDE", "Screen sharing", "PipeWire", "Portal", "xdg desktop portal", "Display settings", "VRR", "HDR", "Scale", "Shortcuts", "Window rules", "Restart Plasma", "Screenshot", "Screen shot", "Screen capture", "Blank screen share", "Display scale"],
    "Diagnostics": ["Health report", "System information", "Diagnostics", "Sign-in options", "Fingerprint", "Passkeys", "Security"],
    "Repair": ["Repair", "Troubleshoot", "Recovery", "Reset this PC", "Rollback", "terminal", "command prompt", "PowerShell", "Quick Assist", "Remote Assistance", "RustDesk", "Remote Desktop", "Restore my apps", "Restore my setup", "PC backup", "Restore layout", "Missing apps", "Remote help"],
    "VPN": ["VPN", "VPN settings"],
    "Network Shares": ["Network shares", "Map network drive", "Shared folders"],
    "Cloud Storage": ["Cloud storage", "OneDrive", "Google Drive", "Dropbox"],
    "NVIDIA": ["NVIDIA drivers", "Graphics drivers", "GeForce"],
    "Kernel": ["Kernel", "Advanced system settings"],
    "Channels": ["Update channel", "Channels", "Insider program"],
    "Feedback": ["Feedback", "Send feedback", "Feedback Hub"],
}



PROBLEM_ROUTES: dict[str, str] = {
    "no audio": "Hardware",
    "no sound": "Hardware",
    "microphone not working": "Hardware",
    "bluetooth not working": "Hardware",
    "wifi not working": "Hardware",
    "printer setup": "Hardware",
    "slow game": "Performance",
    "low fps": "Performance",
    "game stutter": "Performance",
    "game won't launch": "Compatibility",
    "game crashes": "Compatibility",
    "controller not working": "Controllers",
    "black screen": "Plasma Wayland",
    "screen sharing is blank": "Plasma Wayland",
    "take screenshot": "Plasma Wayland",
    "restore layout": "Repair",
    "missing apps": "Repair",
    "rollback update": "Update",
    "undo update": "Update",
}


def get_nav_groups(navigate) -> list[tuple[str | None, list[NavItem]]]:
    from .core import _detect_nvidia

    nav_groups: list[tuple[str | None, list[NavItem]]] = [
        (None, [
            (("go-home",), "⌂", "Home", "Welcome", _page_factory("page_welcome", "WelcomePage", navigate=navigate)),
        ]),
        ("Gaming", [
            (("applications-games", "input-gaming"), "◉", "Gaming", "Gaming", _page_factory("page_gaming", "GamingPage")),
            (("speedometer", "utilities-system-monitor"), "⚡", "Performance", "Performance", _page_factory("page_performance", "PerformancePage")),
            (("dialog-ok-apply", "checkmark"), "◎", "Compatibility", "Compatibility", _page_factory("page_compatibility", "CompatibilityPage")),
            (("input-gamepad", "input-gaming"), "⎮", "Controllers", "Controllers", _page_factory("page_controllers", "ControllerPage")),
        ]),
        ("Apps", [
            (("plasmadiscover", "applications-all"), "⬡", "Discover Apps", "App Store", _page_factory("page_software", "SoftwarePage", initial_tab=4, store_landing=True)),
            (("x-office-document", "applications-office"), "▤", "Work Setup", "Work Setup", _page_factory("page_work", "WorkSetupPage", navigate=navigate)),
            (("document-import", "drive-harddisk"), "⇄", "Move Files", "Move Files", _page_factory("page_windows_migration", "WindowsMigrationPage", navigate=navigate)),
        ]),
        ("System", [
            (("system-software-update", "update-none"), "↻", "Updates", "Update", _page_factory("page_update", "UpdatePage")),
            (("computer", "computer-laptop"), "◈", "Hardware", "Hardware", _page_factory("page_hardware", "HardwarePage", navigate=navigate)),
            (("preferences-desktop-display", "video-display"), "▣", "Plasma & Wayland", "Plasma Wayland", _page_factory("page_plasma_wayland", "PlasmaWaylandPage")),
            (("view-statistics", "office-chart-bar"), "◌", "Health Report", "Diagnostics", _page_factory("page_diagnostics", "DiagnosticsPage")),
            (("tools-wizard", "configure"), "⚠", "Repair", "Repair", _page_factory("page_repair", "RepairPage", navigate=navigate)),
        ]),
        ("Network & Internet", [
            (("network-vpn", "security-high"), "⬡", "VPN", "VPN", _page_factory("page_vpn", "VpnPage")),
            (("folder-network", "network-workgroup"), "◫", "Network Shares", "Network Shares", _page_factory("page_network_shares", "NetworkSharesPage")),
            (("folder-cloud", "weather-clouds"), "☁", "Cloud Storage", "Cloud Storage", _page_factory("page_cloud_storage", "CloudStoragePage")),
        ]),
    ]

    advanced_items: list[NavItem] = []
    if _detect_nvidia():
        advanced_items.append((("video-display", "preferences-desktop-display"), "▣", "NVIDIA Drivers", "NVIDIA", _page_factory("page_nvidia", "NvidiaPage")))
    advanced_items.append((("cpu", "applications-system"), "◌", "Kernel", "Kernel", _page_factory("page_kernel", "KernelPage")))
    advanced_items.append((("vcs-branch", "system-switch-user"), "⎇", "Channels", "Channels", _page_factory("page_branches", "BranchesPage")))
    advanced_items.append((("mail-send", "mail-message"), "✉", "Feedback", "Feedback", _page_factory("page_feedback", "FeedbackPage")))
    nav_groups.append(("Advanced", advanced_items))

    return nav_groups
