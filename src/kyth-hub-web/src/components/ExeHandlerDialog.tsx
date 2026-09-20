import { listen } from "@tauri-apps/api/event";
import { useEffect, useRef, useState } from "react";
import {
  cancelExeHandlerBottles,
  fetchInstallStatus,
  inspectExeHandler,
  isExeHandlerFlatpakInstalled,
  launchExeHandlerFlatpak,
  launchExeHandlerUmu,
  trustExeHandlerFile,
  untrustExeHandlerFile,
  openExeHandlerFlathub,
  setExeHandlerAutoBottles,
  startExeHandlerBottles,
  startExeHandlerFlatpakInstall,
  takePendingExeHandler,
  type ExeHandlerInspection,
  type ExeHandlerJob,
} from "../services/liveData";
import { inTauriShell } from "../services/tauriEnv";

/** Handles `kyth-exe-handler` launches forwarded from the native MIME
 * launcher. It intentionally has no browser fallback: files are opened only
 * by the installed Tauri shell, whose Rust commands validate the path. */
export function ExeHandlerDialog() {
  const [inspection, setInspection] = useState<ExeHandlerInspection | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [autoBottles, setAutoBottles] = useState(false);
  const [trustDirect, setTrustDirect] = useState(false);
  const [flatpakInstalled, setFlatpakInstalled] = useState(false);
  const [job, setJob] = useState<ExeHandlerJob | null>(null);
  const [pollEpoch, setPollEpoch] = useState(0);
  const [cancelling, setCancelling] = useState(false);
  const startedAutomatically = useRef(false);

  useEffect(() => {
    if (!inTauriShell()) return;
    const open = async (path: string) => {
      setError(null); setJob(null); setFlatpakInstalled(false); setTrustDirect(false); startedAutomatically.current = false;
      try {
        const next = await inspectExeHandler(path);
        setInspection(next); setAutoBottles(next.auto_bottles);
        if (next.flatpak_id) setFlatpakInstalled(await isExeHandlerFlatpakInstalled(next.flatpak_id).catch(() => false));
      } catch (reason) { setInspection(null); setError(String(reason)); }
    };
    let unlisten: (() => void) | undefined;
    void (async () => {
      unlisten = await listen<string>("exe-handler", (event) => void open(event.payload));
      const initial = await takePendingExeHandler();
      if (initial) await open(initial);
    })();
    return () => unlisten?.();
  }, []);

  // Cancel reaches the real backend job (app-installs store): the dialog
  // stays open showing the outcome instead of orphaning a headless
  // provisioning run. With no running job the button just closes.
  const closeOrCancel = async () => {
    if (job && job.state === "running" && !cancelling) {
      setCancelling(true);
      try {
        const detail = await cancelExeHandlerBottles(job.job);
        const next = await fetchInstallStatus(job.job).catch(() => null);
        setJob(next ? { job: next.id, state: next.state, detail: next.detail } : { ...job, state: "cancelled", detail });
      } catch (reason) {
        setError(String(reason));
      } finally {
        setCancelling(false);
      }
      return;
    }
    setInspection(null);
  };

  const startBottles = async (allowUnsupported = false) => {
    if (!inspection) return;
    if (inspection.compatibility?.level === "unsupported" && !allowUnsupported) {
      if (!window.confirm(`${inspection.compatibility.detail}\n\nTry it anyway?`)) return;
      return startBottles(true);
    }
    try {
      setError(null);
      setJob(await startExeHandlerBottles(inspection.path, allowUnsupported));
      if (trustDirect && inspection.sha256_full) {
        await trustExeHandlerFile(inspection.sha256_full, inspection.basename, "bottles").catch((reason) => setError(String(reason)));
      }
    } catch (reason) { setError(String(reason)); }
  };

  const startUmu = async () => {
    if (!inspection) return;
    try {
      setError(null);
      await launchExeHandlerUmu(inspection.path);
      if (trustDirect && inspection.sha256_full) {
        await trustExeHandlerFile(inspection.sha256_full, inspection.basename, "umu").catch((reason) => setError(String(reason)));
      }
      setInspection(null);
    } catch (reason) { setError(String(reason)); }
  };

  useEffect(() => {
    if (!inspection || inspection.is_rpm || !inspection.auto_bottles || startedAutomatically.current || inspection.compatibility?.level === "unsupported") return;
    startedAutomatically.current = true;
    void startBottles();
  }, [inspection]); // Deliberately runs only for a new native MIME launch.

  useEffect(() => {
    if (!job || job.state !== "running") return;
    // Bottles provisioning can hang on a dead mirror: cap at 240 polls
    // (~3 minutes at 750ms) then surface a terminal error instead of
    // spinning forever.
    let polls = 0;
    const timer = window.setInterval(async () => {
      polls += 1;
      if (polls >= 240) {
        window.clearInterval(timer);
        setError("The installer is still running after several minutes. It may finish in the background — keep waiting, or close and re-open the file to resume tracking.");
        return;
      }
      const next = await fetchInstallStatus(job.job);
      if (next) setJob({ job: next.id, state: next.state, detail: next.detail });
    }, 750);
    return () => window.clearInterval(timer);
  }, [job, pollEpoch]);

  if (!inspection && !error) return null;
  const unsupported = inspection?.compatibility?.level === "unsupported";
  return (
    <div role="dialog" aria-modal="true" aria-label="Installer help" style={{ position: "fixed", inset: 0, zIndex: 50, background: "rgba(8, 12, 20, .72)", display: "grid", placeItems: "center", padding: 24 }}>
      <section className="glass dashboard-card" style={{ width: "min(620px, 100%)", padding: 28 }}>
        <h2 style={{ marginTop: 0 }}>{inspection?.is_rpm ? "KythOS — Installer Help" : "KythOS — Windows Application"}</h2>
        {inspection && <>
          <p style={{ opacity: .72, overflowWrap: "anywhere" }}>{inspection.basename}</p>
          <h3>{inspection.app_name ?? "Windows Application"}</h3>
          <p style={{ whiteSpace: "pre-line", lineHeight: 1.5 }}>{inspection.suggestion}</p>
          {inspection.compatibility && <>
            <p><strong style={{ color: unsupported ? "#f48771" : inspection.compatibility.level === "likely" ? "#73c991" : "#d7ba7d" }}>{inspection.compatibility.summary.toUpperCase()}</strong> — {inspection.compatibility.detail}</p>
            <p style={{ opacity: .72, fontSize: ".9em" }}>Kyth runs Windows software in an isolated compatibility environment. Apps that need Windows drivers, kernel anti-cheat, device services, or Microsoft Store components generally will not work.</p>
            {inspection.sha256_prefix && <p style={{ opacity: .6, fontSize: ".82em" }}>SHA-256: {inspection.sha256_prefix}…</p>}
          </>}
          {job && <p role="status"><strong>{job.state === "failed" ? "Could not open installer:" : "Installer workflow:"}</strong> {job.detail}</p>}
          {error && <p role="alert" style={{ color: "#f48771" }}>{error} {job?.state === "running" && <button onClick={() => { setError(null); setPollEpoch((epoch) => epoch + 1); }}>Keep waiting</button>}</p>}
          {!inspection.is_rpm && (inspection.trusted_direct
            ? <p style={{ opacity: .72, fontSize: ".9em" }}>✓ Trusted — double-clicking this file runs it directly. <button onClick={() => { if (inspection.sha256_full) void untrustExeHandlerFile(inspection.sha256_full).then(() => setInspection({ ...inspection, trusted_direct: false })).catch((reason) => setError(String(reason))); }}>Forget this file</button></p>
            : <label style={{ display: "block", margin: "16px 0 4px" }}><input type="checkbox" checked={trustDirect} onChange={(event) => setTrustDirect(event.target.checked)} /> Always run this exact file directly (skip this dialog next time — any change to the file asks again)</label>)}
          {!inspection.is_rpm && <label style={{ display: "block", margin: "16px 0" }}><input type="checkbox" checked={autoBottles} onChange={async (event) => { const enabled = event.target.checked; setAutoBottles(enabled); try { await setExeHandlerAutoBottles(enabled); } catch (reason) { setError(String(reason)); } }} /> Skip this dialog for future installers rated Likely — start Bottles straight away</label>}
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
            {inspection.is_rpm && <button onClick={() => { window.location.hash = "/apps"; setInspection(null); }}>Open App Store</button>}
            {!inspection.is_rpm && <button onClick={() => void startBottles()} disabled={job?.state === "running"}>{unsupported ? "Try Anyway" : "Run Windows Installer"}</button>}
            {!inspection.is_rpm && !unsupported && <button onClick={() => void startUmu()} disabled={job?.state === "running"}>Run Game with Proton</button>}
            {inspection.flatpak_id && <button onClick={() => {
              if (flatpakInstalled) void launchExeHandlerFlatpak(inspection.flatpak_id!).then(() => setInspection(null)).catch((reason) => setError(String(reason)));
              else void startExeHandlerFlatpakInstall(inspection.flatpak_id!).then(setJob).catch((reason) => setError(String(reason)));
            }}>{flatpakInstalled ? "Launch Linux Version" : "Install Linux Version"}</button>}
            <button onClick={() => void openExeHandlerFlathub(inspection.search_term).catch((reason) => setError(String(reason)))}>Search Flathub</button>
            {/* Cancel reaches the backend job while one runs (the dialog stays
              open showing the outcome); otherwise it just closes. */}
            <button onClick={() => void closeOrCancel()} disabled={cancelling}>{job?.state === "running" ? (cancelling ? "Cancelling…" : "Cancel") : "Close"}</button>
          </div>
        </>}
        {error && !inspection && <><p role="alert" style={{ color: "#f48771" }}>{error}</p><button onClick={() => setError(null)}>Close</button></>}
      </section>
    </div>
  );
}
