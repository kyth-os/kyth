import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis } from "recharts";
import { sessionSeries } from "../data/mockDashboard";

// Single series bar form — one hue-family gradient (top-to-bottom, accent
// ramp), 2px surface gap reads naturally from bar spacing here since
// there's only one bar per category (no adjacent-segment gap needed).
// Rounded data-ends per the mark spec.
export function SessionsChart() {
  return (
    <div className="glass" style={{ padding: 20, height: "100%", display: "flex", flexDirection: "column" }}>
      <p className="card-title">Gaming sessions</p>
      <p className="card-copy" style={{ marginTop: 2 }}>
        Sessions per day, last 7 days
      </p>
      <div style={{ flex: 1, marginTop: 12, minHeight: 160 }}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={sessionSeries} margin={{ top: 8, right: 4, left: -20, bottom: 0 }}>
            <defs>
              <linearGradient id="sessionsFill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="var(--accent-end)" />
                <stop offset="100%" stopColor="var(--accent-start)" />
              </linearGradient>
            </defs>
            <XAxis dataKey="day" stroke="var(--text-faint)" fontSize={11} tickLine={false} axisLine={false} />
            <Tooltip
              cursor={{ fill: "var(--hairline)" }}
              contentStyle={{
                background: "var(--surface-raised)",
                border: "1px solid var(--hairline)",
                borderRadius: 10,
                fontSize: 12,
              }}
              labelStyle={{ color: "var(--text-muted)" }}
              formatter={(v: number) => [`${v} session${v === 1 ? "" : "s"}`, ""]}
            />
            <Bar dataKey="sessions" fill="url(#sessionsFill)" radius={[6, 6, 0, 0]} maxBarSize={28} />
          </BarChart>
        </ResponsiveContainer>
      </div>
      <div style={{ display: "flex", gap: 20, marginTop: 14 }}>
        {[
          { label: "This week", value: "20" },
          { label: "Avg length", value: "1h 42m" },
          { label: "Longest", value: "3h 05m" },
        ].map((s) => (
          <div key={s.label}>
            <p className="card-copy" style={{ fontSize: 11 }}>
              {s.label}
            </p>
            <p style={{ margin: "2px 0 0", fontSize: 14, fontWeight: 700 }}>{s.value}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
