import { useEffect, useState } from "react";
import { statTiles, type StatTile, type GuardianEvent } from "../data/mockDashboard";
import { StatTileRow } from "../components/StatTileRow";
import { HeroCard } from "../components/HeroCard";
import { GaugeCard } from "../components/GaugeCard";
import { PerformanceChart } from "../components/PerformanceChart";
import { SessionsChart } from "../components/SessionsChart";
import { GuardianHistoryCard } from "../components/GuardianHistoryCard";
import {
  fetchGpuName,
  fetchGuardianSnapshot,
  fetchStorageFree,
  fetchUpdateChannel,
  relativeTime,
  type GuardianSnapshot,
} from "../services/liveData";

// Every stat tile except System health/Stability score now has a real,
// cheap backend read behind it (see services/liveData.ts) — those two
// gauges and the performance/session charts would need either a live
// Guardian probe sweep (too heavy to run on every dashboard load) or
// telemetry plumbing that doesn't exist yet, so those stay on the mock
// fixtures from mockDashboard.ts until there's a real source for them.
export function Dashboard() {
  const [guardian, setGuardian] = useState<GuardianSnapshot | null>(null);
  const [updateChannel, setUpdateChannel] = useState<string | null>(null);
  const [gpuName, setGpuName] = useState<string | null>(null);
  const [storageFree, setStorageFree] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchGuardianSnapshot().then((snapshot) => {
      if (!cancelled) setGuardian(snapshot);
    });
    fetchUpdateChannel().then((channel) => {
      if (!cancelled) setUpdateChannel(channel);
    });
    fetchGpuName().then((name) => {
      if (!cancelled) setGpuName(name);
    });
    fetchStorageFree().then((free) => {
      if (!cancelled) setStorageFree(free);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const tiles: StatTile[] = statTiles.map((tile) => {
    if (tile.label === "Guardian" && guardian) {
      const n = guardian.pendingCount;
      return {
        ...tile,
        value: n === 0 ? "Healthy" : `${n} issue${n === 1 ? "" : "s"}`,
        delta: n === 0 ? "0 issues" : `${n} pending`,
        deltaTone: n === 0 ? "ok" : "warn",
      };
    }
    if (tile.label === "Update Channel" && updateChannel) {
      return { ...tile, value: updateChannel, delta: undefined, deltaTone: undefined };
    }
    if (tile.label === "GPU" && gpuName) {
      return { ...tile, value: gpuName, delta: undefined, deltaTone: undefined };
    }
    if (tile.label === "Storage Free" && storageFree) {
      return { ...tile, value: storageFree, delta: undefined, deltaTone: undefined };
    }
    return tile;
  });

  const guardianEvents: GuardianEvent[] | undefined = guardian?.history.map((item) => ({
    title: item.title,
    detail: item.detail || "No further detail recorded.",
    status: item.status,
    when: relativeTime(item.timestamp),
  }));

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16, paddingBottom: 24 }}>
      <StatTileRow tiles={tiles} />

      <div style={{ display: "grid", gridTemplateColumns: "1.4fr 1fr 1fr", gap: 16 }}>
        <HeroCard name="Mark" />
        <GaugeCard
          gaugeId="health"
          title="System health"
          subtitle="From Guardian's last check"
          value={95}
          displayValue="95"
          unitLabel="Based on active checks"
        />
        <GaugeCard
          gaugeId="stability"
          title="Stability score"
          subtitle="Rollback + boot health"
          value={9.3}
          max={10}
          displayValue="9.3"
          unitLabel="Total score"
        />
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1.4fr 1fr", gap: 16, minHeight: 300 }}>
        <PerformanceChart />
        <SessionsChart />
      </div>

      <GuardianHistoryCard events={guardianEvents} live={guardian !== null} />
    </div>
  );
}
