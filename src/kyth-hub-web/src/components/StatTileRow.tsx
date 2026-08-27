import type { ComponentType, SVGProps } from "react";
import type { StatTile } from "../data/mockDashboard";
import { IconShield, IconRefresh, IconDatabase, IconChip } from "./icons";

const toneClass: Record<NonNullable<StatTile["deltaTone"]>, string> = {
  ok: "pill-ok",
  warn: "pill-warn",
  error: "pill-error",
};

// One icon per stat identity (Guardian/channel/storage/GPU), not one hue
// per tile — the gradient badge is brand chrome, not a categorical
// encoding, so every tile gets the same accent gradient and the icon
// glyph (not color) is what tells them apart.
const iconFor: Record<string, ComponentType<SVGProps<SVGSVGElement>>> = {
  Guardian: IconShield,
  "Update Channel": IconRefresh,
  "Storage Free": IconDatabase,
  GPU: IconChip,
};

export function StatTileRow({ tiles }: { tiles: StatTile[] }) {
  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 16 }}>
      {tiles.map((tile) => {
        const Icon = iconFor[tile.label] ?? IconShield;
        return (
          <div
            key={tile.label}
            className="glass"
            style={{ padding: "18px 20px", display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12 }}
          >
            <div style={{ minWidth: 0 }}>
              <p className="card-copy" style={{ fontSize: 11.5, textTransform: "uppercase", letterSpacing: 0.6 }}>
                {tile.label}
              </p>
              <div style={{ display: "flex", alignItems: "baseline", gap: 8, marginTop: 6 }}>
                <span style={{ fontSize: 19, fontWeight: 800, letterSpacing: -0.3 }}>{tile.value}</span>
              </div>
              {tile.delta && (
                <span className={`pill ${toneClass[tile.deltaTone ?? "ok"]}`} style={{ display: "inline-block", marginTop: 8 }}>
                  {tile.delta}
                </span>
              )}
            </div>
            <span className="icon-badge">
              <Icon width={20} height={20} stroke="#04101c" />
            </span>
          </div>
        );
      })}
    </div>
  );
}
