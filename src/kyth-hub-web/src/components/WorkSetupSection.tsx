import { useEffect, useState } from "react";
import type { HubSection } from "../data/hubSections";
import {
  commandText,
  fetchFontsReady,
  fetchNetworkSummary,
  fetchPrinterDiscover,
  fetchPrinterSetupCommand,
  type NetworkSummary,
} from "../services/liveData";
import { LiveSectionCard, SectionFallbackNote } from "./LiveSectionCard";
import { ActionButton, ActionStatus, CommandLine, RecipeButton, useSectionAction } from "./SectionActions";

// "Apps > Work Setup" — the three things that actually block a work
// machine on day one: Office-compatible fonts, a printer, and the work
// network identity (VPN/cloud) that Move In also reports.
//
// Printer discovery is an IPP network scan, so it stays behind a button;
// fonts and the network summary are cheap enough to read on mount.
export function WorkSetupSection({ section }: { section: HubSection }) {
  const [summary, setSummary] = useState<NetworkSummary | null>(null);
  const [fonts, setFonts] = useState<{ ready: boolean; detail: string } | null>(null);
  const [setupCmd, setSetupCmd] = useState<string | null>(null);
  const [printers, setPrinters] = useState<string[] | null>(null);
  const [loaded, setLoaded] = useState(false);
  const { status, busy, run } = useSectionAction();

  useEffect(() => {
    let c = false;
    Promise.all([fetchNetworkSummary(), fetchFontsReady(), fetchPrinterSetupCommand().then(commandText)]).then(
      ([s, f, cmd]) => {
        if (!c) {
          setSummary(s);
          setFonts(f);
          setSetupCmd(cmd);
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
      {live ? (
        <div style={{ marginTop: 20 }}>
          {fonts && (
            <div style={{ marginBottom: 14 }}>
              <span className={`pill ${fonts.ready ? "pill-ok" : "pill-warn"}`}>
                Office fonts: {fonts.ready ? "installed" : "missing"}
              </span>
              <p className="card-copy" style={{ fontSize: 12, marginTop: 6 }}>{fonts.detail}</p>
            </div>
          )}
          {summary && (
            <>
              <p className="card-copy" style={{ fontSize: 12 }}>{summary.detail}</p>
              <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginTop: 10 }}>
                {summary.vpnConnected && <span className="pill pill-ok">VPN: {summary.vpnName}</span>}
                {summary.cloudProviders.map((p) => (
                  <span key={p} className="pill pill-dim">{p}</span>
                ))}
              </div>
            </>
          )}
          {printers && (
            <div style={{ marginTop: 14 }}>
              <p className="card-copy" style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: 0.6 }}>
                Printers found
              </p>
              {printers.length > 0 ? (
                <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 8 }}>
                  {printers.map((printer) => (
                    <span key={printer} className="pill pill-ok">{printer}</span>
                  ))}
                </div>
              ) : (
                <p className="card-copy" style={{ fontSize: 12, marginTop: 4 }}>
                  Nothing answered on the network — connect the printer by USB and use Set up a printer.
                </p>
              )}
            </div>
          )}
        </div>
      ) : (
        <SectionFallbackNote loaded={loaded} />
      )}

      <div style={{ marginTop: 20, borderTop: "1px solid var(--hairline)", paddingTop: 16 }}>
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
        <CommandLine label="Printer settings (advanced)" command={setupCmd} />
        <ActionStatus status={status} />
      </div>
    </LiveSectionCard>
  );
}
