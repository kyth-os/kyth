import { HubPage } from "./HubPage";
import { APPS_SECTIONS } from "../data/hubSections";

export function Apps() {
  return <HubPage sections={APPS_SECTIONS} />;
}
