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


@dataclass(frozen=True)
class PulseRailItem:
    """One icon-rail destination. Landing is the page the rail button opens."""

    dest: str
    landing_key: str
    title: str
    icon_names: tuple[str, ...]
    glyph: str
    hint: str


PULSE_RAIL: tuple[PulseRailItem, ...] = (
    PulseRailItem("Pulse", "Welcome", "Pulse", ("go-home",), "⌂", "Health and the next step"),
    PulseRailItem("Play", "Play", "Play", ("applications-games", "input-gaming"), "▶", "Games, boost, and controllers"),
    PulseRailItem("Apps", "Apps", "Apps", ("plasmadiscover", "applications-all"), "⬡", "Discover apps and work setup"),
    PulseRailItem("This PC", "This PC", "This PC", ("computer", "computer-laptop"), "◈", "Health, updates, and hardware"),
    PulseRailItem("Move In", "Move In", "Move In", ("document-import", "drive-harddisk"), "⇄", "Files, saves, and familiar workflows"),
)

# Child pages stay in the stack for search; the rail highlights the destination.
_DESTINATION_PAGES: dict[str, tuple[str, ...]] = {
    "Pulse": ("Welcome",),
    "Play": ("Play", "Gaming", "Performance", "Compatibility", "Controllers"),
    "Apps": ("Apps", "App Store", "Work Setup"),
    "This PC": (
        "This PC",
        "Guardian",
        "Update",
        "Hardware",
        "Plasma Wayland",
        "Diagnostics",
        "Repair",
        "NVIDIA",
        "Kernel",
        "Channels",
        "Just",
        "Feedback",
    ),
    "Move In": ("Move In", "Move Files", "Cloud Storage", "Network Shares", "VPN"),
}

PAGE_DESTINATION: dict[str, str] = {
    page: dest for dest, pages in _DESTINATION_PAGES.items() for page in pages
}


def destination_for_page(key: str) -> str:
    """Map any Hub page key to its Pulse rail destination."""
    return PAGE_DESTINATION.get(key, "Pulse")


# Child pages folded into the hub as sections. Unlisted dest pages (NVIDIA,
# Channels, Just, Feedback) still open on their own stack slot.
DESTINATION_SECTIONS: dict[str, tuple[str, ...]] = {
    "Play": ("Gaming", "Performance", "Compatibility", "Controllers"),
    "Apps": ("App Store", "Work Setup"),
    "This PC": ("Guardian", "Update", "Hardware", "Plasma Wayland", "Diagnostics", "Repair"),
    "Move In": ("Move Files", "Cloud Storage", "Network Shares", "VPN"),
}


def landing_for_page(key: str) -> str:
    """Rail landing page that should be on screen for this key."""
    dest = destination_for_page(key)
    for item in PULSE_RAIL:
        if item.dest == dest:
            return item.landing_key
    return key


def section_for_page(key: str) -> str | None:
    """Hub section to show, or None to open the page's own stack slot."""
    dest = destination_for_page(key)
    if key == landing_for_page(key):
        return None
    if key in DESTINATION_SECTIONS.get(dest, ()):
        return key
    return None


def _page_factory(module_name: str, class_name: str, *args, **kwargs) -> PageFactory:
    def factory() -> QWidget:
        module = import_module(f".{module_name}", __package__)
        page_class = getattr(module, class_name)
        return page_class(*args, **kwargs)

    return factory


# Sidebar focus: gaming pages only in gaming focus; Work Setup in everyday/work.
_PAGE_PROFILES: dict[str, str] = {
    "Gaming": "gaming",
    "Performance": "gaming",
    "Compatibility": "gaming",
    "Controllers": "gaming",
    "Work Setup": "work",
}


