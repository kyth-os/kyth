import { useEffect, useState } from "react";
import type { HubSection } from "../data/hubSections";
import { fetchBootcSnapshot, relativeTime, type BootcSnapshot } from "../services/liveData";
import { LiveSectionCard, SectionFallbackNote } from "./LiveSectionCard";

function ago(timestamp: string | undefined): string | null {
  if (!timestamp) return null;
  const ms = Date.parse(timestamp);
  if (Number.isNaN(ms)) return null;
  return relativeTime(ms / 1000);
}

// Real "This PC > Repair" content — same bootc-status-data read as
// UpdatesSection, framed around what Repair actually cares about: is
// there a rollback deployment available right now.
export function RepairSection({ section }: { section: HubSection }) {
  const [snapshot, setSnapshot] = useState<BootcSnapshot | null>(null);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    let cancelled = false;
    fetchBootcSnapshot().then((s) => {
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
        <div style={{ marginTop: 20 }}>
          <p className="card-copy" style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: 0.6 }}>
            Rollback deployment
          </p>
          {snapshot.rollback ? (
            <>
              <p style={{ margin: "4px 0 0", fontSize: 15, fontWeight: 700 }}>{snapshot.rollback.version ?? "Unknown"}</p>
              <p className="card-copy" style={{ fontSize: 12, marginTop: 4, maxWidth: 420 }}>
                Available now — {ago(snapshot.rollback.timestamp) ?? "unknown age"}. `bootc rollback` returns to this
                deployment without needing a new download.
              </p>
            </>
          ) : (
            <p className="card-copy" style={{ fontSize: 13, marginTop: 4 }}>
              No rollback deployment on this system yet.
            </p>
          )}
        </div>
      ) : (
        <SectionFallbackNote loaded={loaded} />
      )}
    </LiveSectionCard>
  );
}
