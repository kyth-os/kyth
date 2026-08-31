import { useEffect, useState } from "react";
import type { HubSection } from "../data/hubSections";
import { fetchNetworkSummary, fetchNetworkSummaryLive, openVpnApp, type NetworkSummary } from "../services/liveData";
import { LiveSectionCard, SectionFallbackNote } from "./LiveSectionCard";
import { ActionButton, ActionStatus, RecipeButton, useSectionAction } from "./SectionActions";

// Real "Move In > VPN" content — one facet of the "network-summary" probe
// section (NetworkSharesSection and CloudStorageSection read the other
// two facets of the same read). Refresh escalates to the live nmcli read.
export function VpnSection({ section }: { section: HubSection }) {
  const [summary, setSummary] = useState<NetworkSummary | null>(null);
  const [loaded, setLoaded] = useState(false);
  const { status, busy, run } = useSectionAction();
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
          <p className="card-copy" style={{ fontSize: 12, marginTop: 10 }}>{summary.detail}</p>
        </div>
      ) : (
        <SectionFallbackNote loaded={loaded} />
      )}

      <div style={{ marginTop: 20, borderTop: "1px solid var(--hairline)", paddingTop: 16 }}>
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
          <ActionButton
            label={busy === "refresh" ? "Checking…" : "Check connection"}
            disabled={busy !== null}
            onClick={() =>
              run("refresh", "Asking NetworkManager…", async () => {
                const fresh = await fetchNetworkSummaryLive();
                if (!fresh) return "Not available outside the Hub shell.";
                setSummary(fresh);
                return fresh.vpnConnected ? `Connected to ${fresh.vpnName}.` : "No VPN connection is up.";
              })
            }
          />
          <RecipeButton recipe="setup-tailscale" label="Set up Tailscale" busy={busy} run={run} />
          <ActionButton
            label={busy === "open-vpn" ? "Opening…" : "Open full VPN connection"}
            disabled={busy !== null}
            onClick={() => run("open-vpn", "Opening the VPN connection app…", openVpnApp)}
          />
        </div>
        <p className="card-copy" style={{ fontSize: 12, marginTop: 12 }}>
          Use the full connection app for saved profiles, GlobalProtect-style gateways, and SAML sign-in.
        </p>
        <ActionStatus status={status} />
      </div>
    </LiveSectionCard>
  );
}
