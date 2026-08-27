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
    <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
      {sections.map((section) => {
        const isActive = section.key === activeKey;
        return (
          <button
            key={section.key}
            onClick={() => onSelect(section.key)}
            style={{
              display: "flex",
              alignItems: "center",
              gap: 8,
              padding: "8px 16px",
              borderRadius: "var(--radius-pill)",
              border: "1px solid",
              borderColor: isActive ? "transparent" : "var(--hairline)",
              background: isActive ? "var(--accent-gradient)" : "var(--card-gradient)",
              color: isActive ? "#04101c" : "var(--text-muted)",
              fontSize: 13,
              fontWeight: isActive ? 700 : 600,
              cursor: "pointer",
              transition: "border-color 0.15s ease, color 0.15s ease",
            }}
          >
            <section.Icon width={15} height={15} />
            {section.title}
          </button>
        );
      })}
    </div>
  );
}
