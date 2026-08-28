import { useEffect, useState } from "react";
import type { HubSection } from "../data/hubSections";
import {
  fetchHardwareSnapshot,
  fetchMesaOverlayDryRun,
  fetchMesaVersion,
  fetchMokStatus,
  fetchSecurebootState,
  type MokStatus,
} from "../services/liveData";
import { LiveSectionCard, SectionFallbackNote } from "./LiveSectionCard";
import { ActionButton, ActionStatus, RecipeButton, useSectionAction } from "./SectionActions";

// "Play > Compatibility" — Secure Boot / anti-cheat readiness plus the
// Mesa version Proton actually runs against.
//
// Mount deliberately reads only cheap things: the disk-cached
// secureboot-state scalar, hardware-summary capabilities, and mesa_version
// (one rpm/glxinfo call). The two slow paths — mokutil, which takes a
// couple of seconds per invocation, and the Mesa overlay dry run — sit
// behind buttons so switching to this tab never stalls.
export function CompatibilitySection({ section }: { section: HubSection }) {
  const [sbState, setSbState] = useState<string | null>(null);
  const [mesa, setMesa] = useState<string | null>(null);
  const [mok, setMok] = useState<MokStatus | null>(null);
  const [hwCaps, setHwCaps] = useState<string[] | null>(null);
  const [loaded, setLoaded] = useState(false);
  const { status, busy, run } = useSectionAction();

  useEffect(() => {
    let c = false;
    Promise.all([fetchSecurebootState(), fetchHardwareSnapshot(), fetchMesaVersion()]).then(([sb, h, m]) => {
      if (!c) {
        setSbState(sb);
        setHwCaps(h?.capabilities ?? null);
        setMesa(m);
        setLoaded(true);
      }
    });
    return () => {
      c = true;
    };
  }, []);

  const live = sbState !== null || hwCaps !== null || mesa !== null;
  return (
    <LiveSectionCard section={section} live={live}>
      {live ? (
        <div style={{ marginTop: 20 }}>
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
            {sbState && (
              <span className={`pill ${sbState === "enabled" ? "pill-ok" : "pill-dim"}`}>Secure Boot: {sbState}</span>
            )}
            {mok && (
              <span className={`pill ${mok.enrolled === "enrolled" ? "pill-ok" : "pill-dim"}`}>MOK: {mok.enrolled}</span>
            )}
            {mesa && <span className="pill pill-dim">Mesa {mesa}</span>}
          </div>
          {hwCaps && hwCaps.length > 0 && (
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 10 }}>
              {hwCaps.slice(0, 6).map((cap) => (
                <span key={cap} className="pill pill-dim">{cap}</span>
              ))}
            </div>
          )}
        </div>
      ) : (
        <SectionFallbackNote loaded={loaded} />
      )}

      <div style={{ marginTop: 20, borderTop: "1px solid var(--hairline)", paddingTop: 16 }}>
        <p className="card-copy" style={{ fontSize: 12, margin: "0 0 12px" }}>
          Anti-cheat in some games needs Secure Boot on with KythOS's key enrolled.
        </p>
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
          <ActionButton
            label={busy === "mok" ? "Checking…" : "Check MOK enrollment"}
            disabled={busy !== null}
            onClick={() =>
              run("mok", "Asking mokutil… (this takes a few seconds)", async () => {
                const fresh = await fetchMokStatus();
                if (!fresh) return "Not available outside the Hub shell.";
                setMok(fresh);
                setSbState(fresh.sb_state);
                return `Secure Boot ${fresh.sb_state}, key ${fresh.enrolled}.`;
              })
            }
          />
          <RecipeButton recipe="enroll-secureboot" label="Enroll KythOS key" busy={busy} run={run} />
          <ActionButton
            label={busy === "mesa" ? "Testing…" : "Test Mesa overlay"}
            disabled={busy !== null}
            onClick={() =>
              run("mesa", "Running the Mesa overlay dry run…", async () => {
                const res = await fetchMesaOverlayDryRun();
                if (!res) return "Not available outside the Hub shell.";
                return res.detail;
              })
            }
          />
        </div>
        <ActionStatus status={status} />
      </div>
    </LiveSectionCard>
  );
}
