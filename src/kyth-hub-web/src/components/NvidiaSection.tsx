import { useEffect, useState } from "react";
import type { HubSection } from "../data/hubSections";
import { fetchNvidiaDetected } from "../services/liveData";
import { LiveSectionCard, SectionFallbackNote } from "./LiveSectionCard";
import { ActionStatus, RecipeButton, useSectionAction } from "./SectionActions";

// Real "This PC > NVIDIA Drivers" content — the "nvidia-detect" probe
// section, already cached for the GPU stat tile; no new backend needed.
export function NvidiaSection({ section }: { section: HubSection }) {
  const [detected, setDetected] = useState<boolean | null>(null);
  const [loaded, setLoaded] = useState(false);
  const { status, busy, run } = useSectionAction();

  useEffect(() => {
    let cancelled = false;
    fetchNvidiaDetected().then((d) => {
      if (!cancelled) {
        setDetected(d);
        setLoaded(true);
      }
    });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <LiveSectionCard section={section} live={detected !== null}>
      {detected !== null ? (
        <div style={{ marginTop: 20 }}>
          <span className={`pill ${detected ? "pill-ok" : "pill-dim"}`}>
            {detected ? "NVIDIA GPU detected" : "No NVIDIA GPU detected"}
          </span>
        </div>
      ) : (
        <SectionFallbackNote loaded={loaded} />
      )}

      {detected && (
        <div style={{ marginTop: 20, borderTop: "1px solid var(--hairline)", paddingTop: 16 }}>
          <p className="card-copy" style={{ fontSize: 12, margin: "0 0 12px" }}>
            The proprietary driver is layered onto the image, so installing it stages a new deployment.
          </p>
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
            <RecipeButton recipe="nvidia-status" label="Driver status" busy={busy} run={run} />
            <RecipeButton recipe="install-nvidia-driver" label="Install NVIDIA driver" busy={busy} run={run} />
          </div>
          <ActionStatus status={status} />
        </div>
      )}
    </LiveSectionCard>
  );
}
