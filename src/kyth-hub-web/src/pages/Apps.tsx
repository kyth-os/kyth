import { HubPage } from "./HubPage";
import { APPS_SECTIONS } from "../data/hubSections";
import { AppStoreSection } from "../components/AppStoreSection";
import { WorkSetupSection } from "../components/WorkSetupSection";
import { AppsOverview } from "../components/AppsOverview";

export function Apps() {
  return (
    <div className="apps-page">
      <AppsOverview />
      <div className="apps-controls-heading">
        <div>
          <span className="apps-eyebrow">Detailed app tools</span>
          <h2>Explore and configure</h2>
          <p>Open the focused workspace when you need the full catalog or work setup controls.</p>
        </div>
      </div>
      <HubPage
        sections={APPS_SECTIONS}
        sectionContent={{
          "App Store": AppStoreSection,
          "Work Setup": WorkSetupSection,
        }}
      />
    </div>
  );
}
