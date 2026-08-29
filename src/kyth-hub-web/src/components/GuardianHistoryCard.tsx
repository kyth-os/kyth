import type { GuardianEvent } from "../data/dashboardTypes";

const dot: Record<string, string> = {
  ok: "var(--status-ok)",
  warn: "var(--status-warn)",
  error: "var(--status-error)",
};

// `events` is required and never defaults to a fixture: a failed or
// not-yet-resolved Guardian read must render the empty state below, not
// four fabricated events presented as this machine's health history.
// `live` toggles the badge; the events come from guardian_snapshot.
export function GuardianHistoryCard({
  events,
  live = false,
}: {
  events: GuardianEvent[];
  live?: boolean;
}) {
  return (
    <div className="glass dashboard-card activity-card" style={{ padding: 20 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <p className="card-title">Guardian activity</p>
          {live && <span className="pill pill-ok">Live</span>}
        </div>
        <span className="card-copy" style={{ fontSize: 11.5 }}>
          {live ? "Most recent" : "Last 4 days"}
        </span>
      </div>
      <div style={{ marginTop: 14, display: "flex", flexDirection: "column", gap: 2 }}>
        {events.length === 0 && (
          <p className="card-copy" style={{ padding: "10px 4px" }}>
            No Guardian activity recorded yet.
          </p>
        )}
        {events.map((event, i) => (
          <div
            key={`${event.title}-${i}`}
            style={{
              display: "flex",
              alignItems: "center",
              gap: 12,
              padding: "10px 4px",
              borderBottom: "1px solid var(--hairline)",
            }}
          >
            <span
              style={{
                width: 8,
                height: 8,
                borderRadius: "50%",
                background: dot[event.status],
                boxShadow: `0 0 0 4px color-mix(in srgb, ${dot[event.status]} 18%, transparent)`,
                flexShrink: 0,
              }}
            />
            <div style={{ flex: 1, minWidth: 0 }}>
              <p style={{ margin: 0, fontSize: 13, fontWeight: 600 }}>{event.title}</p>
              <p className="card-copy" style={{ fontSize: 11.5 }}>
                {event.detail}
              </p>
            </div>
            <span className="card-copy" style={{ fontSize: 11, flexShrink: 0 }}>
              {event.when}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
