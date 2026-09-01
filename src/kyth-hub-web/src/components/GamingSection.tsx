import { useEffect, useState } from "react";
import type { HubSection } from "../data/hubSections";
import {
  commandText,
  fetchAuditCache,
  fetchGamingLibrary,
  fetchGamingSliceAvailable,
  fetchGamingSliceCommand,
  fetchProtonDbMany,
  fetchAntiCheatTable,
  fetchGamingTools,
  installGamingTool,
  uninstallGamingTool,
  launchGamingTool,
  fixDiscordScreenshare,
  fixObsPipewire,
  fetchPrefixResetHint,
  fetchSupportSnapshotCommand,
  openGameFolder,
  fetchGamingPerfStatus,
  fetchScxStatus,
  setScxScheduler,
  fetchProfileLaunchOption,
  fetchPerGameProfile,
  savePerGameProfile,
  type AntiCheatEntry,
  type ProtonDbResult,
  type AuditCache,
  type LauncherEntry,
  type GamingTool,
  type GamingPerfStatus,
  type ScxStatus,
} from "../services/liveData";
import { LiveSectionCard, SectionFallbackNote } from "./LiveSectionCard";
import { ActionStatus, CommandLine, RecipeButton, useSectionAction } from "./SectionActions";

type SectionRun = (id: string, pendingLabel: string, action: () => Promise<string>) => Promise<void>;
const gamingBtnStyle = { padding: "6px 12px", borderRadius: 999, border: "1px solid var(--hairline)", background: "var(--card)", fontWeight: 600, fontSize: 12 } as const;

