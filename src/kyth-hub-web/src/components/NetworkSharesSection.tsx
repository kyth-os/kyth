import { useEffect, useState } from "react";
import type { HubSection } from "../data/hubSections";
import {
  addNetworkShare,
  commandText,
  fetchConfiguredNetworkShares,
  fetchNetworkSummary,
  fetchNetworkSummaryLive,
  fetchSmbBrowse,
  fetchSmbMountCommand,
  removeNetworkShare,
  type ConfiguredNetworkShare,
  type NetworkSummary,
} from "../services/liveData";
import { LiveSectionCard, SectionFallbackNote } from "./LiveSectionCard";
import { ActionButton, ActionStatus, CommandLine, useSectionAction } from "./SectionActions";

const fieldStyle = { padding: "8px 12px", borderRadius: 999, border: "1px solid var(--hairline)", background: "var(--card)", fontSize: 13, minWidth: 180 } as const;
const initialForm = { name: "", server: "", share_path: "", mount_point: "", username: "", password: "", domain: "", auto_mount: true, mount_now: true };

// Credentials are sent only to the existing root helper through the narrow
// privileged socket. The user config holds display metadata only, never a password.
export function NetworkSharesSection({ section }: { section: HubSection }) {
  const [summary, setSummary] = useState<NetworkSummary | null>(null);
  const [configured, setConfigured] = useState<ConfiguredNetworkShare[]>([]);
  const [host, setHost] = useState("");
  const [share, setShare] = useState("");
  const [mountCmd, setMountCmd] = useState<string | null>(null);
  const [form, setForm] = useState(initialForm);
  const [loaded, setLoaded] = useState(false);
  const { status, busy, run } = useSectionAction();

  const refreshConfigured = async () => setConfigured((await fetchConfiguredNetworkShares()) ?? []);
  const refreshSummary = async () => {
    const fresh = await fetchNetworkSummaryLive();
    if (fresh) setSummary(fresh);
    return fresh;
  };

  useEffect(() => {
    let cancelled = false;
    Promise.all([fetchNetworkSummary(), fetchConfiguredNetworkShares()]).then(([network, shares]) => {
      if (!cancelled) { setSummary(network); setConfigured(shares ?? []); setLoaded(true); }
    });
    return () => { cancelled = true; };
  }, []);

  const setField = <K extends keyof typeof initialForm>(field: K, value: (typeof initialForm)[K]) => setForm((current) => ({ ...current, [field]: value }));

  const addShare = () => run("add", "Creating the protected share mount…", async () => {
    const name = form.name.trim().replace(/[^A-Za-z0-9_-]/g, "_");
    const mountPoint = form.mount_point.trim() || (name ? `/mnt/kyth/${name}` : "");
    if (!name || !form.server.trim() || !form.share_path.trim() || !form.username.trim()) return "Share name, server, share path, and username are required.";
    const detail = await addNetworkShare({ ...form, name, server: form.server.trim(), share_path: form.share_path.trim().replace(/^\/+/, ""), mount_point: mountPoint, username: form.username.trim(), domain: form.domain.trim() });
    if (detail === "Cancelled.") return detail;
    await Promise.all([refreshConfigured(), refreshSummary()]);
    setForm(initialForm);
    return detail;
  });

  return (
    <LiveSectionCard section={section} live={summary !== null}>
      {summary ? <div style={{ marginTop: 20 }}>
        <p className="card-copy" style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: 0.6 }}>SMB/CIFS shares mounted</p>
        <p style={{ margin: "4px 0 0", fontSize: 22, fontWeight: 800 }}>{summary.smbMounts}</p>
        <p className="card-copy" style={{ fontSize: 12, marginTop: 8 }}>{summary.detail}</p>
      </div> : <SectionFallbackNote loaded={loaded} />}

      <div style={{ marginTop: 20, borderTop: "1px solid var(--hairline)", paddingTop: 16 }}>
        <p className="card-copy" style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: 0.6 }}>Configure a persistent share</p>
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginTop: 8 }}>
          <input value={form.name} onChange={(event) => setField("name", event.target.value)} placeholder="Share name (media)" style={fieldStyle} />
          <input value={form.server} onChange={(event) => setField("server", event.target.value)} placeholder="Server name or IP" style={fieldStyle} />
          <input value={form.share_path} onChange={(event) => setField("share_path", event.target.value)} placeholder="Share path (media)" style={fieldStyle} />
          <input value={form.mount_point} onChange={(event) => setField("mount_point", event.target.value)} placeholder="Mount point (default /mnt/kyth/name)" style={{ ...fieldStyle, minWidth: 260 }} />
          <input value={form.username} onChange={(event) => setField("username", event.target.value)} placeholder="Username" style={fieldStyle} />
          <input value={form.password} type="password" onChange={(event) => setField("password", event.target.value)} placeholder="Password (stored securely)" style={fieldStyle} />
          <input value={form.domain} onChange={(event) => setField("domain", event.target.value)} placeholder="Domain (optional)" style={fieldStyle} />
        </div>
        <div style={{ display: "flex", gap: 16, flexWrap: "wrap", marginTop: 12, alignItems: "center" }}>
          <label className="card-copy" style={{ fontSize: 12 }}><input type="checkbox" checked={form.auto_mount} onChange={(event) => setField("auto_mount", event.target.checked)} /> Mount automatically at boot</label>
          <label className="card-copy" style={{ fontSize: 12 }}><input type="checkbox" checked={form.mount_now} onChange={(event) => setField("mount_now", event.target.checked)} /> Mount now</label>
          <ActionButton label={busy === "add" ? "Adding…" : "Add share"} disabled={busy !== null} onClick={addShare} />
        </div>
        <p className="card-copy" style={{ fontSize: 12, marginTop: 10 }}>Credentials go only to the protected root helper. This Hub keeps only the non-secret share details shown below.</p>

        {configured.length > 0 && <div style={{ marginTop: 16 }}>
          <p className="card-copy" style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: 0.6 }}>Configured shares</p>
          {configured.map((item) => <div key={item.name} style={{ display: "flex", gap: 10, justifyContent: "space-between", alignItems: "center", padding: "10px 0", borderBottom: "1px solid var(--hairline)", flexWrap: "wrap" }}>
            <span className="card-copy" style={{ fontSize: 12 }}><strong>{item.name}</strong> — //{item.server}/{item.share_path} → {item.mount_point}{item.auto_mount ? " (auto)" : ""}</span>
            <ActionButton label={busy === `remove-${item.name}` ? "Removing…" : "Remove"} disabled={busy !== null} onClick={() => run(`remove-${item.name}`, `Removing ${item.name}…`, async () => {
              const detail = await removeNetworkShare(item);
              if (detail !== "Cancelled.") await Promise.all([refreshConfigured(), refreshSummary()]);
              return detail;
            })} />
          </div>)}
        </div>}
      </div>

      <div style={{ marginTop: 20, borderTop: "1px solid var(--hairline)", paddingTop: 16 }}>
        <p className="card-copy" style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: 0.6 }}>Find a share</p>
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginTop: 8, alignItems: "center" }}>
          <input value={host} onChange={(event) => setHost(event.target.value)} placeholder="server name or IP (blank = whole network)" style={{ ...fieldStyle, minWidth: 260 }} />
          <ActionButton label={busy === "browse" ? "Looking…" : "Browse"} disabled={busy !== null} onClick={() => run("browse", "Asking the network…", async () => (await fetchSmbBrowse(host.trim() || null))?.detail ?? "Not available outside the Hub shell.")} />
          <ActionButton label={busy === "refresh" ? "Checking…" : "Refresh mounts"} disabled={busy !== null} onClick={() => run("refresh", "Re-reading mounts…", async () => { const fresh = await refreshSummary(); return fresh ? `${fresh.smbMounts} share(s) mounted.` : "Not available outside the Hub shell."; })} />
        </div>
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginTop: 12, alignItems: "center" }}>
          <input value={share} onChange={(event) => setShare(event.target.value)} placeholder="smb://server/share" style={{ ...fieldStyle, minWidth: 260 }} />
          <ActionButton label="Show temporary mount command" disabled={busy !== null || share.trim().length === 0} onClick={() => run("mount", "Building the mount command…", async () => { const text = commandText(await fetchSmbMountCommand(share.trim())); setMountCmd(text); return text ? "Copy this for a temporary user-session mount." : "Could not build a mount command."; })} />
        </div>
        <CommandLine label="Temporary mount command" command={mountCmd} />
        <ActionStatus status={status} />
      </div>
    </LiveSectionCard>
  );
}
