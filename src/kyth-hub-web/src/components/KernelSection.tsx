import { useEffect, useState } from "react";
import type { HubSection } from "../data/hubSections";
import { fetchKernelFlavor, runPrivilegedAction } from "../services/liveData";
import { LiveSectionCard, SectionFallbackNote } from "./LiveSectionCard";
import { ActionButton, ActionStatus, useSectionAction } from "./SectionActions";

const FLAVOR_LABEL: Record<string, string> = {
  fedora: "Fedora (default)",
  cachy: "CachyOS",
};

// Real "This PC > Kernel" content — the "kernel-flavor" probe section,
// already cached for the Update Channel tile; no new backend needed.
export function KernelSection({ section }: { section: HubSection }) {
  const [flavor, setFlavor] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);
  const { status, busy, run } = useSectionAction();

  useEffect(() => {
    let cancelled = false;
    fetchKernelFlavor().then((f) => {
      if (!cancelled) {
        setFlavor(f);
        setLoaded(true);
      }
    });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <LiveSectionCard section={section} live={flavor !== null}>
      {flavor ? (
        <div style={{ marginTop: 20 }}>
          <p className="card-copy" style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: 0.6 }}>
            Installed kernel
          </p>
          <p style={{ margin: "4px 0 0", fontSize: 15, fontWeight: 700 }}>{FLAVOR_LABEL[flavor] ?? flavor}</p>
        </div>
      ) : (
        <SectionFallbackNote loaded={loaded} />
      )}

      <div style={{ marginTop: 20, borderTop: "1px solid var(--hairline)", paddingTop: 16 }}>
        <p className="card-copy" style={{ fontSize: 12, margin: "0 0 12px" }}>
          The CachyOS kernel is the gaming default; Fedora's is the conservative fallback. Switching stages a new
          deployment and takes effect on reboot. Progress stays in this Hub window, and authentication appears in a
          normal desktop dialog.
        </p>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 12 }}>
          {(["cachy", "fedora"] as const).map((target) => <ActionButton key={target} label={busy === `kernel-${target}` ? "Staging…" : `Switch to ${FLAVOR_LABEL[target]}`} disabled={busy !== null || flavor === target} onClick={() => run(`kernel-${target}`, `Staging ${target} kernel…`, () => runPrivilegedAction("kernel_switch", { flavor: target }))} />)}
        </div>
        <ActionStatus status={status} />
      </div>
    </LiveSectionCard>
  );
}
