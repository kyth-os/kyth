import { lazy, Suspense, useState } from "react";
import { HubPage } from "./HubPage";
import { PLAY_SECTIONS } from "../data/hubSections";
import { ControllersSection } from "../components/ControllersSection";
import { GamingSection } from "../components/GamingSection";
import { PerformanceSection } from "../components/PerformanceSection";
import { CompatibilitySection } from "../components/CompatibilitySection";
import { PlayOverview } from "../components/PlayOverview";
import type { TelemetrySession } from "../services/liveData";

const PerformanceChart = lazy(() => import("../components/PerformanceChart").then(({ PerformanceChart: chart }) => ({ default: chart })));
const SessionsChart = lazy(() => import("../components/SessionsChart").then(({ SessionsChart: chart }) => ({ default: chart })));

export function Play() {
  const [sessions, setSessions] = useState<TelemetrySession[] | null>(null);
  const [showCharts, setShowCharts] = useState(false);

  return (
    <div className="play-page">
      <PlayOverview onTelemetryLoaded={setSessions} />
      <div className="play-content-heading"><span className="play-eyebrow">Gaming activity</span><h2>Your recent play</h2><p>Performance and gaming sessions from your recent telemetry.</p></div>
      {sessions && sessions.length > 0 ? (
        showCharts ? (
          <Suspense fallback={<div className="glass dashboard-card card-copy">Loading performance charts…</div>}>
            <div className="chart-grid"><PerformanceChart sessions={sessions} /><SessionsChart sessions={sessions} /></div>
          </Suspense>
        ) : (
          <div className="glass dashboard-card card-copy" style={{ padding: 20 }}>
            <p style={{ marginTop: 0 }}>Recent play telemetry is ready.</p>
            <button className="app-action-button app-action-secondary" onClick={() => setShowCharts(true)}>Show performance charts</button>
          </div>
        )
      ) : null}
      <div className="play-controls-heading">
        <div>
          <span className="play-eyebrow">Gaming controls</span>
          <h2>Detailed tools</h2>
          <p>Open a focused gaming workspace when you need deeper setup, tuning, or troubleshooting.</p>
        </div>
      </div>
      <HubPage
        sections={PLAY_SECTIONS}
        sectionContent={{
          Controllers: ControllersSection,
          Gaming: GamingSection,
          Performance: PerformanceSection,
          Compatibility: CompatibilitySection,
        }}
      />
    </div>
  );
}
