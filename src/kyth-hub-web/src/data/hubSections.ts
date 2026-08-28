import type { ComponentType, SVGProps } from "react";
import {
  IconBell,
  IconChip,
  IconCloud,
  IconDatabase,
  IconGamepad,
  IconGrid,
  IconLock,
  IconMonitor,
  IconPlay,
  IconRefresh,
  IconShield,
  IconTransfer,
  IconWrench,
} from "../components/icons";

// Titles and descriptions here are copied verbatim from page_registry.py's
// SEARCH_INDEX (the current Qt Hub's own search descriptions) — not
// invented for the web prototype. Section keys and grouping match
// DESTINATION_SECTIONS exactly, so this is the same information
// architecture as the Qt Hub, just not wired to live kyth_shared data yet
// (see LiveSectionCard.tsx for the same "real data, marked as such"
// fixture" convention this follows).
export interface HubSection {
  key: string;
  title: string;
  description: string;
  Icon: ComponentType<SVGProps<SVGSVGElement>>;
}

export const PLAY_SECTIONS: HubSection[] = [
  { key: "Gaming", title: "Gaming", description: "Install launchers, scan game libraries, set up capture, saves, and migration helpers.", Icon: IconPlay },
  { key: "Performance", title: "Performance", description: "Tune power, scheduler, and desktop performance behavior.", Icon: IconChip },
  { key: "Compatibility", title: "Compatibility", description: "Check known game support, ProtonDB context, and blocked anti-cheat titles.", Icon: IconShield },
  { key: "Controllers", title: "Controllers", description: "Pair, test, and troubleshoot game controllers.", Icon: IconGamepad },
];

export const APPS_SECTIONS: HubSection[] = [
  { key: "App Store", title: "App Store", description: "Install trusted Flatpaks, find familiar app alternatives, and manage AppImages.", Icon: IconGrid },
  { key: "Work Setup", title: "Work Setup", description: "Set up office, mail, focus sessions, and workday conveniences.", Icon: IconMonitor },
];

// Guardian..Repair are the Qt Hub's primary This PC tabs; NVIDIA..Feedback
// live under its "More" tab (see page_registry.py's comment on
// DESTINATION_SECTIONS). The web prototype flattens both into one row —
// same 11 sections, no nested "More" menu yet.
export const THIS_PC_SECTIONS: HubSection[] = [
  { key: "Guardian", title: "Guardian", description: "Self-healing: automatic health checks, safe fixes, history, and optional local AI diagnosis.", Icon: IconShield },
  { key: "Update", title: "Updates", description: "Check OS updates, staged images, rollback status, and auto-update settings.", Icon: IconRefresh },
  { key: "Hardware", title: "Hardware", description: "Inspect graphics, displays, audio, Bluetooth, storage, and device health.", Icon: IconChip },
  { key: "Plasma Wayland", title: "Desktop & displays", description: "Check portals, PipeWire capture, display settings, shortcuts, and Plasma session repair.", Icon: IconMonitor },
  { key: "Diagnostics", title: "Health Report", description: "Run system checks and gather useful troubleshooting information.", Icon: IconDatabase },
  { key: "Repair", title: "Repair", description: "Rollback, restore, collect logs, and open recovery tools when something feels off.", Icon: IconWrench },
  { key: "NVIDIA", title: "NVIDIA Drivers", description: "Check NVIDIA driver state and open driver actions.", Icon: IconChip },
  { key: "Kernel", title: "Kernel", description: "Choose installed kernels and understand advanced boot options.", Icon: IconChip },
  { key: "Channels", title: "Update channel", description: "Choose stable or testing update channels.", Icon: IconRefresh },
  { key: "Just", title: "Recipes", description: "Run Just recipes from Kyth Hub without opening a terminal.", Icon: IconGrid },
  { key: "Feedback", title: "Feedback", description: "Send feedback or report a problem with optional system details.", Icon: IconBell },
];

export const MOVE_IN_SECTIONS: HubSection[] = [
  { key: "Move Files", title: "Move Files", description: "Copy files, saves, libraries, bookmarks, fonts, and familiar workflows.", Icon: IconTransfer },
  { key: "Cloud Storage", title: "Cloud Storage", description: "Set up cloud sync and copy workflows for common providers.", Icon: IconCloud },
  { key: "Network Shares", title: "Network Shares", description: "Map SMB/CIFS shares and configure mount behavior.", Icon: IconDatabase },
  { key: "VPN", title: "VPN", description: "Connect to VPN profiles, including GlobalProtect-style work VPNs.", Icon: IconLock },
];
