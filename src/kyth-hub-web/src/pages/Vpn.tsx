import { VpnSection } from "../components/VpnSection";
import { VPN_SECTIONS } from "../data/hubSections";
import { HubPage } from "./HubPage";

export function Vpn() {
  return (
    <div className="vpn-page">
      <div className="this-pc-controls-heading">
        <div>
          <span className="this-pc-eyebrow">Secure connections</span>
          <h1>VPN</h1>
          <p>Connect to a work or private VPN and complete sign-in securely inside Kyth Hub.</p>
        </div>
      </div>
      <HubPage
        sections={VPN_SECTIONS}
        showTabs={false}
        sectionContent={{ VPN: VpnSection }}
      />
    </div>
  );
}