def descriptor_from_nav_item(
    *,
    section: str | None,
    icon_names: tuple[str, ...],
    key: str,
    title: str,
    factory: PageFactory,
    search_metadata: "tuple[str, str, list[str]] | SearchItem | None" = None,
    profile: str | None = None,
) -> PageDescriptor:
    resolved_profile = profile if profile is not None else _PAGE_PROFILES.get(key, "all")
    if search_metadata is None:
        return PageDescriptor(
            key=key,
            title=title,
            section=section,
            icon_names=icon_names,
            factory=factory,
            profile=resolved_profile,
        )
    if isinstance(search_metadata, SearchItem):
        search_title, description, terms = search_metadata.title, search_metadata.description, search_metadata.terms
    else:
        search_title, description, terms = search_metadata
    return PageDescriptor(
        key=key,
        title=search_title or title,
        section=section,
        icon_names=icon_names,
        factory=factory,
        search_description=description,
        search_terms=tuple(terms),
        profile=resolved_profile,
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
    """Match MainWindow sidebar focus: gaming-only vs everyday/work Work Setup."""
    if descriptor.profile == "gaming":
        return profile == "gaming"
    if descriptor.profile == "work":
        # Everyday and work focuses keep Work Setup; gaming focus hides it.
        return profile != "gaming"
    return True


@dataclass(frozen=True, slots=True)
class SearchItem:
    """S4: typed search entry — use SearchItem instead of raw tuple."""
    title: str
    description: str
    terms: tuple[str, ...] = ()


NavItem = tuple[tuple[str, ...], str, str, str, PageFactory]


# Back-compat: SEARCH_ITEMS entries are now SearchItem; helpers below accept both
def _search_item_title(item) -> str:
    return item.title if isinstance(item, SearchItem) else item[0]

def _search_item_desc(item) -> str:
    return item.description if isinstance(item, SearchItem) else item[1]

def _search_item_terms(item) -> tuple[str, ...]:
    if isinstance(item, SearchItem):
        return item.terms
    return tuple(item[2]) if isinstance(item[2], (list, tuple)) else ()


SEARCH_ITEMS: dict[str, SearchItem] = {
    "Welcome": SearchItem("Pulse", "See this PC's health and the one next step.", ("Home", "Control Panel", "System Hub", "PC focus", "Everyday preset", "Gaming preset", "Switch focus", "Dashboard")),
    "Play": SearchItem("Play", "Open games, launchers, boost, controllers, and compatibility.", ("Gaming", "Game launchers", "Steam", "Library")),
    "Apps": SearchItem("Apps", "Install trusted apps and set up work.", ("Discover", "App Store", "Work Setup")),
    "This PC": SearchItem("This PC", "Health, updates, hardware, and repair in one place.", ("Device Manager", "System", "Guardian", "Updates")),
    "Gaming": SearchItem("Gaming", "Install launchers, scan game libraries, set up capture, saves, and migration helpers.", ("Game launchers", "Steam", "Epic Games", "GOG", "Game Pass", "Xbox app", "Xbox Game Bar", "Game Bar", "Game capture", "Instant replay", "Battle.net", "Screen record", "Record gameplay")),
    "Performance": SearchItem("Performance", "Tune power, scheduler, and desktop performance behavior.", ("Task Manager", "Mission Center", "Performance mode", "Slow game", "Low FPS", "Stutter", "Lag", "Fan noise", "Battery life")),
    "Compatibility": SearchItem("Compatibility", "Check known game support, ProtonDB context, and blocked anti-cheat titles.", ("Game compatibility", "Will my games work", "ProtonDB", "Anti-cheat", "Game crashes", "Game won't launch", "Blocked game")),
    "Controllers": SearchItem("Controllers", "Pair, test, and troubleshoot game controllers.", ("Game controllers", "Xbox controller", "PlayStation controller", "Controller not working", "Gamepad not detected")),
    "App Store": SearchItem("App Store", "Install trusted Flatpaks, find familiar app alternatives, and manage AppImages.", ("Add or remove programs", "Apps & features", "Install apps", "Uninstall a program", "dnf install", "rpm", "exe installer", "downloaded installer", "Flathub")),
    "Work Setup": SearchItem("Work Setup", "Set up office, mail, focus sessions, and workday conveniences.", ("Microsoft 365", "Office", "Outlook", "PST import", "Focus Assist", "Focus Sessions", "Do Not Disturb", "Pomodoro")),
    "Move In": SearchItem("Move In", "Bring files, games, apps, and familiar habits over in four steps.", ("Transfer my files", "PC migration", "Move Files", "Windows migration")),
    "Move Files": SearchItem("Move Files", "Copy files, saves, libraries, bookmarks, fonts, and familiar workflows.", ("Transfer my files", "PC migration", "Copy game saves", "Keyboard shortcuts", "Snipping Tool", "familiar shortcuts", "PowerToys", "PowerToys Run", "FancyZones", "PowerRename", "Always on Top", "Keyboard Manager", "Awake", "Color Picker", "Copy my files", "Import bookmarks", "Bookmarks", "Phone Link", "Connected Devices", "KDE Connect", "Dynamic Lock", "trusted phone", "cross-device clipboard", "ring phone", "SMS", "send text", "text messages", "Nearby Sharing", "Nearby Share", "Quick Share", "LocalSend", "Send to device", "Wallpaper", "Desktop background", "system fonts", "Segoe UI", "Calibri", "Rescue game saves", "Sticky Notes", "Remote Desktop connections", "RDP", "mstsc", "KRDC", "WSL", "Linux subsystem", "Ubuntu", "Distrobox")),
    "Display": SearchItem("Display", "HDR, VRR, night light, and monitor layout.", ("HDR", "VRR", "Night Light", "Display Settings", "Monitor layout", "Refresh rate")),
    "Clipboard": SearchItem("Clipboard", "Clipboard history and PowerToys Run palette.", ("Clipboard history", "Win+V", "PowerToys Run", "Ctrl+K", "Command palette", "FancyZones", "PowerRename")),
    "Bluetooth Audio": SearchItem("Bluetooth Audio", "LDAC, headset mic, and per-app audio routing.", ("Bluetooth headset", "LDAC", "Microphone", "Audio switch", "PipeWire")),
    "Printer": SearchItem("Printer", "Add printers and scanners with one click.", ("Add printer", "Scanner", "CUPS", "Skanlite")),
    "Battery": SearchItem("Battery", "Fan curves, power caps, and sleep drain.", ("Battery", "Fan noise", "Sleep", "Suspend", "Power cap")),
    "Game Boost": SearchItem("Game Boost", "Latency, scheduler, and MangoHud overlay.", ("Game Boost", "Latency", "scx", "MangoHud", "Stutter")),
    "Update": SearchItem("Updates", "Check OS updates, staged images, rollback status, and auto-update settings.", ("Check for updates", "System Update", "Restart pending", "Rollback", "Undo update", "Bad update")),
    "Hardware": SearchItem("Hardware", "Inspect graphics, displays, audio, Bluetooth, storage, and device health.", ("Device Manager", "Display", "Sound", "Bluetooth", "No audio", "No sound", "Speaker", "Microphone", "Wi-Fi", "Wifi", "Printer", "Monitor", "Black screen")),
    "Plasma Wayland": SearchItem("Desktop & displays", "Check portals, PipeWire capture, display settings, shortcuts, and Plasma session repair.", ("Plasma", "Wayland", "Plasma & Wayland", "KDE", "Screen sharing", "PipeWire", "Portal", "xdg desktop portal", "Display settings", "VRR", "HDR", "Scale", "Shortcuts", "Window rules", "Restart Plasma", "Screenshot", "Screen shot", "Screen capture", "Blank screen share", "Black screen", "Display scale")),
    "Diagnostics": SearchItem("Health Report", "Run system checks and gather useful troubleshooting information.", ("System information", "Diagnostics", "Sign-in options", "Fingerprint", "Passkeys", "Security")),
    "Guardian": SearchItem("Guardian", "Self-healing: automatic health checks, safe fixes, history, and optional local AI diagnosis.", ("Guardian", "Self heal", "Self-healing", "Auto repair", "Fix automatically", "Health check", "Supervisor", "AI repair", "Kyth Guardian", "no audio", "flatpak broken", "bluetooth not working", "wifi not working")),
    "Repair": SearchItem("Repair", "Rollback, restore, collect logs, and open recovery tools when something feels off.", ("Troubleshoot", "Recovery", "Reset this PC", "Rollback", "terminal", "command prompt", "PowerShell", "Quick Assist", "Remote Assistance", "RustDesk", "Remote Desktop", "Restore my apps", "Restore my setup", "PC backup", "Restore layout", "Missing apps", "Remote help", "broken")),
    "VPN": SearchItem("VPN", "Connect to VPN profiles, including GlobalProtect-style work VPNs.", ("VPN settings", "GlobalProtect")),
    "Network Shares": SearchItem("Network Shares", "Map SMB/CIFS shares and configure mount behavior.", ("Map network drive", "Shared folders")),
    "Cloud Storage": SearchItem("Cloud Storage", "Set up cloud sync and copy workflows for common providers.", ("OneDrive", "Google Drive", "Dropbox")),
    "NVIDIA": SearchItem("NVIDIA Drivers", "Check NVIDIA driver state and open driver actions.", ("Graphics drivers", "GeForce")),
    "Kernel": SearchItem("Kernel", "Choose installed kernels and understand advanced boot options.", ("Advanced system settings",)),
    "Channels": SearchItem("Update channel", "Choose stable or testing update channels.", ("Channels", "Insider program", "Update channel")),
    "Just": SearchItem("Recipes", "Run Just recipes from System Hub without opening a terminal.", ("Just", "Just Recipes", "ujust", "Recipes")),
    "Feedback": SearchItem("Feedback", "Send feedback or report a problem with optional system details.", ("Send feedback", "Feedback Hub")),
}



PROBLEM_ROUTES: dict[str, str] = {
    "guardian": "Guardian",
    "self heal": "Guardian",
    "auto repair": "Guardian",
    "fix automatically": "Guardian",
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
    # No _detect_nvidia() call here — this used to gate the "NVIDIA Drivers"
    # nav item, but get_nav_groups() runs synchronously in MainWindow.__init__
    # before any window is shown, so an lspci call here blocked the whole
    # app's startup. The NVIDIA item is always included now; MainWindow
    # hides it by default and reveals it via a background probe (see
    # windows.py's _refresh_nvidia_nav_visibility).
    nav_groups: list[tuple[str | None, list[NavItem]]] = [
        (None, [
            (("go-home",), "⌂", "Pulse", "Welcome", _page_factory("page_welcome", "WelcomePage", navigate=navigate)),
            (("applications-games", "input-gaming"), "▶", "Play", "Play", _page_factory("page_hub", "PlayHubPage", navigate=navigate)),
            (("plasmadiscover", "applications-all"), "⬡", "Apps", "Apps", _page_factory("page_hub", "AppsHubPage", navigate=navigate)),
            (("computer", "computer-laptop"), "◈", "This PC", "This PC", _page_factory("page_hub", "ThisPcHubPage", navigate=navigate)),
            (("document-import", "drive-harddisk"), "⇄", "Move In", "Move In", _page_factory("page_hub", "MoveInHubPage", navigate=navigate)),
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
            (("shield", "security-high"), "⬢", "Guardian", "Guardian", _page_factory("page_guardian", "GuardianPage", navigate=navigate)),
            (("system-software-update", "update-none"), "↻", "Updates", "Update", _page_factory("page_update", "UpdatePage", navigate=navigate)),
            (("computer", "computer-laptop"), "◈", "Hardware", "Hardware", _page_factory("page_hardware", "HardwarePage", navigate=navigate)),
            (("preferences-desktop-display", "video-display"), "▣", "Desktop & displays", "Plasma Wayland", _page_factory("page_plasma_wayland", "PlasmaWaylandPage")),
            (("view-statistics", "office-chart-bar"), "◌", "Health Report", "Diagnostics", _page_factory("page_diagnostics", "DiagnosticsPage", navigate=navigate)),
            (("tools-wizard", "configure"), "⚠", "Repair", "Repair", _page_factory("page_repair", "RepairPage", navigate=navigate)),
        ]),
        ("Network & Internet", [
            (("network-vpn", "security-high"), "⬡", "VPN", "VPN", _page_factory("page_vpn", "VpnPage")),
            (("folder-network", "network-workgroup"), "◫", "Network Shares", "Network Shares", _page_factory("page_network_shares", "NetworkSharesPage")),
            (("folder-cloud", "weather-clouds"), "☁", "Cloud Storage", "Cloud Storage", _page_factory("page_cloud_storage", "CloudStoragePage")),
        ]),
    ]

    advanced_items: list[NavItem] = [
        (("video-display", "preferences-desktop-display"), "▣", "NVIDIA Drivers", "NVIDIA", _page_factory("page_nvidia", "NvidiaPage")),
    ]
    # Kernel removed from Advanced nav — now hidden behind Gaming → Tuning → Advanced (Fedora default, Cachy opt-in via MOK). Keep page factory for deep-link/search only.
    # advanced_items.append((("cpu", "applications-system"), "◌", "Kernel", "Kernel", _page_factory("page_kernel", "KernelPage")))
    advanced_items.append((("vcs-branch", "system-switch-user"), "⎇", "Update channel", "Channels", _page_factory("page_branches", "BranchesPage")))
    advanced_items.append((("application-x-executable", "utilities-terminal"), "▶", "Recipes", "Just", _page_factory("page_just", "JustPage")))
    advanced_items.append((("mail-send", "mail-message"), "✉", "Feedback", "Feedback", _page_factory("page_feedback", "FeedbackPage")))
    nav_groups.append(("Advanced", advanced_items))

    return nav_groups