// Install/launch/uninstall grid for the curated Flatpak gaming tools.
// Mirrors page_gaming_tools_grid.py's GAMING_TOOLS tiles.
function GamingToolGrid({ busy, run }: { busy: string | null; run: SectionRun }) {
  const [tools, setTools] = useState<GamingTool[] | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchGamingTools().then((value) => { if (!cancelled) setTools(value); });
    return () => { cancelled = true; };
  }, []);

  async function refresh(): Promise<void> {
    const fresh = await fetchGamingTools();
    if (fresh) setTools(fresh);
  }

  if (!tools || tools.length === 0) return null;
  return (
    <div style={{ marginTop: 22 }}>
      <p className="card-copy" style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: 0.6 }}>Gaming tools</p>
      <p className="card-copy" style={{ fontSize: 12, marginTop: 4 }}>Install, launch, or remove launchers and capture tools — status stays live as you go.</p>
      <div style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: 8 }}>
        {tools.map((tool) => (
          <div key={tool.flatpak} style={{ padding: "10px 12px", border: "1px solid var(--hairline)", borderRadius: 10 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <p style={{ fontWeight: 700, fontSize: 13, margin: 0, flex: 1 }}>{tool.name}</p>
              {tool.installed ? (
                <>
                  <button disabled={busy !== null} onClick={() => run(`gt-launch-${tool.flatpak}`, `Launching ${tool.name}…`, () => launchGamingTool(tool.flatpak))} style={gamingBtnStyle}>Launch</button>
                  <button disabled={busy !== null} onClick={() => run(`gt-uninstall-${tool.flatpak}`, `Uninstalling ${tool.name}…`, async () => { const result = await uninstallGamingTool(tool.flatpak); await refresh(); return result; })} style={gamingBtnStyle}>Uninstall</button>
                </>
              ) : (
                <button disabled={busy !== null} onClick={() => run(`gt-install-${tool.flatpak}`, `Installing ${tool.name}…`, async () => { const result = await installGamingTool(tool.flatpak); await refresh(); return result; })} style={gamingBtnStyle}>Install</button>
              )}
            </div>
            <p className="card-copy" style={{ fontSize: 12, marginTop: 4 }}>{tool.desc}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

// Copyable safe launch-option tests, plus one-shot Discord/OBS capture
// permission fixes. Mirrors page_gaming_fixes.py's first-failure playbook.
function FirstFailurePlaybook({ busy, run }: { busy: string | null; run: SectionRun }) {
  const launchOptions: [string, string][] = [
    ["Capture Proton log", "PROTON_LOG=1 %command%"],
    ["Disable NTSYNC", "PROTON_NO_NTSYNC=1 %command%"],
    ["Disable esync", "PROTON_NO_ESYNC=1 %command%"],
    ["Disable fsync", "PROTON_NO_FSYNC=1 %command%"],
    ["Force Vulkan HUD", "MANGOHUD=1 %command%"],
    ["Launcher retry", "PROTON_LOG=1 PROTON_NO_NTSYNC=1 %command%"],
  ];
  return (
    <div style={{ marginTop: 22 }}>
      <p className="card-copy" style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: 0.6 }}>Game will not launch</p>
      <p className="card-copy" style={{ fontSize: 12, marginTop: 6 }}>
        Start simple: try a clean Proton runner, collect a log, then disable one sync path at a time. These launch options are safe per-game tests.
      </p>
      {launchOptions.map(([label, opt]) => <CommandLine key={label} label={label} command={opt} />)}
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 12 }}>
        <a className="action-button" href="https://www.protondb.com" target="_blank" rel="noreferrer">Open ProtonDB</a>
        <a className="action-button" href="https://areweanticheatyet.com" target="_blank" rel="noreferrer">Open Anti-Cheat Status</a>
        <button disabled={busy !== null} onClick={() => run("fix-discord", "Applying Discord screen share repair…", fixDiscordScreenshare)} style={gamingBtnStyle}>Fix Discord screen share</button>
        <button disabled={busy !== null} onClick={() => run("fix-obs", "Applying OBS capture repair…", fixObsPipewire)} style={gamingBtnStyle}>Fix OBS capture</button>
      </div>
    </div>
  );
}

// Fast non-destructive support actions. Mirrors page_gaming_fixes.py's
// "Fix My Game" card.
function FixMyGame({ busy, run }: { busy: string | null; run: SectionRun }) {
  const [resetHint, setResetHint] = useState<string | null>(null);
  const [snapshotCmd, setSnapshotCmd] = useState<string | null>(null);
  useEffect(() => {
    let cancelled = false;
    Promise.all([fetchPrefixResetHint(), fetchSupportSnapshotCommand()]).then(([hint, snap]) => {
      if (!cancelled) { setResetHint(hint); setSnapshotCmd(snap); }
    });
    return () => { cancelled = true; };
  }, []);
  return (
    <div style={{ marginTop: 22 }}>
      <p className="card-copy" style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: 0.6 }}>Fix my game</p>
      <p className="card-copy" style={{ fontSize: 12, marginTop: 6 }}>Fast non-destructive support actions: open the folders players need, copy safe launch tests, and generate diagnostics.</p>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 10 }}>
        <button disabled={busy !== null} onClick={() => run("open-compatdata", "Opening compatdata…", () => openGameFolder("compatdata"))} style={gamingBtnStyle}>Open Steam compatdata</button>
        <button disabled={busy !== null} onClick={() => run("open-shadercache", "Opening shadercache…", () => openGameFolder("shadercache"))} style={gamingBtnStyle}>Open shadercache</button>
      </div>
      <CommandLine label="Reset a Proton prefix (safe — backs up, doesn't delete)" command={resetHint} />
      <CommandLine label="Support snapshot" command={snapshotCmd} />
    </div>
  );
}

