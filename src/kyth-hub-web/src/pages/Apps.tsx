import { HubPage } from "./HubPage";
import { APPS_SECTIONS } from "../data/hubSections";
import { AppStoreSection } from "../components/AppStoreSection";

export function Apps() {
  return <HubPage sections={APPS_SECTIONS} customContent={{ "App Store": AppStoreSection }} />;
}
