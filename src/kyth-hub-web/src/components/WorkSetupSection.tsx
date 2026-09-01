import { useEffect, useState } from "react";
import type { HubSection } from "../data/hubSections";
import {
  fetchFontsReady,
  fetchNetworkSummary,
  fetchPrinterDiscover,
  fetchInstalledFlatpaks,
  fetchInstallStatus,
  installFlatpak,
  openM365App,
  createM365Shortcuts,
  fetchPstFiles,
  convertPst,
  startFocusSession,
  stopFocusSession,
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
  const [installed, setInstalled] = useState<string[]>([]);
  const [pstFiles, setPstFiles] = useState<string[] | null>(null);
  const [focusMinutes, setFocusMinutes] = useState(25);
  const [focusId, setFocusId] = useState<string | null>(null);
  const [focusRemaining, setFocusRemaining] = useState(0);
  const { status, busy, run } = useSectionAction();

  useEffect(() => {
    let c = false;
    Promise.all([fetchNetworkSummary(), fetchFontsReady(), fetchInstalledFlatpaks()]).then(
      ([s, f, apps]) => {
        if (!c) {
          setSummary(s);
          setFonts(f);
          setLoaded(true);
          setInstalled((apps ?? []).map((app) => app.id));
        }
      },
    );
    return () => {
      c = true;
    };
  }, []);

  useEffect(() => {
    if (!focusId) return;
    const timer = window.setInterval(() => setFocusRemaining((value) => {
      if (value <= 1) {
        void stopFocusSession(focusId).catch(() => undefined);
        setFocusId(null);
        return 0;
      }
      return value - 1;
    }), 1000);
    return () => window.clearInterval(timer);
  }, [focusId]);

  async function installWorkApp(id: string, name: string): Promise<string> {
    const job = await installFlatpak(id);
    for (let i = 0; i < 120; i += 1) {
      await new Promise((resolve) => window.setTimeout(resolve, 500));
      const state = await fetchInstallStatus(job);
      if (!state || state.state === "running") continue;
      if (state.state === "complete") { setInstalled((current) => [...new Set([...current, id])]); return `${name} installed.`; }
      throw new Error(state.detail);
    }
    throw new Error(`${name} is still installing; refresh Apps in a moment.`);
  }

  const formatFocus = (seconds: number) => `${Math.floor(seconds / 60).toString().padStart(2, "0")}:${(seconds % 60).toString().padStart(2, "0")}`;

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
          {[ ["org.libreoffice.LibreOffice", "LibreOffice"], ["eu.betterbird.Betterbird", "Betterbird"] ].map(([id, name]) => installed.includes(id) ? <span key={id} className="pill pill-ok">{name} installed</span> : <ActionButton key={id} label={busy === `install-${id}` ? `Installing ${name}…` : `Install ${name}`} disabled={busy !== null} onClick={() => run(`install-${id}`, `Installing ${name}…`, () => installWorkApp(id, name))} />)}
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
        <div style={{ marginTop: 20, paddingTop: 16, borderTop: "1px solid var(--hairline)" }}>
          <p className="work-setup-copy" style={{ fontWeight: 700 }}>Microsoft 365 web apps</p>
          <p className="work-setup-copy">Open Outlook, Word, Excel, PowerPoint, OneNote, or Teams in a dedicated browser tab, or add all six to the application menu.</p>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 10 }}>
            {["Outlook", "Word", "Excel", "PowerPoint", "OneNote", "Teams"].map((name) => <ActionButton key={name} label={name} disabled={busy !== null} onClick={() => run(`m365-${name}`, `Opening ${name}…`, () => openM365App(name))} />)}
            <ActionButton label={busy === "m365-shortcuts" ? "Adding shortcuts…" : "Add to application menu"} disabled={busy !== null} onClick={() => run("m365-shortcuts", "Adding Microsoft 365 shortcuts…", createM365Shortcuts)} />
          </div>
        </div>
        <div style={{ marginTop: 20, paddingTop: 16, borderTop: "1px solid var(--hairline)" }}>
          <p className="work-setup-copy" style={{ fontWeight: 700 }}>Outlook archives</p>
          <p className="work-setup-copy">Find .pst/.ost files in your user folders and convert them to mail folders under Documents/Outlook Import. Nothing is deleted.</p>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 10 }}>
            <ActionButton label={busy === "pst-scan" ? "Scanning…" : "Find Outlook archives"} disabled={busy !== null} onClick={() => run("pst-scan", "Scanning for Outlook archives…", async () => { const files = await fetchPstFiles(); setPstFiles(files); return files ? `${files.length} archive(s) found.` : "Archive scanning is unavailable outside the Hub shell."; })} />
          </div>
          {pstFiles && (pstFiles.length ? <div style={{ display: "grid", gap: 6, marginTop: 10 }}>{pstFiles.map((path) => <div key={path} style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}><span className="card-copy" style={{ flex: 1, fontSize: 12 }}>{path}</span><ActionButton label={busy === `pst-${path}` ? "Converting…" : "Convert"} disabled={busy !== null} onClick={() => run(`pst-${path}`, "Converting Outlook archive…", () => convertPst(path))} /></div>)}</div> : <p className="card-copy" style={{ fontSize: 12, marginTop: 8 }}>No archives found in Documents, Downloads, local app data, or mounted user drives.</p>)}
        </div>
        <div style={{ marginTop: 20, paddingTop: 16, borderTop: "1px solid var(--hairline)" }}>
          <p className="work-setup-copy" style={{ fontWeight: 700 }}>Focus session</p>
          <p className="work-setup-copy">Start a timed work block. Kyth keeps the PC awake until it ends; normal power behavior is restored when you stop or finish.</p>
          <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", marginTop: 10 }}>
            {!focusId ? <><select value={focusMinutes} onChange={(event) => setFocusMinutes(Number(event.target.value))} style={{ padding: "7px 10px", borderRadius: 999, border: "1px solid var(--hairline)", background: "var(--card)" }}><option value={25}>25 minutes</option><option value={50}>50 minutes</option><option value={90}>90 minutes</option></select><ActionButton label="Start focus session" disabled={busy !== null} onClick={() => run("focus-start", "Starting focus session…", async () => { const id = await startFocusSession(focusMinutes); setFocusId(id); setFocusRemaining(focusMinutes * 60); return `Focus session started for ${focusMinutes} minutes.`; })} /></> : <><span className="pill pill-ok">Active · {formatFocus(focusRemaining)}</span><ActionButton label="End session" disabled={busy !== null} onClick={() => run("focus-stop", "Ending focus session…", async () => { const result = await stopFocusSession(focusId); setFocusId(null); setFocusRemaining(0); return result; })} /></>}
          </div>
        </div>
        <ActionStatus status={status} />
      </div>
    </LiveSectionCard>
  );
}
