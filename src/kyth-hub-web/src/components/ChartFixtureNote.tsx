/** Shared "these numbers are fixtures" note for the two dashboard charts.
 *
 * Unlike the rest of the dashboard, these two still draw mockDashboard
 * fixtures. The data they depict is real and already collected —
 * kyth-telem ships as a systemd user unit and writes gaming sessions to
 * ~/.local/share/kyth/telemetry.db, which the Qt Hub reads via
 * kyth_shared.telemetry.recent_sessions. What's missing is only the Rust
 * side: that reader has no port in kyth-shared-rs, and porting it needs a
 * sqlite dependency this crate doesn't have yet.
 *
 * So the note must not say "no sessions recorded yet" — that would claim
 * we looked. It says we haven't wired the read, and names what's needed.
 */
export function ChartFixtureNote() {
  return (
    <p className="card-copy" style={{ marginTop: 12, fontSize: 11.5 }}>
      Sample figures — the telemetry reader (kyth-telem's session database) isn't
      wired into this shell yet, so this chart isn't showing your machine.
    </p>
  );
}
