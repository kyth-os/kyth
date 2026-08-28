import { useEffect, useState } from "react";
import type { HubSection } from "../data/hubSections";
import { fetchJustList, runJustRecipe, type JustRecipe } from "../services/liveData";
import { LiveSectionCard, SectionFallbackNote } from "./LiveSectionCard";

// "This PC > Recipes (Just)" — now live via Tauri `just_list`/`just_run`
// (port of page_just.py). Falls back to preview note when not in Tauri
// or `just` is not installed.
export function JustSection({ section }: { section: HubSection }) {
  const [recipes, setRecipes] = useState<JustRecipe[] | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
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
  return (
    <LiveSectionCard section={section} live={live}>
      {live ? (
        recipes.length > 0 ? (
          <div style={{ marginTop: 20 }}>
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {recipes.slice(0, 30).map((r) => (
                <div key={r.name} style={{ display: "flex", alignItems: "center", gap: 12, padding: "8px 0", borderBottom: "1px solid var(--hairline)" }}>
                  <button
                    className=" Pill"
                    onClick={async () => {
                      setStatus(`Launching just ${r.name}…`);
                      const ok = await runJustRecipe(r.name);
                      setStatus(ok ? `Launched just ${r.name}` : `Failed to launch just ${r.name}`);
                    }}
                    style={{ minWidth: 160, padding: "6px 12px", borderRadius: 999, border: "1px solid var(--hairline)", background: "var(--card)", fontWeight: 600, cursor: "pointer" }}
                  >
                    {r.name}
                  </button>
                  <span className="card-copy" style={{ fontSize: 12, flex: 1 }}>{r.comment}</span>
                </div>
              ))}
            </div>
            {recipes.length > 30 && <p className="card-copy" style={{ fontSize: 11, marginTop: 8 }}>… and {recipes.length - 30} more (run just --list in terminal)</p>}
            {status && <p className="card-copy" style={{ fontSize: 12, marginTop: 10 }}>{status}</p>}
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
