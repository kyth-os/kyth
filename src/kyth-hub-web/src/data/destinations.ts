import {
  APPS_SECTIONS,
  MOVE_IN_SECTIONS,
  PLAY_SECTIONS,
  THIS_PC_SECTIONS,
  UPDATES_SECTIONS,
  type HubSection,
} from "./hubSections";
import routeManifest from "./hubRoutes.json";

/** The destinations and the sections each one owns.
 *
 * Single source of truth for "what pages exist and where they live":
 * hubRoutes.json is the source for this table, the deepLink.ts `--page` route
 * table, the search.ts index, and packaging-time KRunner entries. Adding a
 * section to the manifest updates every consumer together.
 */
export interface Destination {
  key: string;
  route: string;
  sections: HubSection[];
}

const sectionsByDestination: Record<string, HubSection[]> = {
  Play: PLAY_SECTIONS,
  Apps: APPS_SECTIONS,
  "This PC": THIS_PC_SECTIONS,
  "Move In": MOVE_IN_SECTIONS,
  Updates: UPDATES_SECTIONS,
};

export const DESTINATIONS: Destination[] = routeManifest.destinations.map(({ key, route }) => ({
  key,
  route,
  sections: sectionsByDestination[key],
}));