// "Play > Gaming" — audit master profile + live launcher library scan.
// Previously only audit pills; now also shows which launchers are installed
// and library counts, matching page_gaming_library.py's Steam/Heroic scan.
// Overlay tools (MangoHud/Gamescope/vkBasalt) install-status badges plus
// their copyable Steam launch options. Mirrors page_gaming_tools_perf.py's
// overlays-bulk, MangoHud, and Gamescope cards — read-only status, nothing
// to install here (that's the GamingToolGrid/RecipeButton install paths).
function OverlaysCard() {
  const [status, setStatus] = useState<GamingPerfStatus | null>(null);
  useEffect(() => {
    let cancelled = false;
    fetchGamingPerfStatus().then((value) => { if (!cancelled) setStatus(value); });
    return () => { cancelled = true; };
  }, []);

  return (
    <div style={{ marginTop: 22 }}>
      <p className="card-copy" style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: 0.6 }}>Overlays — MangoHud, Gamescope, vkBasalt</p>
      {status && (
        <div style={{ display: "flex", gap: 6, marginTop: 8 }}>
          <span className={`pill ${status.mangohud_installed ? "pill-ok" : "pill-dim"}`}>MangoHud {status.mangohud_installed ? "installed" : "not installed"}</span>
          <span className={`pill ${status.gamescope_installed ? "pill-ok" : "pill-dim"}`}>Gamescope {status.gamescope_installed ? "installed" : "not installed"}</span>
          <span className={`pill ${status.vkbasalt_installed ? "pill-ok" : "pill-dim"}`}>vkBasalt {status.vkbasalt_installed ? "installed" : "not installed"}</span>
        </div>
      )}
      <CommandLine label="MangoHud + vkBasalt" command="MANGOHUD=1 ENABLE_VKBASALT=1 %command%" />
      <CommandLine label="All three via Gamescope" command="MANGOHUD=1 ENABLE_VKBASALT=1 kyth-gamescope quality -- %command%" />
      <CommandLine label="MangoHud only — Steam launch option" command="MANGOHUD=1 %command%" />
      <p className="card-copy" style={{ fontSize: 11, marginTop: 8 }}>Config: /etc/MangoHud/MangoHud.conf · override: ~/.config/MangoHud/MangoHud.conf</p>
      <CommandLine label="Gamescope — quality preset" command="kyth-gamescope quality -- %command%" />
      <CommandLine label="Gamescope — HDR display" command="kyth-gamescope hdr --fps 120 -- %command%" />
      <CommandLine label="Gamescope — sharp upscaling" command="kyth-gamescope sharp --fsr --nested 1920x1080 --output 2560x1440 -- %command%" />
      <CommandLine label="Gamescope — ujust recipe" command="ujust game-scope quality -- %command%" />
    </div>
  );
}

const PROFILE_GOALS: [string, string][] = [
  ["quality", "Balanced quality"],
  ["hdr", "HDR display"],
  ["sharp", "Sharp upscaling"],
  ["latency", "Low latency"],
  ["troubleshoot", "Troubleshoot launch"],
];
const PROFILE_FPS_CAPS: [string, string][] = [
  ["", "No FPS cap"], ["60", "60 FPS"], ["90", "90 FPS"], ["120", "120 FPS"], ["144", "144 FPS"], ["165", "165 FPS"],
];

