import { HubPage } from "./HubPage";
import { PLAY_SECTIONS } from "../data/hubSections";
import { ControllersSection } from "../components/ControllersSection";
import { GamingSection } from "../components/GamingSection";
import { PerformanceSection } from "../components/PerformanceSection";
import { CompatibilitySection } from "../components/CompatibilitySection";
import { PlayOverview } from "../components/PlayOverview";

export function Play() {
  return (
    <div className="play-page">
      <PlayOverview />
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
