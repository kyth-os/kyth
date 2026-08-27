export function HeroCard({ name }: { name: string }) {
  return (
    <div
      className="glass"
      style={{
        padding: 24,
        position: "relative",
        overflow: "hidden",
        display: "flex",
        flexDirection: "column",
        justifyContent: "space-between",
        minHeight: 220,
        background: "linear-gradient(127deg, rgba(43,107,255,0.22) 0%, rgba(22,28,62,0.92) 55%, rgba(14,18,43,0.85) 100%)",
      }}
    >
      {/* Abstract gradient orb — stands in for the moodboard's photo hero
          without pretending to be a real render; pure CSS, no asset. */}
      <div
        style={{
          position: "absolute",
          right: -70,
          top: -70,
          width: 280,
          height: 280,
          borderRadius: "50%",
          background: "conic-gradient(from 200deg, var(--accent-start), var(--violet-start), var(--accent-end), var(--accent-start))",
          filter: "blur(8px)",
          opacity: 0.4,
        }}
      />
      <div
        style={{
          position: "absolute",
          inset: 0,
          background: "radial-gradient(120% 100% at 0% 100%, rgba(14,18,43,0.9) 40%, transparent 70%)",
        }}
      />
      <div style={{ position: "relative", zIndex: 1 }}>
        <p className="card-copy">Welcome back,</p>
        <h2 style={{ margin: "4px 0 0", fontSize: 26, fontWeight: 800, letterSpacing: -0.5 }}>{name}</h2>
        <p className="card-copy" style={{ marginTop: 8, maxWidth: 260 }}>
          Everything's healthy. Guardian found nothing new to fix today.
        </p>
      </div>
      <button className="btn btn-primary" style={{ position: "relative", zIndex: 1, alignSelf: "flex-start" }}>
        Open Guardian
      </button>
    </div>
  );
}
