import { useEffect, useState } from "react";
import type { GuardianEvent } from "../data/dashboardTypes";
import { GuardianHistoryCard } from "../components/GuardianHistoryCard";
import { ActionButton } from "../components/SectionActions";
import { useNavigate } from "react-router-dom";
import { degradedDashboardAcceptance, recordHubAcceptance } from "../services/acceptance";
import {
  fetchBootRuntimeChecks,
  fetchGpuName,
  fetchGuardianSnapshot,
  dismissGuardianRecommendation,
  invokeGuardianExecute,
  fetchRecoveryStatus,
  fetchStorageFree,
  fetchUpdateChannel,
  fetchUserName,
  relativeTime,
  type BootRuntimeCheck,
  type GuardianSnapshot,
  type RecoveryStatus,
} from "../services/liveData";

// Every value on this page comes from a live read or renders as "no
// reading yet" — including both charts, which read telemetry_recent. The
// fixtures this page used to fall back to are gone (see dashboardTypes.ts):
// a failed fetch left the mock tile in place, so "412 GB" and "RX 7900 XTX"
// rendered as though they were this machine's facts.
function HomeCard({ icon, label, value, detail, good, pendingLabel, pendingNote, meterValue }: { icon: string; label: string; value: string; detail: string; good: boolean | null; pendingLabel?: string; pendingNote?: string; meterValue?: number | null }) {
  const tone = good === null ? "home-card-muted" : good ? "home-card-ok" : "home-card-warn";
  return <article className={`home-card ${tone}`} aria-busy={good === null}><div className="home-card-top"><span className="home-card-icon" aria-hidden="true">{icon}</span><span className="home-card-label">{label}</span><span className="home-status-dot" /></div><strong className="home-card-value">{value}</strong><span className="home-card-detail">{detail}</span>{pendingLabel && good === null && <span className="sr-only">{pendingLabel}{pendingNote ? `: ${pendingNote}` : ""}</span>}{meterValue !== undefined && meterValue !== null && <meter className="home-card-meter" min={0} max={2} value={meterValue} aria-label={`${label}: ${meterValue} of 2 safeguards ready`} />}</article>;
}

