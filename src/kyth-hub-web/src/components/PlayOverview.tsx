import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import {
  fetchAuditCache,
  fetchCompatibilityGames,
  fetchControllersLive,
  fetchFirstbootAppsStatus,
  fetchSteamPlayStatus,
  fetchGamingLibrary,
  fetchGamingPerfStatus,
  fetchTelemetryRecent,
  type AuditCache,
  type CompatibilityGame,
  type ControllersLive,
  type FirstbootAppsStatus,
  type SteamPlayStatus,
  type GamingPerfStatus,
  type LauncherEntry,
  type TelemetrySession,
} from "../services/liveData";
import { ActionButton, ActionStatus, useSectionAction } from "./SectionActions";

type PlayReadings = {
  audit: AuditCache | null;
  launchers: LauncherEntry[] | null;
  controllers: ControllersLive | null;
  compatibility: CompatibilityGame[] | null;
  performance: GamingPerfStatus | null;
  sessions: TelemetrySession[] | null;
  firstboot: FirstbootAppsStatus | null;
  steamPlay: SteamPlayStatus | null;
};

const emptyReadings: PlayReadings = {
  audit: null,
  launchers: null,
  controllers: null,
  compatibility: null,
  performance: null,
  sessions: null,
  firstboot: null,
  steamPlay: null,
};

async function readPlay(): Promise<PlayReadings> {
  const [audit, launchers, controllers, compatibility, performance, sessions, firstboot, steamPlay] = await Promise.all([
    fetchAuditCache(),
    fetchGamingLibrary(),
    fetchControllersLive(),
    fetchCompatibilityGames(),
    fetchGamingPerfStatus(),
    fetchTelemetryRecent(15),
    fetchFirstbootAppsStatus(),
    fetchSteamPlayStatus(),
  ]);
  return { audit, launchers, controllers, compatibility, performance, sessions, firstboot, steamPlay };
}

function tone(status: boolean | null): string {
  return status === null ? "play-card-muted" : status ? "play-card-ok" : "play-card-warn";
}

function PlayCard({ icon, label, value, detail, status }: {
  icon: string;
  label: string;
  value: string;
  detail: string;
  status: boolean | null;
}) {
  return (
    <article className={`play-card ${tone(status)}`}>
      <div className="play-card-top">
        <span className="play-card-icon" aria-hidden="true">{icon}</span>
        <span className="play-card-label">{label}</span>
        <span className={`play-status-dot ${status === null ? "play-status-unknown" : status ? "play-status-ok" : "play-status-warn"}`} />
      </div>
      <strong className="play-card-value">{value}</strong>
      <span className="play-card-detail">{detail}</span>
    </article>
  );
}

