import { HubPage } from "./HubPage";
import { MOVE_IN_SECTIONS } from "../data/hubSections";
import { VpnSection } from "../components/VpnSection";
import { NetworkSharesSection } from "../components/NetworkSharesSection";
import { CloudStorageSection } from "../components/CloudStorageSection";
import { MoveFilesSection } from "../components/MoveFilesSection";

export function MoveIn() {
  return (
    <HubPage
      sections={MOVE_IN_SECTIONS}
      sectionContent={{
        VPN: VpnSection,
        "Network Shares": NetworkSharesSection,
        "Cloud Storage": CloudStorageSection,
        "Move Files": MoveFilesSection,
      }}
    />
  );
}
