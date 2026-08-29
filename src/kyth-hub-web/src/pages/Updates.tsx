import { UpdatesSection } from "../components/UpdatesSection";
import { UPDATES_SECTIONS } from "../data/hubSections";
import { HubPage } from "./HubPage";

export function Updates() {
  return (
    <HubPage
      sections={UPDATES_SECTIONS}
      showTabs={false}
      sectionContent={{
        Update: UpdatesSection,
      }}
    />
  );
}