export function PlayOverview({ onTelemetryLoaded }: { onTelemetryLoaded?: (sessions: TelemetrySession[] | null) => void }) {
  const [readings, setReadings] = useState<PlayReadings>(emptyReadings);
  const [loaded, setLoaded] = useState(false);
  const [, setSearchParams] = useSearchParams();
  const { status, busy, run } = useSectionAction("hub-action");

  useEffect(() => {
    let cancelled = false;
    readPlay().then((next) => {
      if (!cancelled) {
        setReadings(next);
        onTelemetryLoaded?.(next.sessions);
        setLoaded(true);
      }
    });
    return () => { cancelled = true; };
  }, [onTelemetryLoaded]);

  const installedLaunchers = readings.launchers?.filter((launcher) => launcher.installed) ?? null;
  const gameCount = installedLaunchers?.reduce((total, launcher) => total + (launcher.library_count ?? 0), 0) ?? null;
  const controllerCount = readings.controllers
    ? Math.max(readings.controllers.usb_controllers.length, readings.controllers.input_nodes.length)
    : null;
  const driverCount = readings.controllers
    ? [readings.controllers.xone_loaded, readings.controllers.xpadneo_loaded, readings.controllers.hid_ps_loaded].filter(Boolean).length
    : null;
  const supportedGames = readings.compatibility?.filter((game) => game.status !== "blocked").length ?? null;
  const blockedGames = readings.compatibility?.filter((game) => game.status === "blocked").length ?? null;
  const overlayCount = readings.performance
    ? [readings.performance.mangohud_installed, readings.performance.gamescope_installed, readings.performance.vkbasalt_installed].filter(Boolean).length
    : null;
  const latestSession = readings.sessions?.[0] ?? null;
  const hasReadings = Object.values(readings).some((value) => value !== null);

  const readinessDetail = useMemo(() => {
    if (!loaded) return "Reading launchers, controllers, and gaming support…";
    if (!hasReadings) return "Gaming readings are not available yet.";
    const parts: string[] = [];
    if (installedLaunchers) parts.push(`${installedLaunchers.length} launcher${installedLaunchers.length === 1 ? "" : "s"}`);
    if (gameCount !== null && gameCount > 0) parts.push(`${gameCount} game${gameCount === 1 ? "" : "s"} found`);
    if (controllerCount !== null && controllerCount > 0) parts.push(`${controllerCount} controller${controllerCount === 1 ? "" : "s"}`);
    return parts.length > 0 ? parts.join(" · ") : "Start by installing a launcher or pairing a controller.";
  }, [controllerCount, gameCount, hasReadings, installedLaunchers, loaded]);

  async function refresh(): Promise<string> {
    const next = await readPlay();
    setReadings(next);
    setLoaded(true);
    return "Play status refreshed.";
  }

  function openSection(section: string) {
    setSearchParams({ section }, { replace: true });
    window.setTimeout(() => document.querySelector(".tab-nav")?.scrollIntoView({ behavior: "smooth", block: "start" }), 0);
  }

  // First-run setup checklist: ordered, state-driven, no dead ends. Each
  // step completes from live readings; the first incomplete step owns the
  // primary button. Controller pairing is optional and never blocks play.
  const steamInstalled = installedLaunchers?.some((launcher) => launcher.installed && /steam/i.test(`${launcher.id} ${launcher.label}`)) ?? null;
  const gamingProfile = readings.audit?.master === "gaming";
  type SetupStep = { key: string; label: string; hint: string; done: boolean | null; optional?: boolean; section: string; action: string };
  const setupSteps: SetupStep[] = [
    { key: "steam", label: "Install Steam", hint: readings.firstboot?.state === "setting_up" ? "Steam is installing in the background right now — give it a few minutes, then refresh." : "Your game library starts here — KythOS installs it as a Flatpak.", done: steamInstalled, section: "Gaming", action: "Install Steam" },
    { key: "games", label: "Log into Steam and find your games", hint: readings.steamPlay && !readings.steamPlay.mapping_present ? `${readings.steamPlay.detail} Sign in first, then turn it on.` : "Sign in, then enable Steam Play for all titles so Windows games are playable.", done: gameCount === null || steamInstalled === false ? null : gameCount > 0, section: "Gaming", action: "Open game libraries" },
    { key: "controller", label: "Pair a controller (optional)", hint: "Xbox, DualSense, and Switch pads work out of the box, wired or Bluetooth.", done: controllerCount === null ? null : controllerCount > 0, optional: true, section: "Controllers", action: "Pair a controller" },
    { key: "perf", label: "Enable the gaming profile", hint: "Performance CPU scheduling, reduced latency, and overlay support.", done: readings.audit || readings.performance ? gamingProfile : null, section: "Performance", action: "Enable gaming profile" },
  ];
  const setupComplete = setupSteps.every((step) => step.done !== false);

  const launchersValue = installedLaunchers === null
    ? "Checking…"
    : installedLaunchers.length === 0
      ? "No launcher yet"
      : `${installedLaunchers.length} installed`;
  const launchersDetail = gameCount !== null && gameCount > 0
    ? `${gameCount} game${gameCount === 1 ? "" : "s"} across your libraries.`
    : "Steam, Heroic, Lutris, Bottles, and more are ready to set up.";
  const controllerValue = controllerCount === null ? "Checking…" : controllerCount === 0 ? "No controller found" : `${controllerCount} connected`;
  const controllerDetail = driverCount === null
    ? "Checking USB devices and controller drivers."
    : `${driverCount} controller driver${driverCount === 1 ? "" : "s"} loaded · pair and rescan in Controllers.`;
  const performanceValue = readings.audit?.master ? String(readings.audit.master) : readings.performance ? "Ready to tune" : "Checking…";
  const performanceDetail = overlayCount === null
    ? "Gaming profile and overlay status are being checked."
    : `${overlayCount}/3 gaming overlays installed · adjust profiles in Performance.`;
  const compatibilityValue = supportedGames === null
    ? "Checking…"
    : readings.compatibility?.length === 0
      ? "No titles listed"
      : `${supportedGames}/${readings.compatibility?.length ?? 0} workable`;
  const compatibilityDetail = blockedGames === null
    ? "Check Proton and anti-cheat support before installing a title."
    : blockedGames > 0
      ? `${blockedGames} title${blockedGames === 1 ? "" : "s"} currently blocked by compatibility limits.`
      : "No blocked titles in the bundled compatibility matrix.";
  const sessionValue = latestSession?.game_name || (readings.sessions ? "No sessions yet" : "Checking…");
  const sessionDetail = latestSession?.avg_fps != null
    ? `${Math.round(latestSession.avg_fps)} FPS average · recent play telemetry.`
    : "Play a game to see performance history here.";

  return (
    <section className="play-overview" aria-label="Play overview">
      <div className="play-hero">
        <div>
          <span className="play-eyebrow">Gaming command center</span>
          <h1>Everything you need to play</h1>
          <p>Install launchers, tune performance, check compatibility, and keep your controllers ready from one place.</p>
        </div>
        <div className={`play-ready-chip ${hasReadings ? "play-ready-ok" : "play-ready-unknown"}`}><span />{hasReadings ? "Ready when you are" : "Checking setup"}</div>
      </div>

      <div className="play-card-grid">
        <PlayCard icon="▶" label="Game libraries" value={launchersValue} detail={launchersDetail} status={installedLaunchers === null ? null : installedLaunchers.length > 0} />
        <PlayCard icon="◉" label="Controllers" value={controllerValue} detail={controllerDetail} status={controllerCount === null ? null : controllerCount > 0} />
        {/* Same signal the "Enable the gaming profile" setup step already
            uses (gamingProfile) — the status dot used to go green as soon
            as the audit/performance read merely succeeded, regardless of
            whether the gaming profile was actually on, contradicting the
            setup checklist right below it on the same page. */}
        <PlayCard icon="✦" label="Performance" value={performanceValue} detail={performanceDetail} status={readings.audit || readings.performance ? gamingProfile : null} />
        <PlayCard icon="✓" label="Compatibility" value={compatibilityValue} detail={compatibilityDetail} status={supportedGames === null ? null : blockedGames === 0} />
        <PlayCard icon="◷" label="Recent play" value={sessionValue} detail={sessionDetail} status={readings.sessions === null ? null : true} />
      </div>

      <div className="play-actions-card">
        <div>
          <span className="play-eyebrow">{setupComplete ? "Start playing" : "Get set up to play"}</span>
          <h2>{setupComplete ? readinessDetail : "Four steps to your first game"}</h2>
          <p>{setupComplete ? "Jump straight into the task you want to finish." : "Work top to bottom — each step lights up as it completes."}</p>
        </div>
        {setupComplete ? (
        <div className="play-actions">
          <ActionButton label="Install a launcher" disabled={busy !== null} onClick={() => openSection("Gaming")} />
          <ActionButton label="Tune performance" disabled={busy !== null} onClick={() => openSection("Performance")} />
          <ActionButton label="Pair a controller" disabled={busy !== null} onClick={() => openSection("Controllers")} />
          <ActionButton label="Check a game" disabled={busy !== null} onClick={() => openSection("Compatibility")} />
          <ActionButton label={busy === "play-refresh" ? "Refreshing…" : "Refresh status"} disabled={busy !== null} onClick={() => void run("play-refresh", "Refreshing Play status…", refresh)} />
        </div>
        ) : (
        <ol className="play-setup-list">
          {setupSteps.map((step, index) => (
            <li key={step.key} className={step.done ? "play-setup-done" : step.done === null ? "play-setup-pending" : index === setupSteps.findIndex((s) => s.done === false) ? "play-setup-next" : "play-setup-todo"}>
              <span className="play-setup-marker" aria-hidden="true">{step.done ? "✓" : step.done === null ? "…" : `${index + 1}`}</span>
              <div>
                <strong>{step.label}</strong>
                <p>{step.hint}</p>
              </div>
              {!step.done && <ActionButton label={step.action} disabled={busy !== null} onClick={() => openSection(step.section)} />}
            </li>
          ))}
        </ol>
        )}
      </div>
      <ActionStatus status={status} />
    </section>
  );
}
