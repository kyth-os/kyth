import { IconSearch, IconBell } from "./icons";

export function Topbar({ crumb }: { crumb: string }) {
  return (
    <header
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        padding: "22px 8px 18px",
      }}
    >
      <div>
        <p
          style={{
            margin: 0,
            fontSize: 11,
            color: "var(--text-faint)",
            fontWeight: 700,
            letterSpacing: 0.6,
            textTransform: "uppercase",
          }}
        >
          Kyth Hub / {crumb}
        </p>
        <h1 style={{ margin: "4px 0 0", fontSize: 22, fontWeight: 800, letterSpacing: -0.5 }}>{crumb}</h1>
      </div>

      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <div
          className="glass"
          style={{
            display: "flex",
            alignItems: "center",
            gap: 8,
            padding: "9px 14px",
            borderRadius: 12,
            width: 220,
            boxShadow: "none",
          }}
        >
          <IconSearch width={15} height={15} color="var(--text-faint)" />
          <input
            placeholder="Search settings…"
            style={{
              background: "transparent",
              border: "none",
              outline: "none",
              color: "var(--text)",
              fontSize: 13,
              width: "100%",
            }}
          />
        </div>
        <button
          className="glass"
          aria-label="Notifications"
          style={{
            width: 38,
            height: 38,
            display: "grid",
            placeItems: "center",
            cursor: "pointer",
            border: "1px solid var(--hairline)",
            boxShadow: "none",
            position: "relative",
          }}
        >
          <IconBell width={16} height={16} />
          <span
            style={{
              position: "absolute",
              top: 9,
              right: 10,
              width: 6,
              height: 6,
              borderRadius: "50%",
              background: "var(--accent-end)",
              boxShadow: "0 0 0 2px var(--surface-solid)",
            }}
          />
        </button>
      </div>
    </header>
  );
}
