import type { ComponentType, SVGProps } from "react";
import { DESTINATIONS } from "./data/destinations";
import { IconGrid, IconHome, IconTerminal } from "./components/icons";

/** Hub search over the shared route manifest.
 *
 * The Topbar shipped a search input with no `value` and no `onChange`: it
 * accepted typing and did nothing, while the Qt Hub's equivalent box has
 * ranked search over the same pages. The scoring below matches the Python
 * exactly (exact 120, prefix 90, substring 60, all-words 45 + word count,
 * top 5, ties broken by key ascending) so both Hubs answer a given query
 * the same way.
 *
 * Not ported: the Python's `problem_routes` boost, which maps
 * problem-phrase text ("no sound", ...) onto a page and has no source on
 * this side yet. Its absence lowers some scores but never invents a hit.
 */
export interface SearchEntry {
  key: string;
  title: string;
  description: string;
  destination: string;
  Icon: ComponentType<SVGProps<SVGSVGElement>>;
  /** Explicit route for destination-level entries. Section entries omit
   * it and keep routing through routeForPage(entry.key); destination
   * entries carry theirs because the deep-link table is keyed by
   * section/destination keys and the shell-only pages below (Home,
   * Dev Tools) have no manifest destination to resolve from at all. */
  route?: string;
}

function buildIndex(): SearchEntry[] {
  const entries: SearchEntry[] = [];
  // Destination-level entries: the index used to hold sections only, so
  // the pages users name first — Home, Dev Tools, and the destinations
  // themselves ("This PC", "Move In") — matched nothing, or only stray
  // description substrings on unrelated sections. One entry per
  // destination, titled by its displayed name, alongside its sections.
  entries.push({
    key: "dest:Home",
    title: "Home",
    description: "Health and the next step",
    destination: "Destination",
    route: "/",
    Icon: IconHome,
  });
  for (const { key: destination, route, sections } of DESTINATIONS) {
    for (const section of sections) {
      entries.push({
        key: section.key,
        title: section.title,
        description: section.description,
        destination,
        Icon: section.Icon,
      });
    }
    entries.push({
      key: `dest:${destination}`,
      title: destination,
      description: sections.map((section) => section.title).join(" · "),
      destination: "Destination",
      route,
      Icon: sections[0]?.Icon ?? IconGrid,
    });
  }
  entries.push({
    key: "dest:Dev Tools",
    title: "Dev Tools",
    description: "AI dev box, editors, agents",
    destination: "Destination",
    route: "/dev-tools",
    Icon: IconTerminal,
  });
  return entries;
}

export const SEARCH_INDEX: SearchEntry[] = buildIndex();

export interface SearchResult {
  entry: SearchEntry;
  score: number;
}

export function rankSearchResults(text: string, entries: SearchEntry[] = SEARCH_INDEX): SearchResult[] {
  const query = text.trim().toLowerCase();
  if (!query) return [];

  const ranked: SearchResult[] = [];
  for (const entry of entries) {
    const terms = [entry.key, entry.title, entry.description];
    let score = 0;
    for (const term of terms) {
      const lower = term.toLowerCase();
      if (query === lower) score = Math.max(score, 120);
      else if (lower.startsWith(query)) score = Math.max(score, 90);
      else if (lower.includes(query)) score = Math.max(score, 60);
    }
    const haystack = terms.join(" ").toLowerCase();
    const words = query.split(/\s+/).filter(Boolean);
    if (words.length && words.every((word) => haystack.includes(word))) {
      score = Math.max(score, 45 + words.length);
    }
    if (score) ranked.push({ entry, score });
  }

  // Score descending, then key ascending — the Python's stable tie-break,
  // deliberately not title order (that drifts as terms change).
  ranked.sort((a, b) => b.score - a.score || a.entry.key.localeCompare(b.entry.key));
  return ranked.slice(0, 5);
}
