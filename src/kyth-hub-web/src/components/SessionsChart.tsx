import { useEffect, useState } from "react";
import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis } from "recharts";
import { fetchTelemetryRecent, type TelemetrySession } from "../services/liveData";
import { inTauriShell } from "../services/tauriEnv";

export function SessionsChart() {
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
  const data = (() => {
    if (!isLive || !sessions) return [];
    const byDay = new Map<string, { key: string; count: number; day: string }>();
    for (const s of sessions) {
      if (s.started_at == null) continue;
      const d = new Date(s.started_at * 1000);
      const key = d.toISOString().slice(0, 10);
      const day = d.toLocaleDateString(undefined, { weekday: "short" });
      const cur = byDay.get(key) || { key, count: 0, day };
      cur.count += 1;
      byDay.set(key, cur);
    }
    return Array.from(byDay.values())
      .sort((a, b) => a.key.localeCompare(b.key))
      .slice(-7)
      .map((v) => ({ day: v.day, sessions: v.count }));
  })();

  const showLiveData = isLive && data.length > 0;
  const total = data.reduce((acc, cur) => acc + cur.sessions, 0);

  return (
    <div className="glass" style={{ padding: 20, height: "100%", display: "flex", flexDirection: "column" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
        <div>
          <p className="card-title">Gaming sessions</p>
          <p className="card-copy" style={{ marginTop: 2 }}>Sessions per day, last 7 days</p>
        </div>
        <span className={`pill ${showLiveData ? "pill-ok" : "pill-dim"}`}>{showLiveData ? "Live" : loaded ? "Preview" : "…"}</span>
      </div>
      <div style={{ flex: 1, marginTop: 12, minHeight: 160 }}>
        {showLiveData ? (
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data} margin={{ top: 8, right: 4, left: -20, bottom: 0 }}>
              <defs>
                <linearGradient id="sessionsFill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="var(--accent-end)" />
                  <stop offset="100%" stopColor="var(--accent-start)" />
                </linearGradient>
              </defs>
              <XAxis dataKey="day" stroke="var(--text-faint)" fontSize={11} tickLine={false} axisLine={false} />
              <Tooltip
                cursor={{ fill: "var(--hairline)" }}
                contentStyle={{ background: "var(--surface-raised)", border: "1px solid var(--hairline)", borderRadius: 10, fontSize: 12 }}
                labelStyle={{ color: "var(--text-muted)" }}
                formatter={(v: number) => [`${v} session${v === 1 ? "" : "s"}`, ""]}
              />
              <Bar dataKey="sessions" fill="url(#sessionsFill)" radius={[6, 6, 0, 0]} maxBarSize={28} />
            </BarChart>
          </ResponsiveContainer>
        ) : (
          <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", minHeight: 160 }}>
            <p className="card-copy" style={{ fontSize: 12 }}>
              {loaded
                ? inTauriShell()
                  ? "No sessions recorded yet."
                  : "Not in Tauri shell — chart will show your sessions once installed."
                : "Loading…"}
            </p>
          </div>
        )}
      </div>
      {!showLiveData && loaded && (
        <p className="card-copy" style={{ marginTop: 12, fontSize: 11.5 }}>
          No telemetry sessions are available yet.
        </p>
      )}
      {showLiveData && (
        <div style={{ display: "flex", gap: 20, marginTop: 14 }}>
          {[
            { label: "This week", value: String(total) },
            { label: "Days active", value: String(data.length) },
            { label: "Peak day", value: String(Math.max(...data.map((d) => d.sessions))) },
          ].map((s) => (
            <div key={s.label}>
              <p className="card-copy" style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: 0.6 }}>{s.label}</p>
              <p style={{ marginTop: 4, fontWeight: 700 }}>{s.value}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
