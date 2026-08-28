import { useEffect, useState } from "react";
import type { HubSection } from "../data/hubSections";
import {
  commandText,
  fetchAuditCache,
  fetchGamingLibrary,
  fetchGamingSliceAvailable,
  fetchGamingSliceCommand,
  type AuditCache,
  type LauncherEntry,
} from "../services/liveData";
import { LiveSectionCard, SectionFallbackNote } from "./LiveSectionCard";
import { ActionStatus, CommandLine, RecipeButton, useSectionAction } from "./SectionActions";

// "Play > Gaming" — audit master profile + live launcher library scan.
// Previously only audit pills; now also shows which launchers are installed
// and library counts, matching page_gaming_library.py's Steam/Heroic scan.
export function GamingSection({ section }: { section: HubSection }) {
  const [audit, setAudit] = useState<AuditCache | null>(null);
  const [launchers, setLaunchers] = useState<LauncherEntry[] | null>(null);
  const [sliceAvailable, setSliceAvailable] = useState<boolean | null>(null);
  const [sliceCommand, setSliceCommand] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);
  const { status, busy, run } = useSectionAction();
  useEffect(() => {
    let c = false;
    Promise.all([
      fetchAuditCache(),
      fetchGamingLibrary(),
      fetchGamingSliceAvailable(),
      // Rendered as the string you paste into Steam's launch options, so
      // %command% is the argv placeholder rather than a real program.
      fetchGamingSliceCommand(["%command%"]).then(commandText),
    ]).then(([a, l, avail, cmd]) => {
      if (!c) {
        setAudit(a);
        setLaunchers(l);
        setSliceAvailable(avail);
        setSliceCommand(cmd);
        setLoaded(true);
      }
    });
    return () => { c = true; };
  }, []);
  const live = audit !== null || launchers !== null;
  return (
    <LiveSectionCard section={section} live={live}>
      {audit ? (
        <div style={{ marginTop: 20 }}>
          <p className="card-copy" style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: 0.6 }}>Master profile</p>
          <p style={{ margin: "4px 0 0", fontSize: 15, fontWeight: 700 }}>{String(audit.master ?? "unknown")}</p>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 12 }}>
            {(["loader", "oom_gaming", "shader_tmpfs", "gaming_cfs", "ananicy", "kwin"] as const).map((k) => (
              <span key={k} className="pill pill-dim">{k}: {String(audit[k] ?? "\u2014")}</span>
            ))}
          </div>
          {launchers && launchers.length > 0 && (
            <div style={{ marginTop: 20 }}>
              <p className="card-copy" style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: 0.6 }}>Launchers</p>
              <div style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: 8 }}>
                {launchers.map((l) => (
                  <div key={l.id} style={{ display: "flex", alignItems: "center", gap: 10, fontSize: 13 }}>
                    <span className={`pill ${l.installed ? "pill-ok" : "pill-dim"}`}>{l.installed ? "installed" : "not installed"}</span>
                    <span style={{ fontWeight: 600 }}>{l.label}</span>
                    <span className="card-copy" style={{ fontSize: 12 }}>{l.library_count != null ? `${l.library_count} games` : l.path}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      ) : (
        <SectionFallbackNote loaded={loaded} />
      )}

      <div style={{ marginTop: 20, borderTop: "1px solid var(--hairline)", paddingTop: 16 }}>
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 12 }}>
          <span className={`pill ${sliceAvailable ? "pill-ok" : "pill-dim"}`}>
            gaming slice: {sliceAvailable == null ? "unknown" : sliceAvailable ? "available" : "unavailable"}
          </span>
        </div>
        {sliceAvailable && (
          <CommandLine label="Steam launch options — runs the game in its own cgroup" command={sliceCommand} />
        )}
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginTop: 12 }}>
          <RecipeButton recipe="gaming-mode" label="Switch to gaming mode" busy={busy} run={run} />
          <RecipeButton recipe="gaming-stack-status" label="Gaming stack status" busy={busy} run={run} />
        </div>
        <ActionStatus status={status} />
      </div>
    </LiveSectionCard>
  );
}
