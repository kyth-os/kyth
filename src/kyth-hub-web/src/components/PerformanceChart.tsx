import { useEffect, useState } from "react";
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { fetchTelemetryRecent, type TelemetrySession } from "../services/liveData";
import { inTauriShell } from "../services/tauriEnv";

// Dashboard FPS chart — now live. When telemetry.db is absent (dev checkout, no kyth-telem runs)
// it shows Preview with no fake numbers. When data exists, it aggregates recent_sessions by day
// and shows a Live badge.
export function PerformanceChart() {
  const [sessions, setSessions] = useState<TelemetrySession[] | null>(null);
  const [loaded, setLoaded] = useState(false);
  useEffect(() => {
    let cancelled = false;
    fetchTelemetryRecent(15).then((rows) => {
      if (!cancelled) {
        setSessions(rows);
        setLoaded(true);
      }
    });
    return () => { cancelled = true; };
  }, []);

  const isLive = sessions !== null && sessions.length > 0;
  // Aggregate avg_fps by calendar day (last 7 days) — matches Python recent_sessions grouping.
  const data = (() => {
    if (!isLive || !sessions) return [];
    const byDay = new Map<string, { key: string; sum: number; count: number; day: string }>();
    for (const s of sessions) {
      if (s.avg_fps == null || s.started_at == null) continue;
      const d = new Date(s.started_at * 1000);
      const key = d.toISOString().slice(0, 10);
      const day = d.toLocaleDateString(undefined, { weekday: "short" });
      const cur = byDay.get(key) || { key, sum: 0, count: 0, day };
      cur.sum += s.avg_fps;
      cur.count += 1;
      byDay.set(key, cur);
    }
    return Array.from(byDay.values())
      .sort((a, b) => a.key.localeCompare(b.key))
      .slice(-7)
      .map((v) => ({ day: v.day, fps: Math.round(v.sum / v.count) }));
  })();

  const showLiveData = isLive && data.length > 0;

  return (
    <div className="glass dashboard-card chart-card" style={{ height: "100%", display: "flex", flexDirection: "column" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
        <div>
          <p className="card-title">Performance</p>
          <p className="card-copy" style={{ marginTop: 2 }}>Average FPS per day, last 7 days</p>
        </div>
        <span className={`pill ${showLiveData ? "pill-ok" : "pill-dim"}`}>{showLiveData ? "Live" : loaded ? "Preview" : "…"}</span>
      </div>
      <div style={{ flex: 1, marginTop: 12, minHeight: 220 }}>
        {showLiveData ? (
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
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
                contentStyle={{ background: "var(--surface-raised)", border: "1px solid var(--hairline)", borderRadius: 10, fontSize: 12 }}
                labelStyle={{ color: "var(--text-muted)" }}
                formatter={(v) => [`${typeof v === "number" ? v : 0} fps`, "Average"]}
              />
              <Area type="monotone" dataKey="fps" stroke="url(#fpsStroke)" strokeWidth={2.5} fill="url(#fpsFill)" activeDot={{ r: 4, strokeWidth: 0, fill: "var(--accent-end)" }} />
            </AreaChart>
          </ResponsiveContainer>
        ) : (
          <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", minHeight: 220 }}>
            <p className="card-copy" style={{ fontSize: 12 }}>
              {loaded
                ? inTauriShell()
                  ? "No sessions recorded yet — play a game and check back."
                  : "Not in Tauri shell — chart will show live FPS once installed."
                : "Loading…"}
            </p>
          </div>
        )}
      </div>
      {!showLiveData && loaded && (
        <p className="card-copy" style={{ marginTop: 12, fontSize: 11.5 }}>
          No telemetry sessions with FPS data are available yet.
        </p>
      )}
    </div>
  );
}
