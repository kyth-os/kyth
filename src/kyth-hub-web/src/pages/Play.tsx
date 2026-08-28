import { HubPage } from "./HubPage";
import { PLAY_SECTIONS } from "../data/hubSections";
import { ControllersSection } from "../components/ControllersSection";
import { GamingSection } from "../components/GamingSection";
import { PerformanceSection } from "../components/PerformanceSection";
import { CompatibilitySection } from "../components/CompatibilitySection";

export function Play() {
  return (
    <HubPage
      sections={PLAY_SECTIONS}
      sectionContent={{
        Controllers: ControllersSection,
        Gaming: GamingSection,
        Performance: PerformanceSection,
        Compatibility: CompatibilitySection,
      }}
    />
  );
}
