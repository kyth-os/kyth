import { useState, type ComponentType } from "react";
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
export function HubPage({
  sections,
  customContent = {},
}: {
  sections: HubSection[];
  customContent?: Record<string, ComponentType<{ section: HubSection }>>;
}) {
  const [activeKey, setActiveKey] = useState(sections[0].key);
  const active = sections.find((s) => s.key === activeKey) ?? sections[0];
  const Custom = customContent[activeKey];

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <HubTabs sections={sections} activeKey={activeKey} onSelect={setActiveKey} />
      {Custom ? <Custom section={active} /> : <SectionPreviewCard section={active} />}
    </div>
  );
}
