import { HubPage } from "./HubPage";
import { APPS_SECTIONS } from "../data/hubSections";
import { AppStoreSection } from "../components/AppStoreSection";
import { WorkSetupSection } from "../components/WorkSetupSection";

export function Apps() {
  return (
    <HubPage
      sections={APPS_SECTIONS}
      sectionContent={{
        "App Store": AppStoreSection,
        "Work Setup": WorkSetupSection,
      }}
    />
  );
}
