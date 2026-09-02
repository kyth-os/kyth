import { useEffect, useState } from "react";
import type { HubSection } from "../data/hubSections";
import { fetchJustList, type JustRecipe } from "../services/liveData";
import { LiveSectionCard, SectionFallbackNote } from "./LiveSectionCard";
import { ActionStatus } from "./SectionActions";

// "This PC > Recipes (Just)" — read-only inventory via Tauri `just_list`.
// Mutating actions are exposed only through the explicit HubAction enum in
// Rust; arbitrary recipe names are never executable from this page.
//
// Only recipes that take no arguments get a button: a launch passes no
// arguments, so a parameterized recipe would silently run its defaults.
// `switch-kernel flavor="fedora"` was one click from staging a switch off
// the CachyOS default here. Those rows render as text instead.
export function JustSection({ section }: { section: HubSection }) {
  const [recipes, setRecipes] = useState<JustRecipe[] | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [query, setQuery] = useState("");
  const [status] = useState<string | null>(null);
  useEffect(() => {
    let c = false;
    fetchJustList().then((r) => {
      if (!c) {
        setRecipes(r);
        setLoaded(true);
      }
    });
    return () => {
      c = true;
    };
  }, []);
  const live = recipes !== null;
  const needle = query.trim().toLowerCase();
  const matching = (recipes ?? []).filter(
    (r) => needle === "" || r.name.toLowerCase().includes(needle) || r.comment.toLowerCase().includes(needle),
  );
  // Same 30-row cap page_just.py used — the full list is ~200 recipes.
  const shown = matching.slice(0, 30);
  return (
    <LiveSectionCard section={section} live={live}>
      {live ? (
        recipes.length > 0 ? (
          <div style={{ marginTop: 20 }}>
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Filter recipes…"
              style={{
                width: "100%",
                maxWidth: 340,
                marginBottom: 12,
                padding: "8px 12px",
                borderRadius: 999,
                border: "1px solid var(--hairline)",
                background: "var(--card)",
                fontSize: 13,
              }}
            />
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {shown.map((r) => (
                <div key={r.name} style={{ display: "flex", alignItems: "center", gap: 12, padding: "8px 0", borderBottom: "1px solid var(--hairline)" }}>
                  <div style={{ minWidth: 190 }}>
                    <code style={{ fontSize: 12 }}>
                      {r.name} {r.params && <span className="card-copy">{r.params}</span>}
                    </code>
                  </div>
                  <span className="card-copy" style={{ fontSize: 12, flex: 1 }}>{r.comment}</span>
                </div>
              ))}
            </div>
            {matching.length > shown.length && (
              <p className="card-copy" style={{ fontSize: 11, marginTop: 8 }}>
                … and {matching.length - shown.length} more — narrow the filter to find a recipe.
              </p>
            )}
            <p className="card-copy" style={{ fontSize: 11, marginTop: 8 }}>
              Recipes are shown for reference; mutating actions are available from their typed Hub controls.
            </p>
            <ActionStatus status={status} />
          </div>
        ) : (
          <p className="card-copy" style={{ marginTop: 20, fontSize: 13 }}>No just recipes found.</p>
        )
      ) : (
        <SectionFallbackNote loaded={loaded} />
      )}
    </LiveSectionCard>
  );
}
