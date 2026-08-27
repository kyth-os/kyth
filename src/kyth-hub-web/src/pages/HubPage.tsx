import { useState } from "react";
import type { HubSection } from "../data/hubSections";
import { HubTabs } from "../components/HubTabs";
import { SectionPreviewCard } from "../components/SectionPreviewCard";

// Shared shell for the four Pulse-rail destinations (Play/Apps/This
// PC/Move In) — a tab row over that destination's real section list, plus
// a preview card for whichever section is selected. Play/Apps/ThisPc/
// MoveIn.tsx each just supply their own section array; see
// data/hubSections.ts for where those come from.
export function HubPage({ sections }: { sections: HubSection[] }) {
  const [activeKey, setActiveKey] = useState(sections[0].key);
  const active = sections.find((s) => s.key === activeKey) ?? sections[0];

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <HubTabs sections={sections} activeKey={activeKey} onSelect={setActiveKey} />
      <SectionPreviewCard section={active} />
    </div>
  );
}