// Per-game HDR/latency profile builder. Mirrors
// page_gaming_tools_perf.py's _build_profile_builder_card — goal + FPS cap
// combos compute a copyable Steam launch option live via
// profile_launch_option (kyth-shared-rs::system::gaming_perf, the same
// logic as the old Hub's _update_profile_builder dict), and "Save
// per-game" persists goal + HDR to ~/.config/kyth/gaming-per-game.toml.
function ProfileBuilderCard({ busy, run }: { busy: string | null; run: SectionRun }) {
  const [goal, setGoal] = useState("quality");
  const [fps, setFps] = useState("");
  const [hdr, setHdr] = useState(false);
  const [appid, setAppid] = useState("");
  const [launchOption, setLaunchOption] = useState("");
  const [saved, setSaved] = useState<{ profile: string; hdr: boolean } | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchProfileLaunchOption(goal, fps, hdr).then((value) => { if (!cancelled && value) setLaunchOption(value); });
    return () => { cancelled = true; };
  }, [goal, fps, hdr]);

  useEffect(() => {
    let cancelled = false;
    const trimmed = appid.trim();
    if (!trimmed) { setSaved(null); return; }
    const timer = window.setTimeout(() => {
      fetchPerGameProfile(trimmed).then((value) => { if (!cancelled) setSaved(value); });
    }, 250);
    return () => { cancelled = true; window.clearTimeout(timer); };
  }, [appid]);

  return (
    <div style={{ marginTop: 22 }}>
      <p className="card-copy" style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: 0.6 }}>Per-game profile builder</p>
      <p className="card-copy" style={{ fontSize: 12, marginTop: 6 }}>
        Pick a common goal and copy the Steam launch option. Per-game HDR is saved to ~/.config/kyth/gaming-per-game.toml so launches stay lean (no global LD_PRELOAD) and survive reboots.
      </p>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 10 }}>
        <select value={goal} onChange={(event) => setGoal(event.target.value)} style={{ padding: "7px 10px", borderRadius: 999, border: "1px solid var(--hairline)", background: "var(--card)", fontSize: 12.5 }}>
          {PROFILE_GOALS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </select>
        <select value={fps} onChange={(event) => setFps(event.target.value)} style={{ padding: "7px 10px", borderRadius: 999, border: "1px solid var(--hairline)", background: "var(--card)", fontSize: 12.5 }}>
          {PROFILE_FPS_CAPS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </select>
      </div>
      <CommandLine label="Steam launch option" command={launchOption || null} />
      <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap", marginTop: 12 }}>
        <label style={{ fontSize: 12, display: "flex", gap: 6, alignItems: "center", cursor: "pointer" }}>
          <input type="checkbox" checked={hdr} onChange={(event) => setHdr(event.target.checked)} />
          HDR per game (KYTH_HDR=1)
        </label>
        <input
          value={appid}
          onChange={(event) => setAppid(event.target.value)}
          placeholder="Steam app id (optional)"
          style={{ padding: "7px 10px", borderRadius: 999, border: "1px solid var(--hairline)", background: "var(--card)", fontSize: 12, width: 180 }}
        />
        {saved && <span className="card-copy" style={{ fontSize: 11 }}>Currently saved: {saved.profile}{saved.hdr ? " · HDR" : ""}</span>}
        <button
          disabled={busy !== null}
          onClick={() => run("save-per-game", "Saving per-game profile…", () => savePerGameProfile(appid.trim() || "builder-default", goal, hdr))}
          style={gamingBtnStyle}
        >
          {busy === "save-per-game" ? "Saving…" : "Save per-game"}
        </button>
      </div>
      <p className="card-copy" style={{ fontSize: 11, marginTop: 8 }}>Saved per-game — launch env is KYTH_HDR + the goal's flags, no global layer.</p>
    </div>
  );
}

// sched-ext scheduler control. Mirrors page_gaming_tools_perf.py's
// _build_scx_card — KythOS uses scx_rusty for gaming and falls back to
// the kernel scheduler otherwise.
function SchedExtCard({ busy, run }: { busy: string | null; run: SectionRun }) {
  const [status, setStatus] = useState<ScxStatus | null>(null);
  useEffect(() => {
    let cancelled = false;
    fetchScxStatus().then((value) => { if (!cancelled) setStatus(value); });
    return () => { cancelled = true; };
  }, []);

  async function refresh(): Promise<void> {
    setStatus(await fetchScxStatus());
  }

  return (
    <div style={{ marginTop: 22 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <p className="card-copy" style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: 0.6, margin: 0, flex: 1 }}>sched-ext — CPU scheduler</p>
        {status && <span className={`pill ${status.active ? "pill-ok" : "pill-dim"}`}>{status.active ? "Active" : "Inactive"}</span>}
      </div>
      <p className="card-copy" style={{ fontSize: 12, marginTop: 6 }}>KythOS uses Fedora's packaged scx_rusty scheduler for gaming and returns to the kernel scheduler for normal desktop work.</p>
      {status && <p className="card-copy" style={{ fontSize: 12, marginTop: 4 }}>Configured: {status.configured}</p>}
      <div style={{ display: "flex", gap: 8, marginTop: 10 }}>
        <button disabled={busy !== null} onClick={() => run("scx-rusty", "Setting scheduler: rusty…", async () => { const result = await setScxScheduler("rusty"); await refresh(); return result; })} style={gamingBtnStyle}>
          {busy === "scx-rusty" ? "Setting…" : "Use scx_rusty"}
        </button>
        <button disabled={busy !== null} onClick={() => run("scx-stop", "Stopping sched-ext…", async () => { const result = await setScxScheduler("stop"); await refresh(); return result; })} style={gamingBtnStyle}>
          {busy === "scx-stop" ? "Stopping…" : "Stop scx"}
        </button>
      </div>
    </div>
  );
}

