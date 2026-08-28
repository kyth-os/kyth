import { useEffect, useState } from "react";
import type { HubSection } from "../data/hubSections";
import { fetchBootcSnapshot, relativeTime, type BootcSnapshot } from "../services/liveData";
import { LiveSectionCard, SectionFallbackNote } from "./LiveSectionCard";

function shortDigest(digest: string | undefined): string | null {
  if (!digest) return null;
  return digest.replace(/^sha256:/, "").slice(0, 12);
}

function ago(timestamp: string | undefined): string | null {
  if (!timestamp) return null;
  const ms = Date.parse(timestamp);
  if (Number.isNaN(ms)) return null;
  return relativeTime(ms / 1000);
}

// The real "This PC > Updates" content — reads the same bootc-status-data /
// bootc-branch probe sections the current Qt Hub's Update page reads,
// through the Tauri probe_backend bridge (see services/liveData.ts).
export function UpdatesSection({ section }: { section: HubSection }) {
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
      {snapshot?.booted ? (
        <div style={{ marginTop: 24, display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 16 }}>
          <div>
            <p className="card-copy" style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: 0.6 }}>
              Channel
            </p>
            <p style={{ margin: "4px 0 0", fontSize: 15, fontWeight: 700 }}>{snapshot.channel ?? "Unknown"}</p>
          </div>
          <div>
            <p className="card-copy" style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: 0.6 }}>
              Booted version
            </p>
            <p style={{ margin: "4px 0 0", fontSize: 15, fontWeight: 700 }}>{snapshot.booted.version ?? "Unknown"}</p>
            <p className="card-copy" style={{ fontSize: 11.5, marginTop: 2 }}>
              {ago(snapshot.booted.timestamp) ?? "unknown age"} · {shortDigest(snapshot.booted.imageDigest) ?? "no digest"}
            </p>
          </div>
          <div>
            <p className="card-copy" style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: 0.6 }}>
              Rollback available
            </p>
            {snapshot.rollback ? (
              <>
                <p style={{ margin: "4px 0 0", fontSize: 15, fontWeight: 700 }}>{snapshot.rollback.version ?? "Unknown"}</p>
                <p className="card-copy" style={{ fontSize: 11.5, marginTop: 2 }}>
                  {ago(snapshot.rollback.timestamp) ?? "unknown age"}
                </p>
              </>
            ) : (
              <p style={{ margin: "4px 0 0", fontSize: 15, fontWeight: 700 }}>None</p>
            )}
          </div>
        </div>
      ) : (
        <SectionFallbackNote loaded={loaded} />
      )}
    </LiveSectionCard>
  );
}
