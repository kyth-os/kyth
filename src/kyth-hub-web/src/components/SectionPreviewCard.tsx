import type { HubSection } from "../data/hubSections";

// One honest card per section rather than fabricated per-section data:
// title + icon + the real Qt Hub description (see hubSections.ts), and a
// plain "Preview" badge instead of pretending this reads live kyth_shared
// state. Same posture as pages/Placeholder.tsx, just organized under the
// real information architecture instead of one flat stand-in per
// destination.
export function SectionPreviewCard({ section }: { section: HubSection }) {
  return (
    <div className="glass" style={{ padding: 28 }}>
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 16 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
          <span className="icon-badge" style={{ width: 52, height: 52 }}>
            <section.Icon width={24} height={24} stroke="#04101c" />
          </span>
          <div>
            <p className="card-title" style={{ fontSize: 18 }}>
              {section.title}
            </p>
            <p className="card-copy" style={{ marginTop: 6, maxWidth: 460 }}>
              {section.description}
            </p>
          </div>
        </div>
        <span className="pill pill-dim" style={{ flexShrink: 0 }}>
          Preview
        </span>
      </div>
      <p className="card-copy" style={{ marginTop: 20, fontSize: 12 }}>
        Not wired to live system data in the web prototype yet — this section exists and works in the current Qt Hub today.
      </p>
    </div>
  );
}