export function Dashboard() {
  const navigate = useNavigate();
  const [guardian, setGuardian] = useState<GuardianSnapshot | null>(null);
  const [updateChannel, setUpdateChannel] = useState<string | null>(null);
  const [gpuName, setGpuName] = useState<string | null>(null);
  const [storageFree, setStorageFree] = useState<string | null>(null);
  const [userName, setUserName] = useState<string | null>(null);
  const [bootChecks, setBootChecks] = useState<BootRuntimeCheck[] | null>(null);
  const [recovery, setRecovery] = useState<RecoveryStatus | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [, setClock] = useState(() => Date.now());

  useEffect(() => {
    let cancelled = false;
    let forcedDegraded = false;
    async function readDashboard() {
      if (await degradedDashboardAcceptance()) {
        forcedDegraded = true;
        if (!cancelled) {
          setLoaded(true);
          void recordHubAcceptance("dashboard", JSON.stringify({ state: "degraded", label: "Status unavailable" }));
        }
        return;
      }
      const [nextGuardian, nextChannel, nextGpu, nextStorage, nextUser, nextBoot, nextRecovery] = await Promise.all([
        fetchGuardianSnapshot(), fetchUpdateChannel(), fetchGpuName(), fetchStorageFree(),
        fetchUserName(), fetchBootRuntimeChecks(), fetchRecoveryStatus(),
      ]);
      if (cancelled) return;
      setGuardian(nextGuardian);
      setUpdateChannel(nextChannel);
      setGpuName(nextGpu);
      setStorageFree(nextStorage);
      setUserName(nextUser);
      setBootChecks(nextBoot);
      setRecovery(nextRecovery);
      setLoaded(true);
      const hasInitialReadings = nextGuardian !== null || nextBoot !== null || nextRecovery !== null || nextChannel !== null || nextGpu !== null || nextStorage !== null;
      void recordHubAcceptance("dashboard", JSON.stringify({ state: hasInitialReadings ? "live" : "degraded", label: hasInitialReadings ? "System at a glance" : "Status unavailable" }));
    }
    void readDashboard();
    const refresh = window.setInterval(() => {
      if (forcedDegraded) return;
      fetchGuardianSnapshot().then((value) => { if (!cancelled) setGuardian(value); });
      setClock(Date.now());
    }, 60_000);
    const clock = window.setInterval(() => setClock(Date.now()), 30_000);
    return () => {
      cancelled = true;
      window.clearInterval(refresh);
      window.clearInterval(clock);
    };
  }, []);

  // Boot runtime checks are a real pass/total, so the gauge shows that
  // ratio rather than a health "score" with no defined derivation.
  const passedChecks = bootChecks?.filter((check) => check.passed).length ?? 0;
  const totalChecks = bootChecks?.length ?? 0;
  const recentGuardianHistory = guardian?.history.filter((item) => Date.now() / 1000 - item.timestamp <= 24 * 60 * 60) ?? [];
  const historyRecipeIds = new Set(recentGuardianHistory.map((item) => item.recipeId).filter(Boolean));
  const guardianEvents: GuardianEvent[] =
    recentGuardianHistory.map((item) => ({
      title: item.title,
      detail: item.detail || "No further detail recorded.",
      status: item.status,
      when: relativeTime(item.timestamp),
      recipeId: item.recipeId,
      action: item.action,
      verified: item.verified,
    })).concat(
      (guardian?.pending ?? [])
        .filter((item) => !historyRecipeIds.has(item.recipeId))
        .map((item) => ({
          title: item.title,
          detail: item.detail || "Guardian has a recommendation ready for review.",
          status: "warn" as const,
          when: "Needs attention",
          recipeId: item.recipeId,
          action: "recommended",
          verified: null,
        })),
    );

  const hasReadings = guardian !== null || bootChecks !== null || recovery !== null || updateChannel !== null || gpuName !== null || storageFree !== null;
  const healthGood = bootChecks === null ? null : totalChecks > 0 && passedChecks === totalChecks;
  const guardianGood = guardian === null ? null : guardian.pendingCount === 0;
  const recoveryGood = recovery === null ? null : !recovery.quarantined_digest;
  const recoverySafeguards = recovery === null ? null : Number(recovery.has_rollback) + Number(!recovery.quarantined_digest);
  const healthLabel = !loaded ? "Checking…" : bootChecks === null ? "Unavailable" : totalChecks === 0 ? "Not reported" : `${passedChecks}/${totalChecks} passing`;
  const healthDetail = !loaded ? "Boot runtime checks are being read." : bootChecks === null ? "Boot health data is unavailable; open Diagnostics for recovery guidance." : healthGood ? "All boot checks are passing." : "Review the checks that need attention.";
  const recoveryLabel = !loaded ? "Checking…" : recovery === null ? "Unavailable" : recovery.quarantined_digest ? "Review needed" : recovery.has_rollback ? "Rollback ready" : "Protected";
  const recoveryDetail = !loaded ? "Recovery safeguards are being read." : recovery === null ? "Recovery data is unavailable." : `${recoverySafeguards} of 2 safeguards ready · ${recovery.has_rollback ? "a previous deployment is available" : "no rollback recorded"}.`;
  const guardianLabel = !loaded ? "Checking…" : guardian === null ? "Unavailable" : guardian.pendingCount === 0 ? "Healthy" : `${guardian.pendingCount} issue${guardian.pendingCount === 1 ? "" : "s"}`;
  const guardianDetail = !loaded ? "Guardian is checking the device." : guardian === null ? "Guardian data is unavailable; open This PC to retry." : guardian.pendingCount === 0 ? "No recommendations are waiting." : "Open Guardian to review recommendations.";
  const dashboardLabel = loaded && !hasReadings ? "Status unavailable" : loaded ? "System at a glance" : "Checking system";
  const dashboardDetail = loaded && !hasReadings ? "Live system data is unavailable. The Hub is still usable for navigation and local recovery guidance." : "Health, recovery, updates, and device status in one place.";

  return (
    <div className="home-page">
      <section className="home-overview" aria-label="Home overview">
        <div className={`home-hero ${hasReadings ? "home-hero-live" : "home-hero-muted"}`}><div><span className="home-eyebrow">KythOS command center</span><h1>Welcome back{userName ? `, ${userName}` : ""}</h1><p>{dashboardDetail}</p></div><div className="home-ready-chip"><span />{guardianGood === false || healthGood === false ? "Needs attention" : dashboardLabel}</div></div>
        <div className="home-card-grid">
          <HomeCard icon="✓" label="Guardian" value={guardianLabel} detail={guardianDetail} good={guardianGood} pendingLabel="PENDING" />
          <HomeCard icon="⌁" label="Boot health" value={healthLabel} detail={healthDetail} good={healthGood} pendingLabel="PENDING" pendingNote={bootChecks ? "Boot checks were reported." : "Boot checks are still pending."} />
          <HomeCard icon="↶" label="Recovery" value={recoveryLabel} detail={recoveryDetail} good={recoveryGood} pendingLabel="PENDING" meterValue={recoverySafeguards} />
          <HomeCard icon="◈" label="Update channel" value={!loaded ? "Checking…" : updateChannel ?? "Unavailable"} detail="The release stream this device follows." good={!loaded || updateChannel === null ? null : true} pendingLabel="PENDING" />
          <HomeCard icon="▣" label="Storage & graphics" value={!loaded ? "Checking…" : storageFree ?? gpuName ?? "Unavailable"} detail={`${gpuName ?? (loaded ? "Hardware data unavailable" : "Graphics not identified")} · hardware summary`} good={!loaded || (storageFree === null && gpuName === null) ? null : true} />
        </div>
        <div className="home-actions-card"><div><span className="home-eyebrow">System actions</span><h2>Keep this device healthy</h2><p>Open the system tools you need without leaving the Home overview.</p></div><div className="home-actions"><ActionButton label="Run health check" onClick={() => navigate("/this-pc?section=Guardian")} /><ActionButton label="Check updates" onClick={() => navigate("/updates")} /><ActionButton label="Open Repair" onClick={() => navigate("/this-pc?section=Repair")} /><ActionButton label="Open Hardware" onClick={() => navigate("/this-pc?section=Hardware")} /></div></div>
      </section>
      <div className="home-content-heading"><span className="home-eyebrow">Activity</span><h2>Your recent system activity</h2><p>Guardian history stays visible without opening another workspace.</p></div>
      <GuardianHistoryCard
        events={guardianEvents}
        pending={guardian?.pending}
        live={guardian !== null}
        onConfirm={async (recipeId) => {
          const result = await invokeGuardianExecute(recipeId);
          const next = await fetchGuardianSnapshot();
          if (next) setGuardian(next);
          return result;
        }}
        onDismiss={async (recipeId) => {
          const result = await dismissGuardianRecommendation(recipeId);
          const next = await fetchGuardianSnapshot();
          if (next) setGuardian(next);
          return result;
        }}
      />
    </div>
  );
}
