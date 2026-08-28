import { useEffect, useState } from "react";
import type { HubSection } from "../data/hubSections";
import { fetchKernelFlavor } from "../services/liveData";
import { LiveSectionCard, SectionFallbackNote } from "./LiveSectionCard";
import { CommandLine } from "./SectionActions";

const FLAVOR_LABEL: Record<string, string> = {
  fedora: "Fedora (default)",
  cachy: "CachyOS",
};

// Real "This PC > Kernel" content — the "kernel-flavor" probe section,
// already cached for the Update Channel tile; no new backend needed.
export function KernelSection({ section }: { section: HubSection }) {
  const [flavor, setFlavor] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);

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
          deployment and takes effect on reboot, so it runs from a terminal where you can read what it stages and
          answer the sudo prompt — the flavour is part of the command, and a bare <code>switch-kernel</code> would
          silently mean Fedora.
        </p>
        <CommandLine label="Switch to the CachyOS kernel" command="ujust switch-kernel cachy" />
        <CommandLine label="Switch to the Fedora kernel" command="ujust switch-kernel fedora" />
        <CommandLine label="Kernel arguments (status, or balanced/performance/gaming)" command="ujust kargs-apply status" />
      </div>
    </LiveSectionCard>
  );
}
