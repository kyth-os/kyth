import { useEffect, useState } from "react";
import type { HubSection } from "../data/hubSections";
import { fetchNetworkSummary, type NetworkSummary } from "../services/liveData";
import { LiveSectionCard, SectionFallbackNote } from "./LiveSectionCard";

// Real "Move In > Network Shares" content — one facet of the
// "network-summary" probe section (see VpnSection's comment).
export function NetworkSharesSection({ section }: { section: HubSection }) {
  const [summary, setSummary] = useState<NetworkSummary | null>(null);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    let cancelled = false;
    fetchNetworkSummary().then((s) => {
      if (!cancelled) {
        setSummary(s);
        setLoaded(true);
      }
    });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <LiveSectionCard section={section} live={summary !== null}>
      {summary ? (
        <div style={{ marginTop: 20 }}>
          <p className="card-copy" style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: 0.6 }}>
            SMB/CIFS shares mounted
          </p>
          <p style={{ margin: "4px 0 0", fontSize: 22, fontWeight: 800 }}>{summary.smbMounts}</p>
        </div>
      ) : (
        <SectionFallbackNote loaded={loaded} />
      )}
    </LiveSectionCard>
  );
}
