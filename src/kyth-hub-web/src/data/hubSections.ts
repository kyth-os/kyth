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
import routeManifest from "./hubRoutes.json";

// Titles and descriptions are owned by the route manifest, not duplicated in
// React. Section bodies read through the typed Tauri bridge and show
// an explicit empty state when a real device has no reading yet.
export interface HubSection {
  key: string;
  title: string;
  description: string;
  Icon: ComponentType<SVGProps<SVGSVGElement>>;
}

const SECTION_ICONS: Record<string, ComponentType<SVGProps<SVGSVGElement>>> = {
  Gaming: IconPlay,
  Performance: IconChip,
  Compatibility: IconShield,
  Controllers: IconGamepad,
  "App Store": IconGrid,
  "Work Setup": IconMonitor,
  Update: IconRefresh,
  Guardian: IconShield,
  Hardware: IconChip,
  "Plasma Wayland": IconMonitor,
  Diagnostics: IconDatabase,
  Repair: IconWrench,
  NVIDIA: IconChip,
  Kernel: IconChip,
  Channels: IconRefresh,
  Just: IconGrid,
  Feedback: IconBell,
  "Move Files": IconTransfer,
  "Cloud Storage": IconCloud,
  "Network Shares": IconDatabase,
  VPN: IconLock,
};

function sectionsFor(destinationKey: string): HubSection[] {
  const destination = routeManifest.destinations.find(({ key }) => key === destinationKey);
  if (!destination) {
    // sectionsFor runs at module init for every destination: throwing
    // here would brick the whole shell over one manifest mismatch.
    console.error(`Unknown Hub destination: ${destinationKey}`);
    return [];
  }
  return destination.sections.map((section) => {
    const Icon = SECTION_ICONS[section.key];
    if (!Icon) console.error(`Hub section "${section.key}" has no icon entry; using the fallback icon.`);
    return { ...section, Icon: Icon ?? IconGrid };
  });
}

export const PLAY_SECTIONS = sectionsFor("Play");

export const APPS_SECTIONS = sectionsFor("Apps");

export const UPDATES_SECTIONS = sectionsFor("Updates");

// Guardian..Repair are the primary This PC tabs; NVIDIA..Feedback live under
// its "More" tab. Updates has its own destination in the web Hub;
// This PC keeps the remaining ten sections flattened into one row.
export const THIS_PC_SECTIONS = sectionsFor("This PC");

export const MOVE_IN_SECTIONS = sectionsFor("Move In");
export const VPN_SECTIONS = sectionsFor("VPN");
