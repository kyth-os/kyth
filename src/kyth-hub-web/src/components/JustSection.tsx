import { useEffect, useState } from "react";
import type { HubSection } from "../data/hubSections";
import { fetchJustList, type JustRecipe } from "../services/liveData";
import { LiveSectionCard, SectionFallbackNote } from "./LiveSectionCard";
import { ActionStatus, RecipeButton, useSectionAction } from "./SectionActions";

// "This PC > Recipes (Just)" — now live via Tauri `just_list`/`just_run`
// (port of page_just.py). Falls back to preview note when not in Tauri
// or `just` is not installed.
//
// Only recipes that take no arguments get a button: `just_run` spawns the
// bare name, so a parameterized recipe would silently run its defaults.
// `switch-kernel flavor="fedora"` was one click from staging a switch off
// the CachyOS default here. Those rows render as text instead.
export function JustSection({ section }: { section: HubSection }) {
  const [recipes, setRecipes] = useState<JustRecipe[] | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [query, setQuery] = useState("");
  const { status, busy, run } = useSectionAction();
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
                    {r.params ? (
                      <code style={{ fontSize: 12 }}>
                        {r.name} <span className="card-copy">{r.params}</span>
                      </code>
                    ) : (
                      <RecipeButton recipe={r.name} label={r.name} busy={busy} run={run} />
                    )}
                  </div>
                  <span className="card-copy" style={{ fontSize: 12, flex: 1 }}>{r.comment}</span>
                </div>
              ))}
            </div>
            {matching.length > shown.length && (
              <p className="card-copy" style={{ fontSize: 11, marginTop: 8 }}>
                … and {matching.length - shown.length} more — narrow the filter, or run `just --list` in a terminal.
              </p>
            )}
            <p className="card-copy" style={{ fontSize: 11, marginTop: 8 }}>
              Recipes that take arguments are shown as text — run those in a terminal, where you choose the argument.
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
