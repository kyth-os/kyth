import { useEffect, useState } from "react";
import type { StatTile, GuardianEvent } from "../data/dashboardTypes";
import { StatTileRow } from "../components/StatTileRow";
import { HeroCard } from "../components/HeroCard";
import { GaugeCard } from "../components/GaugeCard";
import { PerformanceChart } from "../components/PerformanceChart";
import { SessionsChart } from "../components/SessionsChart";
import { GuardianHistoryCard } from "../components/GuardianHistoryCard";
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
const PENDING = "—";

export function Dashboard() {
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

  const guardianTile = (): StatTile => {
    if (!guardian) return { label: "Guardian", value: PENDING };
    const n = guardian.pendingCount;
    return {
      label: "Guardian",
      value: n === 0 ? "Healthy" : `${n} issue${n === 1 ? "" : "s"}`,
      delta: n === 0 ? "0 issues" : `${n} pending`,
      deltaTone: n === 0 ? "ok" : "warn",
    };
  };

  const tiles: StatTile[] = [
    guardianTile(),
    { label: "Update Channel", value: updateChannel ?? PENDING },
    { label: "Storage Free", value: storageFree ?? PENDING },
    { label: "GPU", value: gpuName ?? PENDING },
  ];

  // Boot runtime checks are a real pass/total, so the gauge shows that
  // ratio rather than a health "score" with no defined derivation.
  const passedChecks = bootChecks?.filter((check) => check.passed).length ?? 0;
  const totalChecks = bootChecks?.length ?? 0;
  const healthValue = bootChecks && totalChecks > 0 ? (passedChecks / totalChecks) * 100 : null;

  // Likewise a count of concrete safeguards that are actually in place,
  // not an invented 0-10 stability figure. Only genuine safety properties
  // count: recovery_status.rs sets `watcher_staged` to the same value as
  // `has_staged`, so a staged update is not a missing safeguard and must
  // not drag this figure down.
  const safeguards = recovery ? [recovery.has_rollback, !recovery.quarantined_digest] : null;
  const safeguardsReady = safeguards?.filter(Boolean).length ?? 0;

  const guardianEvents: GuardianEvent[] =
    guardian?.history.map((item) => ({
      title: item.title,
      detail: item.detail || "No further detail recorded.",
      status: item.status,
      when: relativeTime(item.timestamp),
    })) ?? [];

  return (
    <div className="page-content" style={{ display: "flex", flexDirection: "column", gap: 18 }}>
      <div className="dashboard-grid">
        <HeroCard name={userName} pendingCount={guardian ? guardian.pendingCount : null} />
        <GaugeCard
          gaugeId="health"
          title="Boot health"
          subtitle="Boot runtime checks"
          value={healthValue}
          displayValue={`${passedChecks}/${totalChecks}`}
          unitLabel={`${passedChecks} of ${totalChecks} checks passing`}
          pendingNote={bootChecks ? "No boot checks reported" : "Boot checks not read yet"}
        />
        <GaugeCard
          gaugeId="stability"
          title="Recovery safeguards"
          subtitle="Rollback + quarantine state"
          value={safeguards ? safeguardsReady : null}
          max={2}
          displayValue={`${safeguardsReady}/2`}
          unitLabel={`${safeguardsReady} of 2 safeguards ready`}
          pendingNote="Recovery status not read yet"
        />
      </div>

      <StatTileRow tiles={tiles} />

      <div className="chart-grid">
        <PerformanceChart />
        <SessionsChart />
      </div>

      <GuardianHistoryCard events={guardianEvents} live={guardian !== null} />
    </div>
  );
}
