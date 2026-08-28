import type { ComponentType } from "react";
import { useSearchParams } from "react-router-dom";
import type { HubSection } from "../data/hubSections";
import { HubTabs } from "../components/HubTabs";
import { SectionPreviewCard } from "../components/SectionPreviewCard";

// Shared shell for the four Pulse-rail destinations (Play/Apps/This
// PC/Move In) — a tab row over that destination's real section list, plus
// content for whichever section is selected. Every section gets the
// generic preview card by default; a page can hand a real component for
// specific keys via `customContent` once that section has an actual
// backend behind it (see ThisPc.tsx's "Update" entry for the first one) —
// everything else stays on the honest "Preview" card from
// SectionPreviewCard.tsx.
//
// The active tab lives in ?section= rather than useState so that
// `kyth-welcome-launch --page Guardian` can land on it (deepLink.ts builds
// those URLs). Deliberately no state mirror and no effect syncing one to
// the other — a mount-time effect would clobber the incoming deep link.
export function HubPage({
  sections,
  customContent = {},
}: {
  sections: HubSection[];
  customContent?: Record<string, ComponentType<{ section: HubSection }>>;
}) {
  const [searchParams, setSearchParams] = useSearchParams();
  const requested = searchParams.get("section");
  const active = sections.find((s) => s.key === requested) ?? sections[0];
  const Custom = customContent[active.key];

  // replace, not push: tabbing within a destination shouldn't stack up
  // history entries the back button then has to walk out of.
  const onSelect = (key: string) => setSearchParams({ section: key }, { replace: true });

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <HubTabs sections={sections} activeKey={active.key} onSelect={onSelect} />
      {Custom ? <Custom section={active} /> : <SectionPreviewCard section={active} />}
    </div>
  );
}
