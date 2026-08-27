import { NavLink } from "react-router-dom";
import { IconHome, IconPlay, IconGrid, IconMonitor, IconTransfer } from "./icons";
import type { ComponentType, SVGProps } from "react";

// Same five destinations as PULSE_RAIL in the current Qt Hub
// (page_registry.py) — this is a reskin of that navigation model, not a
// new one, so a page key still means the same thing on both sides during
// migration.
const destinations: { to: string; label: string; hint: string; Icon: ComponentType<SVGProps<SVGSVGElement>> }[] = [
  { to: "/", label: "Home", hint: "Health and the next step", Icon: IconHome },
  { to: "/play", label: "Play", hint: "Games, boost, controllers", Icon: IconPlay },
  { to: "/apps", label: "Apps", hint: "Discover and work setup", Icon: IconGrid },
  { to: "/this-pc", label: "This PC", hint: "Health, updates, hardware", Icon: IconMonitor },
  { to: "/move-in", label: "Move In", hint: "Files, saves, workflows", Icon: IconTransfer },
];

export function Sidebar() {
  return (
    <aside
      className="glass"
      style={{
        width: 244,
        margin: 16,
        marginRight: 0,
        display: "flex",
        flexDirection: "column",
        padding: "22px 14px",
        flexShrink: 0,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 12, padding: "2px 10px 26px" }}>
        <div className="icon-badge icon-badge-sm" style={{ borderRadius: 10 }}>
          <div style={{ width: 14, height: 14, borderRadius: 4, background: "#04101c" }} />
        </div>
        <span style={{ fontWeight: 800, letterSpacing: -0.3, fontSize: 15 }}>Kyth Hub</span>
      </div>

      <nav style={{ display: "flex", flexDirection: "column", gap: 4 }}>
        {destinations.map(({ to, label, hint, Icon }) => (
          <NavLink
            key={to}
            to={to}
            end={to === "/"}
            style={({ isActive }) => ({
              display: "flex",
              alignItems: "center",
              gap: 12,
              padding: "9px 10px",
              borderRadius: 14,
              textDecoration: "none",
              color: isActive ? "var(--text)" : "var(--text-muted)",
              background: isActive ? "rgba(43, 107, 255, 0.14)" : "transparent",
              transition: "background 0.15s ease, color 0.15s ease",
            })}
          >
            {({ isActive }) => (
              <>
                <span
                  className={`icon-badge icon-badge-sm ${isActive ? "" : "icon-badge-muted"}`}
                  style={{ borderRadius: 10 }}
                >
                  <Icon width={16} height={16} />
                </span>
                <span style={{ display: "flex", flexDirection: "column" }}>
                  <span style={{ fontWeight: isActive ? 700 : 600, fontSize: 13 }}>{label}</span>
                  <span style={{ fontSize: 10.5, opacity: 0.75, fontWeight: 500 }}>{hint}</span>
                </span>
              </>
            )}
          </NavLink>
        ))}
      </nav>

      <div style={{ flex: 1 }} />

      <div
        className="glass"
        style={{
          padding: 14,
          background: "linear-gradient(160deg, rgba(43,107,255,0.2), rgba(124,58,237,0.14))",
          boxShadow: "none",
        }}
      >
        <p className="card-title" style={{ fontSize: 13 }}>
          Everyday
        </p>
        <p className="card-copy" style={{ fontSize: 11.5, marginTop: 4 }}>
          Switch focus to Gaming from Home.
        </p>
      </div>
    </aside>
  );
}
