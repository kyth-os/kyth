import { useEffect, useState } from "react";
import type { HubSection } from "../data/hubSections";
import { fetchGuardianSnapshot, type GuardianSnapshot } from "../services/liveData";
import { LiveSectionCard, SectionFallbackNote } from "./LiveSectionCard";

// "This PC > Feedback" — reuse Guardian's pending/history snapshot as the
// "system details to attach" that Feedback already bundles in Qt Hub.
export function FeedbackSection({ section }: { section: HubSection }) {
  const [snap, setSnap] = useState<GuardianSnapshot | null>(null);
  const [loaded, setLoaded] = useState(false);
  useEffect(() => {
    let c = false;
    fetchGuardianSnapshot().then((s) => {
      if (!c) {
        setSnap(s);
        setLoaded(true);
      }
    });
    return () => {
      c = true;
    };
  }, []);
  return (
    <LiveSectionCard section={section} live={snap !== null}>
      {snap ? (
        <div style={{ marginTop: 20 }}>
          <p className="card-copy" style={{ fontSize: 12 }}>{snap.pendingCount} pending Guardian recommendations — included when you send feedback.</p>
          {snap.history.length > 0 && (
            <p className="card-copy" style={{ fontSize: 11, marginTop: 6 }}>{snap.history.length} recent history items available to attach.</p>
          )}
        </div>
      ) : (
        <SectionFallbackNote loaded={loaded} />
      )}
    </LiveSectionCard>
  );
}
