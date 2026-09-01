import { HubPage } from "./HubPage";
import { MOVE_IN_SECTIONS } from "../data/hubSections";
import { VpnSection } from "../components/VpnSection";
import { NetworkSharesSection } from "../components/NetworkSharesSection";
import { CloudStorageSection } from "../components/CloudStorageSection";
import { MoveFilesSection } from "../components/MoveFilesSection";
import { MoveInOverview } from "../components/MoveInOverview";

export function MoveIn() {
  return (
    <div className="move-in-page">
      <MoveInOverview />
      <div className="move-in-controls-heading">
        <div>
          <span className="move-in-eyebrow">More connections</span>
          <h2>Detailed migration tools</h2>
          <p>Open a focused workflow when you need to inspect drives, configure shares, or manage saved connections.</p>
        </div>
      </div>
      <HubPage
        sections={MOVE_IN_SECTIONS}
        sectionContent={{
          VPN: VpnSection,
          "Network Shares": NetworkSharesSection,
          "Cloud Storage": CloudStorageSection,
          "Move Files": MoveFilesSection,
        }}
      />
    </div>
  );
}
