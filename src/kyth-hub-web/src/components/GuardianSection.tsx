import { useEffect, useState } from "react";
import type { HubSection } from "../data/hubSections";
import { fetchGuardianSnapshot, relativeTime, type GuardianSnapshot } from "../services/liveData";
import { LiveSectionCard, SectionFallbackNote } from "./LiveSectionCard";

const riskTone: Record<string, string> = {
  safe: "pill-ok",
  confirm: "pill-warn",
};

const statusDot: Record<string, string> = {
  ok: "var(--status-ok)",
  warn: "var(--status-warn)",
  error: "var(--status-error)",
};

// Real "This PC > Guardian" content — the same pending_recommendations()
// list Hub's own mission bar/sidebar badge reads, plus recent history.
// Dashboard's Guardian stat tile shows a compact count of this same data;
// this is the full picture. See services/liveData.ts / main.rs's
// guardian_snapshot command.
export function GuardianSection({ section }: { section: HubSection }) {
  const [snapshot, setSnapshot] = useState<GuardianSnapshot | null>(null);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    let cancelled = false;
    fetchGuardianSnapshot().then((s) => {
      if (!cancelled) {
        setSnapshot(s);
        setLoaded(true);
      }
    });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <LiveSectionCard section={section} live={snapshot !== null}>
      {snapshot ? (
        <div style={{ marginTop: 20, display: "flex", flexDirection: "column", gap: 20 }}>
          <div>
            <p className="card-copy" style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: 0.6 }}>
              Needs your attention
            </p>
            {snapshot.pending.length === 0 ? (
              <p style={{ margin: "8px 0 0", fontSize: 13 }}>Nothing pending — Guardian has no open recommendations.</p>
            ) : (
              <div style={{ marginTop: 8, display: "flex", flexDirection: "column", gap: 2 }}>
                {snapshot.pending.map((item, i) => (
                  <div
                    key={`${item.title}-${i}`}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: 12,
                      padding: "10px 4px",
                      borderBottom: "1px solid var(--hairline)",
                    }}
                  >
                    <p style={{ margin: 0, fontSize: 13, fontWeight: 600, flex: 1 }}>{item.title}</p>
                    <span className={`pill ${riskTone[item.risk] ?? "pill-dim"}`} style={{ flexShrink: 0 }}>
                      {item.risk}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>

          {snapshot.history.length > 0 && (
            <div>
              <p className="card-copy" style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: 0.6 }}>
                Recent activity
              </p>
              <div style={{ marginTop: 8, display: "flex", flexDirection: "column", gap: 2 }}>
                {snapshot.history.slice(0, 5).map((event, i) => (
                  <div
                    key={`${event.title}-${i}`}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: 12,
                      padding: "8px 4px",
                      borderBottom: "1px solid var(--hairline)",
                    }}
                  >
                    <span
                      style={{
                        width: 7,
                        height: 7,
                        borderRadius: "50%",
                        background: statusDot[event.status],
                        flexShrink: 0,
                      }}
                    />
                    <p style={{ margin: 0, fontSize: 12.5, flex: 1 }}>{event.title}</p>
                    <span className="card-copy" style={{ fontSize: 11, flexShrink: 0 }}>
                      {relativeTime(event.timestamp)}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      ) : (
        <SectionFallbackNote loaded={loaded} />
      )}
    </LiveSectionCard>
  );
}
