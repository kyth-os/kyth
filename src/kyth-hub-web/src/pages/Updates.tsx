import { UpdatesSection } from "../components/UpdatesSection";
import { UPDATES_SECTIONS } from "../data/hubSections";
import { HubPage } from "./HubPage";
import { UpdatesOverview } from "../components/UpdatesOverview";

export function Updates() {
  return (
    <div className="updates-page">
      <UpdatesOverview />
      <div className="updates-controls-heading">
        <div>
          <span className="updates-eyebrow">Detailed update tools</span>
          <h2>Deployment details</h2>
          <p>Inspect raw status and use the full update workflow when you need more context.</p>
        </div>
      </div>
      <HubPage
        sections={UPDATES_SECTIONS}
        showTabs={false}
        sectionContent={{
          Update: UpdatesSection,
        }}
      />
    </div>
  );
}
