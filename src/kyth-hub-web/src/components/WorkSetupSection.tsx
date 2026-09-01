import { useEffect, useState } from "react";
import type { HubSection } from "../data/hubSections";
import {
  fetchFontsReady,
  fetchNetworkSummary,
  fetchPrinterDiscover,
  type NetworkSummary,
} from "../services/liveData";
import { LiveSectionCard, SectionFallbackNote } from "./LiveSectionCard";
import { ActionButton, ActionStatus, RecipeButton, useSectionAction } from "./SectionActions";

function WorkCard({ icon, label, value, detail, good }: { icon: string; label: string; value: string; detail: string; good: boolean | null }) {
  const tone = good === null ? "work-card-muted" : good ? "work-card-ok" : "work-card-warn";
  return <article className={`work-card ${tone}`}><div className="work-card-top"><span className="work-card-icon" aria-hidden="true">{icon}</span><span className="work-card-label">{label}</span><span className="work-status-dot" /></div><strong className="work-card-value">{value}</strong><span className="work-card-detail">{detail}</span></article>;
}

// "Apps > Work Setup" — the three things that actually block a work
// machine on day one: Office-compatible fonts, a printer, and the work
// network identity (VPN/cloud) that Move In also reports.
//
// Printer discovery is an IPP network scan, so it stays behind a button;
// fonts and the network summary are cheap enough to read on mount.
export function WorkSetupSection({ section }: { section: HubSection }) {
  const [summary, setSummary] = useState<NetworkSummary | null>(null);
  const [fonts, setFonts] = useState<{ ready: boolean; detail: string } | null>(null);
  const [printers, setPrinters] = useState<string[] | null>(null);
  const [loaded, setLoaded] = useState(false);
  const { status, busy, run } = useSectionAction();

  useEffect(() => {
    let c = false;
    Promise.all([fetchNetworkSummary(), fetchFontsReady()]).then(
      ([s, f]) => {
        if (!c) {
          setSummary(s);
          setFonts(f);
          setLoaded(true);
        }
      },
    );
    return () => {
      c = true;
    };
  }, []);

  const live = summary !== null || fonts !== null;
  return (
    <LiveSectionCard section={section} live={live}>
      <div className="work-card-grid">
        <WorkCard icon="Aa" label="Office fonts" value={fonts ? fonts.ready ? "Installed" : "Needs setup" : "Checking…"} detail={fonts?.detail || "Microsoft-compatible fonts support office documents."} good={fonts ? fonts.ready : null} />
        <WorkCard icon="⌁" label="Connected services" value={summary ? `${summary.cloudProviders.length} cloud provider${summary.cloudProviders.length === 1 ? "" : "s"}` : "Checking…"} detail={summary?.detail || "VPN and cloud connectivity are being checked."} good={summary ? summary.cloudProviders.length > 0 || summary.vpnConnected : null} />
        <WorkCard icon="▣" label="Printers" value={printers === null ? "Not scanned" : printers.length === 0 ? "None found" : `${printers.length} found`} detail={printers === null ? "Scan the network or open printer setup." : printers.length > 0 ? printers.join(" · ") : "USB and manually added printers can still be configured."} good={printers === null ? null : printers.length > 0} />
      </div>
      {!live && <SectionFallbackNote loaded={loaded} />}

      <div style={{ marginTop: 20, borderTop: "1px solid var(--hairline)", paddingTop: 16 }}>
        <p className="work-setup-copy">Set up the tools you use for documents, meetings, printing, and focused work.</p>
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
          <RecipeButton recipe="install-ms-fonts" label="Install Office fonts" busy={busy} run={run} />
          <RecipeButton recipe="setup-printer" label="Set up a printer" busy={busy} run={run} />
          <ActionButton
            label={busy === "discover" ? "Scanning…" : "Find network printers"}
            disabled={busy !== null}
            onClick={() =>
              run("discover", "Scanning the network for IPP printers…", async () => {
                const found = await fetchPrinterDiscover();
                if (!found) return "Not available outside the Hub shell.";
                setPrinters(found);
                return found.length > 0 ? `${found.length} printer(s) found.` : "No network printers answered.";
              })
            }
          />
        </div>
        <ActionStatus status={status} />
      </div>
    </LiveSectionCard>
  );
}
