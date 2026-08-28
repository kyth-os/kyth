// Single-value gauge — one hue-family ramp (var(--accent-start) ->
// var(--accent-end)), track in the muted surface tone, per the
// sequential-color rule (one metric, not a category to distinguish, so no
// multi-hue palette is needed here — the gradient is a lightness/chroma
// step within blue, not a hue swap).
export function GaugeCard({
  title,
  subtitle,
  value,
  max = 100,
  displayValue,
  unitLabel,
  gaugeId,
  pendingNote,
}: {
  title: string;
  subtitle: string;
  value: number | null;
  max?: number;
  displayValue: string;
  unitLabel: string;
  gaugeId: string;
  pendingNote?: string;
}) {
  // A null value is "we have no reading", not "the reading is zero" — an
  // empty arc with an em dash, never a number the subtitle would then
  // attribute to a source we never queried.
  const pct = value === null ? 0 : Math.max(0, Math.min(1, value / max));
  const radius = 54;
  const circumference = Math.PI * radius; // half circle
  const offset = circumference * (1 - pct);
  const gradientId = `gauge-${gaugeId}`;

  return (
    <div className="glass" style={{ padding: 20, display: "flex", flexDirection: "column", height: "100%" }}>
      <p className="card-title">{title}</p>
      <p className="card-copy" style={{ marginTop: 2 }}>
        {subtitle}
      </p>
      <div style={{ display: "grid", placeItems: "center", flex: 1, marginTop: 8 }}>
        <svg width="140" height="80" viewBox="0 0 140 80">
          <defs>
            <linearGradient id={gradientId} x1="0" y1="0" x2="1" y2="0">
              <stop offset="0%" stopColor="var(--accent-start)" />
              <stop offset="100%" stopColor="var(--accent-end)" />
            </linearGradient>
          </defs>
          <path
            d="M 13 70 A 54 54 0 0 1 127 70"
            fill="none"
            stroke="var(--surface-overlay)"
            strokeWidth="10"
            strokeLinecap="round"
          />
          <path
            d="M 13 70 A 54 54 0 0 1 127 70"
            fill="none"
            stroke={`url(#${gradientId})`}
            strokeWidth="10"
            strokeLinecap="round"
            strokeDasharray={circumference}
            strokeDashoffset={offset}
          />
          <text
            x="70"
            y="58"
            textAnchor="middle"
            fontSize="20"
            fontWeight={800}
            fill={value === null ? "var(--text-faint)" : "var(--text)"}
          >
            {value === null ? "\u2014" : displayValue}
          </text>
        </svg>
      </div>
      <p className="card-copy" style={{ textAlign: "center", marginTop: -4 }}>
        {value === null ? (pendingNote ?? "No reading available") : unitLabel}
      </p>
    </div>
  );
}
