import { useEffect, useState } from "react";
import type { HubSection } from "../data/hubSections";
import { fetchNetworkSummary, type NetworkSummary } from "../services/liveData";
import { LiveSectionCard, SectionFallbackNote } from "./LiveSectionCard";

// Real "Move In > Cloud Storage" content — one facet of the
// "network-summary" probe section (see VpnSection's comment).
export function CloudStorageSection({ section }: { section: HubSection }) {
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
        summary.cloudProviders.length > 0 ? (
          <div style={{ display: "flex", gap: 8, marginTop: 20, flexWrap: "wrap" }}>
            {summary.cloudProviders.map((p) => (
              <span key={p} className="pill pill-ok">
                {p}
              </span>
            ))}
          </div>
        ) : (
          <p className="card-copy" style={{ marginTop: 20, fontSize: 13 }}>
            No cloud storage providers set up yet.
          </p>
        )
      ) : (
        <SectionFallbackNote loaded={loaded} />
      )}
    </LiveSectionCard>
  );
}
