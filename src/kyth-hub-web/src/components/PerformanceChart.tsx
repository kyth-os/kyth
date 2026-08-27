import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { performanceSeries } from "../data/mockDashboard";

// Single series -> no legend needed (the card title names it); recessive
// dashed grid, thin 2px line, gradient fill anchored to the baseline,
// hover tooltip per the interaction guidance for line/area forms. Stroke
// and fill both draw from the same accent ramp used everywhere else on
// the dashboard for "magnitude," not a chart-only color.
export function PerformanceChart() {
  return (
    <div className="glass" style={{ padding: 20, height: "100%", display: "flex", flexDirection: "column" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
        <div>
          <p className="card-title">Performance</p>
          <p className="card-copy" style={{ marginTop: 2 }}>
            Average FPS captured by kyth-telem, last 7 days
          </p>
        </div>
        <span className="pill pill-ok">+18% vs last week</span>
      </div>
      <div style={{ flex: 1, marginTop: 12, minHeight: 220 }}>
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={performanceSeries} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
            <defs>
              <linearGradient id="fpsStroke" x1="0" y1="0" x2="1" y2="0">
                <stop offset="0%" stopColor="var(--accent-start)" />
                <stop offset="100%" stopColor="var(--accent-end)" />
              </linearGradient>
              <linearGradient id="fpsFill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="var(--accent-end)" stopOpacity={0.38} />
                <stop offset="100%" stopColor="var(--accent-end)" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid stroke="var(--hairline)" strokeDasharray="3 6" vertical={false} />
            <XAxis dataKey="day" stroke="var(--text-faint)" fontSize={11} tickLine={false} axisLine={false} />
            <YAxis domain={["dataMin - 10", "dataMax + 10"]} stroke="var(--text-faint)" fontSize={11} tickLine={false} axisLine={false} width={40} />
            <Tooltip
              cursor={{ stroke: "var(--hairline-light)", strokeWidth: 1 }}
              contentStyle={{
                background: "var(--surface-raised)",
                border: "1px solid var(--hairline)",
                borderRadius: 10,
                fontSize: 12,
              }}
              labelStyle={{ color: "var(--text-muted)" }}
              formatter={(v: number) => [`${v} fps`, "Average"]}
            />
            <Area
              type="monotone"
              dataKey="fps"
              stroke="url(#fpsStroke)"
              strokeWidth={2.5}
              fill="url(#fpsFill)"
              activeDot={{ r: 4, strokeWidth: 0, fill: "var(--accent-end)" }}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
