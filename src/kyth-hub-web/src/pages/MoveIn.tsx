import { HubPage } from "./HubPage";
import { MOVE_IN_SECTIONS } from "../data/hubSections";
import { VpnSection } from "../components/VpnSection";
import { NetworkSharesSection } from "../components/NetworkSharesSection";
import { CloudStorageSection } from "../components/CloudStorageSection";

export function MoveIn() {
  return (
    <HubPage
      sections={MOVE_IN_SECTIONS}
      customContent={{ VPN: VpnSection, "Network Shares": NetworkSharesSection, "Cloud Storage": CloudStorageSection }}
    />
  );
}
