import type { ReactNode } from "react";
import type { HubSection } from "../data/hubSections";

// Shared shell for every HubPage section that has real content behind it
// (see HubPage.tsx's sectionContent) — icon/title/description header plus a
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
    <div className="glass section-card">
      <div className="section-header" style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 16 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
          <span className="icon-badge section-icon">
            <section.Icon width={24} height={24} stroke="#04101c" />
          </span>
          <div>
            <p className="card-title section-heading">
              {section.title}
            </p>
            <p className="card-copy" style={{ marginTop: 6, maxWidth: 460 }}>
              {section.description}
            </p>
          </div>
        </div>
        <span className={`pill section-status ${live ? "pill-ok" : "pill-dim"}`}>
          {live ? "Live" : "Preview"}
        </span>
      </div>
      <div className="section-body">{children}</div>
    </div>
  );
}

/** Standard "why is this empty" note for a section whose reads came back
 * with nothing. The two cases are genuinely different and worth telling
 * apart: the fetch resolved and there's nothing on disk yet, versus the
 * fetch never happened because this isn't running inside the Hub shell. */
export function SectionFallbackNote({ loaded }: { loaded: boolean }) {
  return (
    <div className="empty-state">
      <span className="empty-state-mark">{loaded ? "·" : "…"}</span>
      <div>
        <p className="card-title" style={{ fontSize: 13 }}>{loaded ? "No reading yet" : "Reading system status"}</p>
        <p className="card-copy" style={{ marginTop: 3, fontSize: 12 }}>
          {loaded
            ? "kyth-probe.service fills this in on a real KythOS install."
            : "The Hub is checking this device now."}
        </p>
      </div>
    </div>
  );
}
