import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import {
  fetchAuditCache,
  fetchCompatibilityGames,
  fetchControllersLive,
  fetchGamingLibrary,
  fetchGamingPerfStatus,
  fetchTelemetryRecent,
  type AuditCache,
  type CompatibilityGame,
  type ControllersLive,
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
};

const emptyReadings: PlayReadings = {
  audit: null,
  launchers: null,
  controllers: null,
  compatibility: null,
  performance: null,
  sessions: null,
};

async function readPlay(): Promise<PlayReadings> {
  const [audit, launchers, controllers, compatibility, performance, sessions] = await Promise.all([
    fetchAuditCache(),
    fetchGamingLibrary(),
    fetchControllersLive(),
    fetchCompatibilityGames(),
    fetchGamingPerfStatus(),
    fetchTelemetryRecent(1),
  ]);
  return { audit, launchers, controllers, compatibility, performance, sessions };
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

export function PlayOverview() {
  const [readings, setReadings] = useState<PlayReadings>(emptyReadings);
  const [loaded, setLoaded] = useState(false);
  const [, setSearchParams] = useSearchParams();
  const { status, busy, run } = useSectionAction();

  useEffect(() => {
    let cancelled = false;
    readPlay().then((next) => {
      if (!cancelled) {
        setReadings(next);
        setLoaded(true);
      }
    });
    return () => { cancelled = true; };
  }, []);

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
    : `${driverCount} controller driver${driverCount === 1 ? "" : "s"} loaded · test input in Controllers.`;
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
        <PlayCard icon="✦" label="Performance" value={performanceValue} detail={performanceDetail} status={readings.audit || readings.performance ? true : null} />
        <PlayCard icon="✓" label="Compatibility" value={compatibilityValue} detail={compatibilityDetail} status={supportedGames === null ? null : blockedGames === 0} />
        <PlayCard icon="◷" label="Recent play" value={sessionValue} detail={sessionDetail} status={readings.sessions === null ? null : true} />
      </div>

      <div className="play-actions-card">
        <div>
          <span className="play-eyebrow">Start playing</span>
          <h2>{readinessDetail}</h2>
          <p>Jump straight into the task you want to finish.</p>
        </div>
        <div className="play-actions">
          <ActionButton label="Install a launcher" disabled={busy !== null} onClick={() => openSection("Gaming")} />
          <ActionButton label="Tune performance" disabled={busy !== null} onClick={() => openSection("Performance")} />
          <ActionButton label="Pair a controller" disabled={busy !== null} onClick={() => openSection("Controllers")} />
          <ActionButton label="Check a game" disabled={busy !== null} onClick={() => openSection("Compatibility")} />
          <ActionButton label={busy === "play-refresh" ? "Refreshing…" : "Refresh status"} disabled={busy !== null} onClick={() => void run("play-refresh", "Refreshing Play status…", refresh)} />
        </div>
      </div>
      <ActionStatus status={status} />
    </section>
  );
}
