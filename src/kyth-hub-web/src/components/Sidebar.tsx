import { NavLink } from "react-router-dom";
import { IconHome, IconPlay, IconGrid, IconMonitor, IconRefresh, IconShield, IconTransfer } from "./icons";
import type { ComponentType, SVGProps } from "react";

// The web Hub's left rail. Updates is deliberately last: it is a global,
// high-value action, but should stay out of the way of the everyday workflow.
// (page_registry.py) — this is a reskin of that navigation model, not a
// new one, so a page key still means the same thing on both sides during
// migration.
const destinations: { to: string; label: string; hint: string; Icon: ComponentType<SVGProps<SVGSVGElement>> }[] = [
  { to: "/", label: "Home", hint: "Health and the next step", Icon: IconHome },
  { to: "/play", label: "Play", hint: "Games, boost, controllers", Icon: IconPlay },
  { to: "/apps", label: "Apps", hint: "Discover and work setup", Icon: IconGrid },
  { to: "/this-pc", label: "This PC", hint: "Health, hardware, repair", Icon: IconMonitor },
  { to: "/move-in", label: "Move In", hint: "Files, saves, workflows", Icon: IconTransfer },
  { to: "/updates", label: "Updates", hint: "System updates and rollback", Icon: IconRefresh },
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
        <div className="sidebar-status-row"><span className="status-dot" /> Kyth Hub is ready</div>
        <p className="card-copy" style={{ fontSize: 11.5, marginTop: 6 }}>
          Your system tools and protection checks live here.
        </p>
      </div>
    </aside>
  );
}
