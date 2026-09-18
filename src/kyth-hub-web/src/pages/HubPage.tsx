import type { ComponentType } from "react";
import { useSearchParams } from "react-router-dom";
import type { HubSection } from "../data/hubSections";
import { HubTabs } from "../components/HubTabs";

// Shared shell for the Hub destinations — a tab row over that destination's
// real section list, plus
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
  showTabs = true,
  defaultToFirstSection = false,
}: {
  sections: HubSection[];
  sectionContent: Record<string, ComponentType<{ section: HubSection }>>;
  showTabs?: boolean;
  /**
   * Overview destinations stay lightweight until the user selects a detailed
   * workspace.  Single-workspace pages such as Updates and VPN opt in so
   * their only control surface remains visible without a tab click.
   */
  defaultToFirstSection?: boolean;
}) {
  const [searchParams, setSearchParams] = useSearchParams();
  const requested = searchParams.get("section");
  // An explicit but unknown ?section= (stale bookmark, renamed section)
  // counts as a request so it falls back to the first section with a
  // notice instead of a blank content area. With no request at all, the
  // defaultToFirstSection opt-in still decides between the first section
  // and nothing.
  const active = sections.find((s) => s.key === requested)
    ?? (requested !== null || defaultToFirstSection ? sections[0] : null);
  const unknownSection = requested !== null && active?.key !== requested;
  const Content = active ? sectionContent[active.key] : null;

  // replace, not push: tabbing within a destination shouldn't stack up
  // history entries the back button then has to walk out of.
  const onSelect = (key: string) => setSearchParams({ section: key }, { replace: true });

  return (
    <div className="page-content" style={{ display: "flex", flexDirection: "column", gap: 18 }}>
      {showTabs && <HubTabs sections={sections} activeKey={active?.key ?? null} onSelect={onSelect} />}
      {unknownSection && (
        <p className="card-copy" role="status" style={{ opacity: 0.72 }}>
          Unknown section “{requested}” — showing {active ? `“${active.key}”` : "nothing"} instead.
        </p>
      )}
      {Content && active ? <Content section={active} /> : null}
    </div>
  );
}
