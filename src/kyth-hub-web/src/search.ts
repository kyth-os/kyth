import type { ComponentType, SVGProps } from "react";
import { DESTINATIONS } from "./data/destinations";

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
}

function buildIndex(): SearchEntry[] {
  const entries: SearchEntry[] = [];
  for (const { key: destination, sections } of DESTINATIONS) {
    for (const section of sections) {
      entries.push({
        key: section.key,
        title: section.title,
        description: section.description,
        destination,
        Icon: section.Icon,
      });
    }
  }
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
