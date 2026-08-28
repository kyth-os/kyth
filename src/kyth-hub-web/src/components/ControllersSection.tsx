import { useEffect, useState } from "react";
import type { HubSection } from "../data/hubSections";
import { fetchControllers, type ControllerInfo } from "../services/liveData";
import { LiveSectionCard, SectionFallbackNote } from "./LiveSectionCard";

// Real "Play > Controllers" content — kyth_shared.system.controllers'
// detect_controllers(), read through the disk-backed "controllers-detect"
// probe section (see services/liveData.ts).
export function ControllersSection({ section }: { section: HubSection }) {
  const [info, setInfo] = useState<ControllerInfo | null>(null);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    let cancelled = false;
    fetchControllers().then((c) => {
      if (!cancelled) {
        setInfo(c);
        setLoaded(true);
      }
    });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <LiveSectionCard section={section} live={info !== null}>
      {info ? (
        info.usbControllers.length > 0 ? (
          <div style={{ marginTop: 20, display: "flex", flexDirection: "column", gap: 2 }}>
            {info.usbControllers.map((c, i) => (
              <div
                key={`${c.kind}-${i}`}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 12,
                  padding: "10px 4px",
                  borderBottom: "1px solid var(--hairline)",
                }}
              >
                <span style={{ width: 8, height: 8, borderRadius: "50%", background: "var(--status-ok)", flexShrink: 0 }} />
                <p style={{ margin: 0, fontSize: 13, fontWeight: 600, flex: 1 }}>{c.name}</p>
                <span className="pill pill-dim" style={{ flexShrink: 0 }}>
                  {c.kind}
                </span>
              </div>
            ))}
          </div>
        ) : (
          <p className="card-copy" style={{ marginTop: 20, fontSize: 13 }}>
            No game controllers detected right now — plug one in and reopen this page.
          </p>
        )
      ) : (
        <SectionFallbackNote loaded={loaded} />
      )}
    </LiveSectionCard>
  );
}
