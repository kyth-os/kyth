import type { ComponentType } from "react";
import { useSearchParams } from "react-router-dom";
import type { HubSection } from "../data/hubSections";
import { HubTabs } from "../components/HubTabs";

// Shared shell for the four Pulse-rail destinations (Play/Apps/This
// PC/Move In) — a tab row over that destination's real section list, plus
// content for whichever section is selected. Every section key has a
// component in `sectionContent`; the null branch below is a safety net for
// a key added to hubSections.ts without one, which
// tests/test_kyth_hub_web_actions.py fails on rather than shipping.
//
// The active tab lives in ?section= rather than useState so that
// `kyth-welcome-launch --page Guardian` can land on it (deepLink.ts builds
// those URLs). Deliberately no state mirror and no effect syncing one to
// the other — a mount-time effect would clobber the incoming deep link.
export function HubPage({
  sections,
  sectionContent,
}: {
  sections: HubSection[];
  sectionContent: Record<string, ComponentType<{ section: HubSection }>>;
}) {
  const [searchParams, setSearchParams] = useSearchParams();
  const requested = searchParams.get("section");
  const active = sections.find((s) => s.key === requested) ?? sections[0];
  const Content = sectionContent[active.key];

  // replace, not push: tabbing within a destination shouldn't stack up
  // history entries the back button then has to walk out of.
  const onSelect = (key: string) => setSearchParams({ section: key }, { replace: true });

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <HubTabs sections={sections} activeKey={active.key} onSelect={onSelect} />
      {Content ? <Content section={active} /> : null}
    </div>
  );
}
