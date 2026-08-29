import { useNavigate } from "react-router-dom";
import { IconShield } from "./icons";

// `name` null means the identity read gave us nothing (not in the Tauri
// shell, or no GECOS/login name) — greet without a name rather than
// falling back to a placeholder person, which is what the hardcoded
// name="Mark" here used to do to every user. `pendingCount` null means
// Guardian hasn't answered yet, which reads differently from "Guardian
// answered and found nothing" and must not be rendered as the latter.
export function HeroCard({
  name,
  pendingCount,
}: {
  name: string | null;
  pendingCount: number | null;
}) {
  const summary =
    pendingCount === null
      ? "Checking with Guardian\u2026"
      : pendingCount === 0
        ? "Guardian's last check found nothing to fix."
        : `Guardian has ${pendingCount} suggestion${pendingCount === 1 ? "" : "s"} waiting for you.`;

  const navigate = useNavigate();

  return (
    <div className="glass dashboard-card hero-card">
      {/* Abstract gradient orb — stands in for the moodboard's photo hero
          without pretending to be a real render; pure CSS, no asset. */}
      <div
        className="hero-orb"
      />
      <div
        className="hero-wash"
      />
      <div style={{ position: "relative", zIndex: 1 }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12 }}>
          <span className="hero-status">
            <IconShield width={14} height={14} strokeWidth={2.2} />
            {pendingCount === null ? "Checking protection" : pendingCount === 0 ? "Protected" : "Review needed"}
          </span>
          <span className="card-copy" style={{ fontSize: 10, letterSpacing: 1, textTransform: "uppercase" }}>KythOS</span>
        </div>
        <p className="card-copy">Welcome back{name ? "," : ""}</p>
        {name && (
          <h2 style={{ margin: "4px 0 0", fontSize: 26, fontWeight: 800, letterSpacing: -0.5 }}>{name}</h2>
        )}
        <p className="card-copy" style={{ marginTop: 8, maxWidth: 260 }}>
          {summary}
        </p>
      </div>
      <button
        className="btn btn-primary"
        style={{ position: "relative", zIndex: 1, alignSelf: "flex-start" }}
        onClick={() => navigate("/this-pc?section=Guardian")}
      >
        Open Guardian
      </button>
    </div>
  );
}
