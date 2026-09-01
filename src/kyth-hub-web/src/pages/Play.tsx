import { HubPage } from "./HubPage";
import { PLAY_SECTIONS } from "../data/hubSections";
import { ControllersSection } from "../components/ControllersSection";
import { GamingSection } from "../components/GamingSection";
import { PerformanceSection } from "../components/PerformanceSection";
import { CompatibilitySection } from "../components/CompatibilitySection";
import { PlayOverview } from "../components/PlayOverview";
import { PerformanceChart } from "../components/PerformanceChart";
import { SessionsChart } from "../components/SessionsChart";

export function Play() {
  return (
    <div className="play-page">
      <PlayOverview />
      <div className="play-content-heading"><span className="play-eyebrow">Gaming activity</span><h2>Your recent play</h2><p>Performance and gaming sessions from your recent telemetry.</p></div>
      <div className="chart-grid"><PerformanceChart /><SessionsChart /></div>
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
