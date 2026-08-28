import {
  APPS_SECTIONS,
  MOVE_IN_SECTIONS,
  PLAY_SECTIONS,
  THIS_PC_SECTIONS,
  type HubSection,
} from "./hubSections";

/** The four destinations and the sections each one owns.
 *
 * Single source of truth for "what pages exist and where they live":
 * deepLink.ts builds its `--page` route table from this, and search.ts
 * builds its index from it. Both used to be written out separately, which
 * is how deepLink.ts came to know only 5 of the 26 shipped page keys —
 * anything this list gains is picked up by both callers at once.
 */
export interface Destination {
  key: string;
  route: string;
  sections: HubSection[];
}

export const DESTINATIONS: Destination[] = [
  { key: "Play", route: "/play", sections: PLAY_SECTIONS },
  { key: "Apps", route: "/apps", sections: APPS_SECTIONS },
  { key: "This PC", route: "/this-pc", sections: THIS_PC_SECTIONS },
  { key: "Move In", route: "/move-in", sections: MOVE_IN_SECTIONS },
];
