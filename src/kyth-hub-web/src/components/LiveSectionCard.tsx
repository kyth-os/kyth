import type { ReactNode } from "react";
import type { HubSection } from "../data/hubSections";

// Shared shell for every HubPage section that has real content behind it
// (see HubPage.tsx's customContent) — icon/title/description header plus a
// Live/Preview badge, with the body left to the caller. Factored out once
// UpdatesSection and ControllersSection turned out to be pixel-identical
// except for their data and body — new sections should use this rather
// than reintroducing a sixth copy of the header markup.
export function LiveSectionCard({
  section,
  live,
  children,
}: {
  section: HubSection;
  live: boolean;
  children: ReactNode;
}) {
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
        <span className={`pill ${live ? "pill-ok" : "pill-dim"}`} style={{ flexShrink: 0 }}>
          {live ? "Live" : "Preview"}
        </span>
      </div>
      {children}
    </div>
  );
}

/** Standard "why is this empty" note for a section with no live data yet —
 * distinguishes "the fetch resolved and there's genuinely nothing cached"
 * from "still on the always-mock prototype path", same distinction every
 * section's fallback copy already made individually. */
export function SectionFallbackNote({ loaded }: { loaded: boolean }) {
  return (
    <p className="card-copy" style={{ marginTop: 20, fontSize: 12 }}>
      {loaded
        ? "No probe data on disk yet — kyth-probe.service populates this on a real KythOS install."
        : "Not wired to live system data in the web prototype yet — this section exists and works in the current Qt Hub today."}
    </p>
  );
}
