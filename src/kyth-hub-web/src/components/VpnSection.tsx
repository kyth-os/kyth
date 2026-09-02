import { useEffect, useState } from "react";
import type { HubSection } from "../data/hubSections";
import { disconnectVpnConnection, fetchNetworkSummary, fetchNetworkSummaryLive, fetchVpnConnectionStatus, fetchVpnSavedProfile, openVpnApp, startVpnConnection, type NetworkSummary, type VpnSavedProfile } from "../services/liveData";
import { LiveSectionCard, SectionFallbackNote } from "./LiveSectionCard";
import { ActionButton, ActionStatus, RecipeButton, useSectionAction } from "./SectionActions";

const fieldStyle = { padding: "8px 12px", borderRadius: 999, border: "1px solid var(--hairline)", background: "var(--card)", fontSize: 13, minWidth: 180 } as const;

// Real "Move In > VPN" content — one facet of the "network-summary" probe
// section (NetworkSharesSection and CloudStorageSection read the other
// two facets of the same read). Refresh escalates to the live nmcli read.
export function VpnSection({ section }: { section: HubSection }) {
  const [summary, setSummary] = useState<NetworkSummary | null>(null);
  const [profile, setProfile] = useState<VpnSavedProfile | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [gateway, setGateway] = useState("");
  const [protocol, setProtocol] = useState("gp");
  const [osEmulation, setOsEmulation] = useState("win");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [job, setJob] = useState<string | null>(null);
  const [jobStatus, setJobStatus] = useState<string | null>(null);
  const { status, busy, run } = useSectionAction();
  useEffect(() => {
    let cancelled = false;
    Promise.all([fetchNetworkSummary(), fetchVpnSavedProfile()]).then(([s, savedProfile]) => {
      if (!cancelled) {
        setSummary(s);
        setProfile(savedProfile);
        if (savedProfile) {
          setGateway(savedProfile.gateway);
          setProtocol(savedProfile.protocol);
          setOsEmulation(savedProfile.os);
        }
        setLoaded(true);
      }
    });
    return () => {
      cancelled = true;
    };
  }, []);
  useEffect(() => {
    if (!job) return;
    let cancelled = false;
    const poll = async () => {
      const current = await fetchVpnConnectionStatus(job);
      if (!cancelled && current) {
        setJobStatus(current.detail);
        if (current.state === "connected" || current.state === "failed" || current.state === "disconnected") {
          if (current.state === "connected") setSummary((value) => value ? { ...value, vpnConnected: true, vpnName: gateway } : value);
        }
      }
    };
    void poll();
    const timer = window.setInterval(() => void poll(), 1000);
    return () => { cancelled = true; window.clearInterval(timer); };
  }, [job, gateway]);
  return (
    <LiveSectionCard section={section} live={summary !== null}>
      {summary ? (
        <div style={{ marginTop: 20 }}>
          <span className={`pill ${summary.vpnConnected ? "pill-ok" : "pill-dim"}`}>
            {summary.vpnConnected ? `Connected — ${summary.vpnName}` : "Not connected"}
          </span>
          <p className="card-copy" style={{ fontSize: 12, marginTop: 10 }}>{summary.detail}</p>
          {profile && (
            <p className="card-copy" style={{ fontSize: 12, marginTop: 10 }}>
              Saved profile: <strong>{profile.gateway}</strong> · {profile.protocol} · {profile.os}
            </p>
          )}
        </div>
      ) : (
        <SectionFallbackNote loaded={loaded} />
      )}

      <div style={{ marginTop: 20, borderTop: "1px solid var(--hairline)", paddingTop: 16 }}>
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
          <ActionButton
            label={busy === "refresh" ? "Checking…" : "Check connection"}
            disabled={busy !== null}
            onClick={() =>
              run("refresh", "Asking NetworkManager…", async () => {
                const [fresh, savedProfile] = await Promise.all([fetchNetworkSummaryLive(), fetchVpnSavedProfile()]);
                if (!fresh) return "Not available outside the Hub shell.";
                setSummary(fresh);
                setProfile(savedProfile);
                return fresh.vpnConnected ? `Connected to ${fresh.vpnName}.` : "No VPN connection is up.";
              })
            }
          />
          <RecipeButton recipe="setup-tailscale" label="Set up Tailscale" busy={busy} run={run} />
          <ActionButton
            label={busy === "open-vpn" ? "Opening…" : "Open full VPN connection"}
            disabled={busy !== null}
            onClick={() => run("open-vpn", "Opening the VPN connection app…", openVpnApp)}
          />
        </div>
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginTop: 16 }}>
          <input value={gateway} onChange={(event) => setGateway(event.target.value)} placeholder="VPN gateway (https://vpn.example)" style={{ ...fieldStyle, minWidth: 260 }} />
          <select value={protocol} onChange={(event) => setProtocol(event.target.value)} style={fieldStyle}>
            {['gp', 'anyconnect', 'pulse', 'nc', 'f5', 'fortinet', 'array'].map((value) => <option key={value} value={value}>{value}</option>)}
          </select>
          <select value={osEmulation} onChange={(event) => setOsEmulation(event.target.value)} style={fieldStyle}>
            {['win', 'linux', 'mac'].map((value) => <option key={value} value={value}>{value}</option>)}
          </select>
          <input value={username} onChange={(event) => setUsername(event.target.value)} placeholder="Username (optional)" style={fieldStyle} />
          <input value={password} onChange={(event) => setPassword(event.target.value)} type="password" placeholder="Password (optional)" style={fieldStyle} />
          <ActionButton label={busy === "connect" ? "Starting…" : "Connect"} disabled={busy !== null || !gateway.trim()} onClick={() => run("connect", "Starting native VPN connection…", async () => {
            const nextJob = await startVpnConnection({ gateway: gateway.trim(), protocol, os_emulation: osEmulation, username: username.trim(), password });
            setJob(nextJob);
            setPassword("");
            return "VPN connection started. Complete SAML sign-in if the secure window appears.";
          })} />
          {job && <ActionButton label="Disconnect" disabled={busy !== null} onClick={() => run("disconnect", "Disconnecting VPN…", async () => { const detail = await disconnectVpnConnection(job); setJobStatus(detail); setSummary((value) => value ? { ...value, vpnConnected: false, vpnName: "" } : value); return detail; })} />}
        </div>
        <p className="card-copy" style={{ fontSize: 12, marginTop: 12 }}>
          VPN profiles, openconnect, and SAML sign-in are handled by native Rust commands. Credentials and authentication tokens are never shown in status text.
        </p>
        {jobStatus && <p className="card-copy" style={{ fontSize: 12, marginTop: 8 }}>{jobStatus}</p>}
        <ActionStatus status={status} />
      </div>
    </LiveSectionCard>
  );
}
