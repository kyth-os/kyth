import { useEffect, useState } from "react";
import type { HubSection } from "../data/hubSections";
import { fetchUpdateChannel } from "../services/liveData";
import { LiveSectionCard, SectionFallbackNote } from "./LiveSectionCard";

// "This PC > Update channel" — same bootc-branch read as UpdatesSection,
// framed as the channel switcher state rather than the deployment view.
export function ChannelsSection({ section }: { section: HubSection }) {
  const [channel, setChannel] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);
  useEffect(() => {
    let cancelled = false;
    fetchUpdateChannel().then((c) => {
      if (!cancelled) {
        setChannel(c);
        setLoaded(true);
      }
    });
    return () => {
      cancelled = true;
    };
  }, []);
  return (
    <LiveSectionCard section={section} live={channel !== null}>
      {channel ? (
        <div style={{ marginTop: 20 }}>
          <p className="card-copy" style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: 0.6 }}>
            Active channel
          </p>
          <p style={{ margin: "4px 0 0", fontSize: 15, fontWeight: 700 }}>{channel}</p>
        </div>
      ) : (
        <SectionFallbackNote loaded={loaded} />
      )}
    </LiveSectionCard>
  );
}
