import { HubPage } from "./HubPage";
import { APPS_SECTIONS } from "../data/hubSections";
import { AppStoreSection } from "../components/AppStoreSection";
import { WorkSetupSection } from "../components/WorkSetupSection";

// The Apps destination is the software center up front: the App Store
// workspace on top, Work Setup below it — no status-card overview, no
// start-here actions, no tab switcher. Both workspaces always render in
// manifest order, so an incoming ?section= deep link scrolls (HubPage)
// instead of tab-switching.
export function Apps() {
  return (
    <div className="apps-page">
      <div className="apps-hero apps-hero-live"><div><span className="apps-eyebrow">Software center</span><h1>Make this desktop yours</h1><p>Find trusted apps, keep them current, and set up the tools you use every day.</p></div><div className="apps-ready-chip"><span />Ready to explore</div></div>
      <HubPage
        sections={APPS_SECTIONS}
        sectionContent={{
          "App Store": AppStoreSection,
          "Work Setup": WorkSetupSection,
        }}
        showTabs={false}
        stacked
      />
    </div>
  );
}
