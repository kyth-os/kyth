import { useEffect, useState } from "react";
import type { HubSection } from "../data/hubSections";
import { fetchUpdateChannel, invokeBootcSwitchBranch } from "../services/liveData";
import { LiveSectionCard, SectionFallbackNote } from "./LiveSectionCard";
import { ActionButton, ActionStatus, useSectionAction } from "./SectionActions";

// The two channels `just switch-channel` accepts (system-updates.just);
// bootc_policy::switch_channel_arg is the authority and rejects anything
// else, so this list stays in step with it rather than with the tag names.
const SWITCHABLE_CHANNELS = [
  { key: "stable", label: "Stable" },
  { key: "testing", label: "Testing" },
] as const;

// "This PC > Update channel" — same bootc-branch read as UpdatesSection,
// framed as the channel switcher state rather than the deployment view.
export function ChannelsSection({ section }: { section: HubSection }) {
  const [channel, setChannel] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);
  const { status, busy, run } = useSectionAction();
  useEffect(() => {
    let cancelled = false;
    fetchUpdateChannel().then((c) => {
      if (!cancelled) {
        setChannel(c);
        setLoaded(true);
      }
    });
    return () => {
      cancelled = true;
    };
  }, []);
  return (
    <LiveSectionCard section={section} live={channel !== null}>
      {channel ? (
        <div style={{ marginTop: 20 }}>
          <p className="card-copy" style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: 0.6 }}>
            Active channel
          </p>
          <p style={{ margin: "4px 0 0", fontSize: 15, fontWeight: 700 }}>{channel}</p>
          <div style={{ marginTop: 20, borderTop: "1px solid var(--hairline)", paddingTop: 16 }}>
            <p className="card-copy" style={{ fontSize: 12, margin: "0 0 12px" }}>
              Switching stages the new image; the change applies on reboot.
            </p>
            <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
              {SWITCHABLE_CHANNELS.map(({ key, label }) => (
                <ActionButton
                  key={key}
                  label={busy === key ? `Switching to ${label}…` : `Switch to ${label}`}
                  disabled={busy !== null}
                  onClick={() => run(key, `Switching to ${label}…`, () => invokeBootcSwitchBranch(key))}
                />
              ))}
            </div>
            <ActionStatus status={status} />
          </div>
        </div>
      ) : (
        <SectionFallbackNote loaded={loaded} />
      )}
    </LiveSectionCard>
  );
}
