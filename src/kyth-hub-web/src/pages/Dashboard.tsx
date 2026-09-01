import { useEffect, useState } from "react";
import type { GuardianEvent } from "../data/dashboardTypes";
import { PerformanceChart } from "../components/PerformanceChart";
import { SessionsChart } from "../components/SessionsChart";
import { GuardianHistoryCard } from "../components/GuardianHistoryCard";
import { ActionButton } from "../components/SectionActions";
import { useNavigate } from "react-router-dom";
import {
  fetchBootRuntimeChecks,
  fetchGpuName,
  fetchGuardianSnapshot,
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
function HomeCard({ icon, label, value, detail, good }: { icon: string; label: string; value: string; detail: string; good: boolean | null }) {
  const tone = good === null ? "home-card-muted" : good ? "home-card-ok" : "home-card-warn";
  return <article className={`home-card ${tone}`}><div className="home-card-top"><span className="home-card-icon" aria-hidden="true">{icon}</span><span className="home-card-label">{label}</span><span className="home-status-dot" /></div><strong className="home-card-value">{value}</strong><span className="home-card-detail">{detail}</span></article>;
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

  useEffect(() => {
    let cancelled = false;
    const set = <T,>(setter: (v: T) => void) => (value: T) => {
      if (!cancelled) setter(value);
    };
    fetchGuardianSnapshot().then(set(setGuardian));
    fetchUpdateChannel().then(set(setUpdateChannel));
    fetchGpuName().then(set(setGpuName));
    fetchStorageFree().then(set(setStorageFree));
    fetchUserName().then(set(setUserName));
    fetchBootRuntimeChecks().then(set(setBootChecks));
    fetchRecoveryStatus().then(set(setRecovery));
    return () => {
      cancelled = true;
    };
  }, []);

  // Boot runtime checks are a real pass/total, so the gauge shows that
  // ratio rather than a health "score" with no defined derivation.
  const passedChecks = bootChecks?.filter((check) => check.passed).length ?? 0;
  const totalChecks = bootChecks?.length ?? 0;
  const guardianEvents: GuardianEvent[] =
    guardian?.history.map((item) => ({
      title: item.title,
      detail: item.detail || "No further detail recorded.",
      status: item.status,
      when: relativeTime(item.timestamp),
    })) ?? [];

  const hasReadings = guardian !== null || bootChecks !== null || recovery !== null || updateChannel !== null || gpuName !== null || storageFree !== null;
  const healthGood = bootChecks === null ? null : totalChecks > 0 && passedChecks === totalChecks;
  const guardianGood = guardian === null ? null : guardian.pendingCount === 0;
  const recoveryGood = recovery === null ? null : !recovery.quarantined_digest;
  const healthLabel = bootChecks === null ? "Checking…" : totalChecks === 0 ? "Not reported" : `${passedChecks}/${totalChecks} passing`;
  const healthDetail = bootChecks === null ? "Boot runtime checks are being read." : healthGood ? "All boot checks are passing." : "Review the checks that need attention.";
  const recoveryLabel = recovery === null ? "Checking…" : recovery.quarantined_digest ? "Review needed" : recovery.has_rollback ? "Rollback ready" : "Protected";
  const recoveryDetail = recovery === null ? "Recovery safeguards are being read." : recovery.has_rollback ? "A previous deployment is available." : "No quarantined image is active.";
  const guardianLabel = guardian === null ? "Checking…" : guardian.pendingCount === 0 ? "Healthy" : `${guardian.pendingCount} issue${guardian.pendingCount === 1 ? "" : "s"}`;
  const guardianDetail = guardian === null ? "Guardian is checking the device." : guardian.pendingCount === 0 ? "No recommendations are waiting." : "Open Guardian to review recommendations.";

  return (
    <div className="home-page">
      <section className="home-overview" aria-label="Home overview">
        <div className={`home-hero ${hasReadings ? "home-hero-live" : "home-hero-muted"}`}><div><span className="home-eyebrow">KythOS command center</span><h1>Welcome back{userName ? `, ${userName}` : ""}</h1><p>Health, updates, apps, and everyday controls in one place.</p></div><div className="home-ready-chip"><span />{guardianGood === false || healthGood === false ? "Needs attention" : hasReadings ? "System at a glance" : "Checking system"}</div></div>
        <div className="home-card-grid">
          <HomeCard icon="✓" label="Guardian" value={guardianLabel} detail={guardianDetail} good={guardianGood} />
          <HomeCard icon="⌁" label="Boot health" value={healthLabel} detail={healthDetail} good={healthGood} />
          <HomeCard icon="↶" label="Recovery" value={recoveryLabel} detail={recoveryDetail} good={recoveryGood} />
          <HomeCard icon="◈" label="Update channel" value={updateChannel ?? "Checking…"} detail="The release stream this device follows." good={updateChannel === null ? null : true} />
          <HomeCard icon="▣" label="Storage & graphics" value={storageFree ?? "Checking…"} detail={`${gpuName ?? "Graphics not identified"} · hardware summary`} good={storageFree === null && gpuName === null ? null : true} />
        </div>
        <div className="home-actions-card"><div><span className="home-eyebrow">Quick actions</span><h2>What do you want to do?</h2><p>Jump directly to the part of Kyth Hub you need.</p></div><div className="home-actions"><ActionButton label="Run health check" onClick={() => navigate("/this-pc?section=Guardian")} /><ActionButton label="Check updates" onClick={() => navigate("/updates")} /><ActionButton label="Find apps" onClick={() => navigate("/apps")} /><ActionButton label="Start playing" onClick={() => navigate("/play")} /></div></div>
      </section>
      <div className="home-content-heading"><span className="home-eyebrow">Activity</span><h2>Your recent system activity</h2><p>Performance and Guardian history stay visible without opening another workspace.</p></div>
      <div className="chart-grid"><PerformanceChart /><SessionsChart /></div>
      <GuardianHistoryCard events={guardianEvents} live={guardian !== null} />
    </div>
  );
}
