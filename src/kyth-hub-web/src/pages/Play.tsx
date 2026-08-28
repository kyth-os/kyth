import { HubPage } from "./HubPage";
import { PLAY_SECTIONS } from "../data/hubSections";
import { ControllersSection } from "../components/ControllersSection";

export function Play() {
  return <HubPage sections={PLAY_SECTIONS} customContent={{ Controllers: ControllersSection }} />;
}
