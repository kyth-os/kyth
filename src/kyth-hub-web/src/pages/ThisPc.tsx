import { HubPage } from "./HubPage";
import { THIS_PC_SECTIONS } from "../data/hubSections";
import { UpdatesSection } from "../components/UpdatesSection";
import { GuardianSection } from "../components/GuardianSection";
import { HardwareSection } from "../components/HardwareSection";

export function ThisPc() {
  return (
    <HubPage
      sections={THIS_PC_SECTIONS}
      customContent={{ Update: UpdatesSection, Guardian: GuardianSection, Hardware: HardwareSection }}
    />
  );
}
