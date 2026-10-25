import { NavLink } from "react-router-dom";
import { IconHome, IconPlay, IconGrid, IconLock, IconMonitor, IconRefresh, IconShield, IconTerminal, IconTransfer } from "./icons";
import type { ComponentType, SVGProps } from "react";
import { DESTINATIONS } from "../data/destinations";

// The web Hub's left rail. Updates is deliberately last: it is a global,
// high-value action, but should stay out of the way of the everyday workflow.
// The route manifest is the single navigation model, so a page key has one
// meaning across the sidebar, deep-link resolver, and packaging metadata:
// the workspace entries are derived from DESTINATIONS (hubRoutes.json)
// rather than restating routes here — a manifest destination now appears
// in the rail automatically. Home and Dev Tools are shell-only routes
// with no manifest destination, so they are spliced in at their
// established positions around the derived entries. Presentation (hint +
// icon) stays a per-destination map in this file; routing does not.
const DESTINATION_PRESENTATION: Record<string, { hint: string; Icon: ComponentType<SVGProps<SVGSVGElement>> }> = {
  Play: { hint: "Games, boost, controllers", Icon: IconPlay },
  Apps: { hint: "Discover and work setup", Icon: IconGrid },
  "This PC": { hint: "Health, hardware, repair", Icon: IconMonitor },
  "Move In": { hint: "Files, saves, workflows", Icon: IconTransfer },
  VPN: { hint: "Secure work connections", Icon: IconLock },
  Updates: { hint: "System updates and rollback", Icon: IconRefresh },
};

const workspaceDestinations = DESTINATIONS.map(({ key, route }) => {
  const presentation = DESTINATION_PRESENTATION[key];
  if (!presentation) console.error(`Hub destination "${key}" has no sidebar presentation entry; using the fallback icon.`);
  return { to: route, label: key, hint: presentation?.hint ?? "", Icon: presentation?.Icon ?? IconGrid };
});

const destinations: { to: string; label: string; hint: string; Icon: ComponentType<SVGProps<SVGSVGElement>> }[] = [
  { to: "/", label: "Home", hint: "Health and the next step", Icon: IconHome },
  ...workspaceDestinations.slice(0, 2),
  { to: "/dev-tools", label: "Dev Tools", hint: "AI dev box, editors, agents", Icon: IconTerminal },
  ...workspaceDestinations.slice(2),
];

export function Sidebar() {
  return (
    <aside className="glass sidebar-shell" aria-label="Kyth Hub navigation">
      <div className="sidebar-brand">
        <div className="brand-mark"><IconShield width={21} height={21} strokeWidth={2.2} /></div>
        <div>
          <div className="brand-name">Kyth Hub</div>
          <div className="brand-kicker">System protection</div>
        </div>
      </div>

      <div className="sidebar-section-label">Workspace</div>
      <nav className="sidebar-nav">
        {destinations.map(({ to, label, hint, Icon }) => (
          <NavLink
            key={to}
            to={to}
            end={to === "/"}
            className={({ isActive }) => `sidebar-link ${isActive ? "sidebar-link-active" : ""}`}
          >
            {({ isActive }) => (
              <>
                <span className={`icon-badge icon-badge-sm ${isActive ? "" : "icon-badge-muted"}`}>
                  <Icon width={16} height={16} />
                </span>
                <span style={{ display: "flex", flexDirection: "column", minWidth: 0 }}>
                  <span style={{ fontWeight: isActive ? 700 : 600, fontSize: 13 }}>{label}</span>
                  <span style={{ fontSize: 10.5, opacity: 0.75, fontWeight: 500 }}>{hint}</span>
                </span>
              </>
            )}
          </NavLink>
        ))}
      </nav>

      <div style={{ flex: 1 }} />

      <div className="sidebar-status">
        <div className="sidebar-status-row">Kyth Hub</div>
        <p className="card-copy" style={{ fontSize: 11.5, marginTop: 6 }}>
          Your system tools and protection checks live here.
        </p>
      </div>
    </aside>
  );
}
