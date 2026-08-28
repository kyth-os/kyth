import { useEffect, useState } from "react";
import type { HubSection } from "../data/hubSections";
import {
  commandText,
  fetchNetworkSummary,
  fetchNetworkSummaryLive,
  fetchSmbBrowse,
  fetchSmbMountCommand,
  type NetworkSummary,
} from "../services/liveData";
import { LiveSectionCard, SectionFallbackNote } from "./LiveSectionCard";
import { ActionButton, ActionStatus, CommandLine, useSectionAction } from "./SectionActions";

// Real "Move In > Network Shares" content — the SMB facet of the
// "network-summary" probe section (see VpnSection's comment), plus the
// browse/mount path from kyth_shared::system::smb.
//
// smb_browse hits the network, so it only runs when the user asks. The
// mount command is rendered as text rather than run: mounting needs root
// and a credentials prompt this window can't host safely.
export function NetworkSharesSection({ section }: { section: HubSection }) {
  const [summary, setSummary] = useState<NetworkSummary | null>(null);
  const [host, setHost] = useState("");
  const [share, setShare] = useState("");
  const [mountCmd, setMountCmd] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);
  const { status, busy, run } = useSectionAction();

  useEffect(() => {
    let cancelled = false;
    fetchNetworkSummary().then((s) => {
      if (!cancelled) {
        setSummary(s);
        setLoaded(true);
      }
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const inputStyle = {
    padding: "8px 12px",
    borderRadius: 999,
    border: "1px solid var(--hairline)",
    background: "var(--card)",
    fontSize: 13,
    minWidth: 180,
  } as const;

  return (
    <LiveSectionCard section={section} live={summary !== null}>
      {summary ? (
        <div style={{ marginTop: 20 }}>
          <p className="card-copy" style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: 0.6 }}>
            SMB/CIFS shares mounted
          </p>
          <p style={{ margin: "4px 0 0", fontSize: 22, fontWeight: 800 }}>{summary.smbMounts}</p>
          <p className="card-copy" style={{ fontSize: 12, marginTop: 8 }}>{summary.detail}</p>
        </div>
      ) : (
        <SectionFallbackNote loaded={loaded} />
      )}

      <div style={{ marginTop: 20, borderTop: "1px solid var(--hairline)", paddingTop: 16 }}>
        <p className="card-copy" style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: 0.6 }}>
          Find a share
        </p>
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginTop: 8, alignItems: "center" }}>
          <input
            value={host}
            onChange={(event) => setHost(event.target.value)}
            placeholder="server name or IP (blank = whole network)"
            style={{ ...inputStyle, minWidth: 260 }}
          />
          <ActionButton
            label={busy === "browse" ? "Looking…" : "Browse"}
            disabled={busy !== null}
            onClick={() =>
              run("browse", "Asking the network…", async () => {
                const res = await fetchSmbBrowse(host.trim() || null);
                if (!res) return "Not available outside the Hub shell.";
                return res.detail;
              })
            }
          />
          <ActionButton
            label={busy === "refresh" ? "Checking…" : "Refresh mounts"}
            disabled={busy !== null}
            onClick={() =>
              run("refresh", "Re-reading mounts…", async () => {
                const fresh = await fetchNetworkSummaryLive();
                if (!fresh) return "Not available outside the Hub shell.";
                setSummary(fresh);
                return `${fresh.smbMounts} share(s) mounted.`;
              })
            }
          />
        </div>

        <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginTop: 12, alignItems: "center" }}>
          <input
            value={share}
            onChange={(event) => setShare(event.target.value)}
            placeholder="//server/share"
            style={{ ...inputStyle, minWidth: 260 }}
          />
          <ActionButton
            label="Show mount command"
            disabled={busy !== null || share.trim().length === 0}
            onClick={() =>
              run("mount", "Building the mount command…", async () => {
                const argv = await fetchSmbMountCommand(share.trim());
                const text = commandText(argv);
                setMountCmd(text);
                return text ? "Run this in a terminal — mounting needs root." : "Could not build a mount command.";
              })
            }
          />
        </div>
        <CommandLine label="Mount command" command={mountCmd} />
        <ActionStatus status={status} />
      </div>
    </LiveSectionCard>
  );
}
