import { useEffect, useState } from "react";
import type { HubSection } from "../data/hubSections";
import {
  commandText,
  fetchCloudOauthStatus,
  fetchNetworkSummary,
  fetchNetworkSummaryLive,
  fetchRcloneOauthCommand,
  type NetworkSummary,
} from "../services/liveData";
import { LiveSectionCard, SectionFallbackNote } from "./LiveSectionCard";
import { ActionButton, ActionStatus, CommandLine, useSectionAction } from "./SectionActions";

// The remotes rclone_oauth_command knows how to configure — the Rust side
// is the authority on the argv, this list is only which buttons to offer.
const REMOTES = ["onedrive", "drive", "dropbox"] as const;
const REMOTE_LABEL: Record<string, string> = {
  onedrive: "OneDrive",
  drive: "Google Drive",
  dropbox: "Dropbox",
};

// Real "Move In > Cloud Storage" content — the cloud facet of the
// "network-summary" probe section (see VpnSection's comment), plus
// rclone's OAuth setup path. The setup command is shown rather than run:
// rclone's OAuth flow is interactive and needs a terminal of its own.
export function CloudStorageSection({ section }: { section: HubSection }) {
  const [summary, setSummary] = useState<NetworkSummary | null>(null);
  const [oauth, setOauth] = useState<{ ok: boolean; detail: string } | null>(null);
  const [setupCmd, setSetupCmd] = useState<{ remote: string; text: string | null } | null>(null);
  const [loaded, setLoaded] = useState(false);
  const { status, busy, run } = useSectionAction();

  useEffect(() => {
    let cancelled = false;
    Promise.all([fetchNetworkSummary(), fetchCloudOauthStatus()]).then(([s, o]) => {
      if (!cancelled) {
        setSummary(s);
        setOauth(o);
        setLoaded(true);
      }
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const live = summary !== null || oauth !== null;
  return (
    <LiveSectionCard section={section} live={live}>
      {live ? (
        <div style={{ marginTop: 20 }}>
          {summary && summary.cloudProviders.length > 0 ? (
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              {summary.cloudProviders.map((p) => (
                <span key={p} className="pill pill-ok">{p}</span>
              ))}
            </div>
          ) : (
            <p className="card-copy" style={{ fontSize: 13 }}>No cloud storage providers set up yet.</p>
          )}
          {oauth && (
            <p className="card-copy" style={{ fontSize: 12, marginTop: 10 }}>
              <span className={`pill ${oauth.ok ? "pill-ok" : "pill-dim"}`} style={{ marginRight: 8 }}>
                rclone: {oauth.ok ? "ready" : "not configured"}
              </span>
              {oauth.detail}
            </p>
          )}
        </div>
      ) : (
        <SectionFallbackNote loaded={loaded} />
      )}

      <div style={{ marginTop: 20, borderTop: "1px solid var(--hairline)", paddingTop: 16 }}>
        <p className="card-copy" style={{ fontSize: 12, margin: "0 0 12px" }}>
          Connecting an account opens a browser sign-in; the command below runs that flow in a terminal.
        </p>
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
          {REMOTES.map((remote) => (
            <ActionButton
              key={remote}
              label={busy === remote ? "Preparing…" : `Connect ${REMOTE_LABEL[remote]}`}
              disabled={busy !== null}
              onClick={() =>
                run(remote, "Building the rclone command…", async () => {
                  const argv = await fetchRcloneOauthCommand(remote);
                  const text = commandText(argv);
                  setSetupCmd({ remote, text });
                  return text ? `Run this to sign in to ${REMOTE_LABEL[remote]}.` : "Could not build the command.";
                })
              }
            />
          ))}
          <ActionButton
            label={busy === "refresh" ? "Checking…" : "Refresh"}
            disabled={busy !== null}
            onClick={() =>
              run("refresh", "Re-reading cloud mounts…", async () => {
                const [fresh, freshOauth] = await Promise.all([fetchNetworkSummaryLive(), fetchCloudOauthStatus()]);
                if (!fresh && !freshOauth) return "Not available outside the Hub shell.";
                if (fresh) setSummary(fresh);
                if (freshOauth) setOauth(freshOauth);
                return `${fresh?.cloudProviders.length ?? 0} provider(s) connected.`;
              })
            }
          />
        </div>
        {setupCmd && <CommandLine label={`${REMOTE_LABEL[setupCmd.remote]} setup`} command={setupCmd.text} />}
        <ActionStatus status={status} />
      </div>
    </LiveSectionCard>
  );
}