export function GamingSection({ section }: { section: HubSection }) {
  const launcherRecipes = [
    ["install-steam", "Steam"], ["install-heroic", "Heroic"], ["install-lutris", "Lutris"],
    ["install-bottles", "Bottles"], ["install-prismlauncher", "Prism Launcher"], ["install-itch", "Itch.io"],
    ["install-epic-launcher", "Epic Games"], ["install-battlenet", "Battle.net"], ["install-ea-app", "EA App"], ["install-ubisoft-connect", "Ubisoft Connect"],
  ] as const;
  const fixRecipes = [
    ["health-check", "Gaming health check"], ["preheat-shaders", "Preheat shaders"], ["enable-obs-capture", "Enable OBS capture"],
    ["game-boost", "Game boost"], ["controller-check", "Check controllers"], ["export-steam-games", "Export Steam library"],
  ] as const;
  const toolRecipes = [
    ["install-obs", "OBS Studio"], ["install-gpu-screen-recorder", "GPU Screen Recorder"],
    ["install-goverlay", "GOverlay"], ["install-mangojuice", "MangoJuice"], ["install-umu", "UMU"],
    ["install-lact", "LACT"], ["install-piper", "Piper"], ["install-solaar", "Solaar"],
  ] as const;
  const [audit, setAudit] = useState<AuditCache | null>(null);
  const [launchers, setLaunchers] = useState<LauncherEntry[] | null>(null);
  const [sliceAvailable, setSliceAvailable] = useState<boolean | null>(null);
  const [sliceCommand, setSliceCommand] = useState<string | null>(null);
  const [gameId, setGameId] = useState("");
  const [proton, setProton] = useState<ProtonDbResult[]>([]);
  const [antiCheat, setAntiCheat] = useState<AntiCheatEntry[] | null>(null);
  const [loaded, setLoaded] = useState(false);
  const { status, busy, run } = useSectionAction();
  useEffect(() => {
    let c = false;
    Promise.all([
      fetchAuditCache(),
      fetchGamingLibrary(),
      fetchGamingSliceAvailable(),
      // Rendered as the string you paste into Steam's launch options, so
      // %command% is the argv placeholder rather than a real program.
      fetchGamingSliceCommand(["%command%"]).then(commandText),
      fetchAntiCheatTable(),
    ]).then(([a, l, avail, cmd, ac]) => {
      if (!c) {
        setAudit(a);
        setLaunchers(l);
        setSliceAvailable(avail);
        setSliceCommand(cmd);
        setAntiCheat(ac);
        setLoaded(true);
      }
    });
    return () => { c = true; };
  }, []);

  async function lookupProtonDb() {
    const ids = gameId.split(/[ ,]+/).map((id) => id.trim()).filter(Boolean).slice(0, 20);
    setProton((await fetchProtonDbMany(ids)) ?? []);
  }
  const live = audit !== null || launchers !== null;
  return (
    <LiveSectionCard section={section} live={live}>
      {audit ? (
        <div style={{ marginTop: 20 }}>
          <p className="card-copy" style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: 0.6 }}>Master profile</p>
          <p style={{ margin: "4px 0 0", fontSize: 15, fontWeight: 700 }}>{String(audit.master ?? "unknown")}</p>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 12 }}>
            {(["loader", "oom_gaming", "shader_tmpfs", "gaming_cfs", "ananicy", "kwin"] as const).map((k) => (
              <span key={k} className="pill pill-dim">{k}: {String(audit[k] ?? "\u2014")}</span>
            ))}
          </div>
          {launchers && launchers.length > 0 && (
            <div style={{ marginTop: 20 }}>
              <p className="card-copy" style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: 0.6 }}>Launchers</p>
              <div style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: 8 }}>
                {launchers.map((l) => (
                  <div key={l.id} style={{ display: "flex", alignItems: "center", gap: 10, fontSize: 13 }}>
                    <span className={`pill ${l.installed ? "pill-ok" : "pill-dim"}`}>{l.installed ? "installed" : "not installed"}</span>
                    <span style={{ fontWeight: 600 }}>{l.label}</span>
                    <span className="card-copy" style={{ fontSize: 12 }}>{l.library_count != null ? `${l.library_count} games` : l.path}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      ) : (
        <SectionFallbackNote loaded={loaded} />
      )}

      <div style={{ marginTop: 20, borderTop: "1px solid var(--hairline)", paddingTop: 16 }}>
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 12 }}>
          <span className={`pill ${sliceAvailable ? "pill-ok" : "pill-dim"}`}>
            gaming slice: {sliceAvailable == null ? "unknown" : sliceAvailable ? "available" : "unavailable"}
          </span>
        </div>
        {sliceAvailable && (
          <CommandLine label="Steam launch options — runs the game in its own cgroup" command={sliceCommand} />
        )}
        <div style={{ marginTop: 20 }}>
          <p className="card-copy" style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: 0.6 }}>ProtonDB lookup</p>
          <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
            <input value={gameId} onChange={(event) => setGameId(event.target.value)} placeholder="Steam IDs, e.g. 730, 570" inputMode="numeric" style={{ flex: 1, maxWidth: 220, padding: "8px 12px", borderRadius: 999, border: "1px solid var(--hairline)", background: "var(--card)", fontSize: 13 }} />
            <button disabled={!gameId.trim()} onClick={lookupProtonDb} style={{ padding: "7px 14px", borderRadius: 999, border: "1px solid var(--hairline)", background: "var(--card)", fontWeight: 600 }}>Look up</button>
          </div>
          {proton.length > 0 ? proton.map((result) => <p key={result.app_id} className="card-copy" style={{ fontSize: 12, marginTop: 8 }}>{result.app_id}: {result.detail}</p>) : gameId && <p className="card-copy" style={{ fontSize: 12, marginTop: 8 }}>Enter one or more Steam app IDs and look up current ProtonDB reports.</p>}
        </div>
        {antiCheat && <div style={{ marginTop: 20 }}>
          <p className="card-copy" style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: 0.6 }}>Anti-cheat compatibility</p>
          {antiCheat.map((entry) => <div key={entry.game} style={{ display: "flex", gap: 8, marginTop: 8, fontSize: 12 }}><span className="pill pill-dim">{entry.status}</span><span><strong>{entry.game}</strong> — {entry.detail}</span></div>)}
        </div>}
        <div style={{ marginTop: 20 }}>
          <p className="card-copy" style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: 0.6 }}>Migration checklist</p>
          <p className="card-copy" style={{ fontSize: 12, marginTop: 8 }}>Back up saves, install the launcher, verify each title in ProtonDB, then test controller and anti-cheat requirements before deleting the old install.</p>
        </div>
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginTop: 12 }}>
          <RecipeButton recipe="gaming-mode" label="Switch to gaming mode" busy={busy} run={run} />
          <RecipeButton recipe="gaming-stack-status" label="Gaming stack status" busy={busy} run={run} />
        </div>
        <div style={{ marginTop: 22 }}>
          <p className="card-copy" style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: 0.6 }}>Gaming setup</p>
          <p className="card-copy" style={{ fontSize: 12, marginTop: 6 }}>Install a launcher or tool from this window. Progress, prompts, and the result stay in the Hub.</p>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 10 }}>
            {launcherRecipes.map(([recipe, label]) => <RecipeButton key={recipe} recipe={recipe} label={label} busy={busy} run={run} />)}
          </div>
        </div>
        <div style={{ marginTop: 22 }}>
          <p className="card-copy" style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: 0.6 }}>Fixes and tools</p>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 10 }}>
            {[...fixRecipes, ...toolRecipes].map(([recipe, label]) => <RecipeButton key={recipe} recipe={recipe} label={label} busy={busy} run={run} />)}
          </div>
        </div>
        <GamingToolGrid busy={busy} run={run} />
        <FirstFailurePlaybook busy={busy} run={run} />
        <FixMyGame busy={busy} run={run} />
        <OverlaysCard />
        <ProfileBuilderCard busy={busy} run={run} />
        <SchedExtCard busy={busy} run={run} />
        <ActionStatus status={status} />
      </div>
    </LiveSectionCard>
  );
}
