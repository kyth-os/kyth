import type { HubSection } from "../data/hubSections";

// Pill tab row, wraps rather than scrolling — This PC has 11 sections
// (Qt's Guardian..Repair primary tabs + its "More" tab's NVIDIA..Feedback
// flattened into one row, see hubSections.ts), so wrapping is what keeps
// every section reachable without inventing a nested menu.
export function HubTabs({
  sections,
  activeKey,
  onSelect,
}: {
  sections: HubSection[];
  activeKey: string;
  onSelect: (key: string) => void;
}) {
  return (
    <div className="tab-nav">
      {sections.map((section) => {
        const isActive = section.key === activeKey;
        return (
          <button
            className={`tab-button ${isActive ? "tab-button-active" : ""}`}
            key={section.key}
            onClick={() => onSelect(section.key)}
          >
            <section.Icon width={15} height={15} />
            {section.title}
          </button>
        );
      })}
    </div>
  );
}
