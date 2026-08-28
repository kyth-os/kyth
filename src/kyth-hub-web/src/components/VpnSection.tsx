import { useEffect, useState } from "react";
import type { HubSection } from "../data/hubSections";
import { fetchNetworkSummary, type NetworkSummary } from "../services/liveData";
import { LiveSectionCard, SectionFallbackNote } from "./LiveSectionCard";

// Real "Move In > VPN" content — one facet of the "network-summary" probe
// section (see services/liveData.ts; NetworkSharesSection and
// CloudStorageSection read the other two facets of the same read).
export function VpnSection({ section }: { section: HubSection }) {
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
          <span className={`pill ${summary.vpnConnected ? "pill-ok" : "pill-dim"}`}>
            {summary.vpnConnected ? `Connected — ${summary.vpnName}` : "Not connected"}
          </span>
        </div>
      ) : (
        <SectionFallbackNote loaded={loaded} />
      )}
    </LiveSectionCard>
  );
}
