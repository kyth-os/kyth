import { useRef, type KeyboardEvent } from "react";
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
  activeKey: string | null;
  onSelect: (key: string) => void;
}) {
  const navRef = useRef<HTMLDivElement>(null);

  // Roving-tabindex tablist: arrows move and activate (automatic
  // activation, matching the click-to-switch behavior), Home/End jump.
  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key !== "ArrowRight" && event.key !== "ArrowLeft" && event.key !== "Home" && event.key !== "End") return;
    const tabs = Array.from(navRef.current?.querySelectorAll<HTMLButtonElement>('[role="tab"]') ?? []);
    if (tabs.length === 0) return;
    const current = tabs.findIndex((tab) => tab.getAttribute("aria-selected") === "true");
    let next = current < 0 ? 0 : current;
    if (event.key === "ArrowRight") next = (current + 1) % tabs.length;
    else if (event.key === "ArrowLeft") next = (current - 1 + tabs.length) % tabs.length;
    else if (event.key === "Home") next = 0;
    else if (event.key === "End") next = tabs.length - 1;
    event.preventDefault();
    const target = tabs[next];
    if (target) {
      target.focus();
      onSelect(sections[next].key);
    }
  };

  return (
    <div className="tab-nav" role="tablist" aria-label="Sections" ref={navRef} onKeyDown={onKeyDown}>
      {sections.map((section) => {
        const isActive = section.key === activeKey;
        return (
          <button
            type="button"
            role="tab"
            aria-selected={isActive}
            tabIndex={isActive ? 0 : -1}
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
