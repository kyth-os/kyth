import { useEffect, useState } from "react";
import type { HubSection } from "../data/hubSections";
import { fetchNetworkSummary, type NetworkSummary } from "../services/liveData";
import { LiveSectionCard, SectionFallbackNote } from "./LiveSectionCard";

// "Apps > Work Setup" — office/mail focus, but the live signal we have
// today is the same work-network identity (VPN/cloud detail) that Move In
// shows — reused here with a Work framing.
export function WorkSetupSection({ section }: { section: HubSection }) {
  const [summary, setSummary] = useState<NetworkSummary | null>(null);
  const [loaded, setLoaded] = useState(false);
  useEffect(() => {
    let c = false;
    fetchNetworkSummary().then((s) => {
      if (!c) {
        setSummary(s);
        setLoaded(true);
      }
    });
    return () => {
      c = true;
    };
  }, []);
  return (
    <LiveSectionCard section={section} live={summary !== null}>
      {summary ? (
        <div style={{ marginTop: 20 }}>
          <p className="card-copy" style={{ fontSize: 12 }}>{summary.detail}</p>
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginTop: 10 }}>
            {summary.vpnConnected && <span className="pill pill-ok">VPN: {summary.vpnName}</span>}
            {summary.cloudProviders.map((p) => (
              <span key={p} className="pill pill-dim">{p}</span>
            ))}
          </div>
        </div>
      ) : (
        <SectionFallbackNote loaded={loaded} />
      )}
    </LiveSectionCard>
  );
}
