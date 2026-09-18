import { useEffect, useRef, useState } from "react";
import type { HubSection } from "../data/hubSections";
import { cancelVpnConnection, disconnectVpnConnection, fetchNetworkSummary, fetchNetworkSummaryLive, fetchVpnConnectionStatus, fetchVpnProtectionStatus, fetchVpnSavedProfile, getInFlightJob, onOnlineRefetch, openVpnApp, setVpnProtection, startVpnConnection, untrackVpnJob, type NetworkSummary, type VpnProtectionStatus, type VpnSavedProfile } from "../services/liveData";
import { LiveSectionCard, SectionFallbackNote } from "./LiveSectionCard";
import { ActionButton, ActionStatus, RecipeButton, useSectionAction } from "./SectionActions";

const fieldStyle = { padding: "8px 12px", borderRadius: 999, border: "1px solid var(--hairline)", background: "var(--card)", fontSize: 13, minWidth: 180 } as const;

// Real VPN controls — one facet of the "network-summary" probe
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
  // The connect job is tracked in the shared in-flight registry, so a reload
  // reattaches here: Cancel/Disconnect keeps reaching the real backend job
  // even though component state was lost.
  const [job, setJob] = useState<string | null>(() => getInFlightJob("vpn") ?? null);
  const [jobStatus, setJobStatus] = useState<string | null>(null);
  const [protection, setProtection] = useState<VpnProtectionStatus | null>(null);
  const { status, busy, run } = useSectionAction("hub-action");
  // Mount fetch as a named refresh so a reconnect can re-run it: the
  // summary/profile rendered from a stale offline read would otherwise
  // sit unchanged until manual navigation.
  const refreshAll = useRef(() => {});
  refreshAll.current = () => {
    void Promise.all([fetchNetworkSummary(), fetchVpnSavedProfile(), fetchVpnProtectionStatus()]).then(([s, savedProfile, vpnProtection]) => {
      setSummary(s);
      setProfile(savedProfile);
      setProtection(vpnProtection);
      if (savedProfile) {
        setGateway(savedProfile.gateway);
        setProtocol(savedProfile.protocol);
        setOsEmulation(savedProfile.os);
      }
      setLoaded(true);
    });
  };
  useEffect(() => {
    refreshAll.current();
    return onOnlineRefetch(() => refreshAll.current());
  }, []);
  useEffect(() => {
    if (!job) return;
    let cancelled = false;
    let timer: number | undefined;
    let polls = 0;
    const TERMINAL_VPN_STATES = new Set(["connected", "failed", "disconnected", "complete", "failed_lockdown", "failed_lockdown_open", "connected_firewall_open", "complete_firewall_open"]);
    const poll = async () => {
      if (cancelled) return;
      polls += 1;
      const current = await fetchVpnConnectionStatus(job);
      if (!cancelled && current) {
        setJobStatus(current.detail);
        // The backend no longer knows this job (restart, eviction): release
        // the slot instead of polling a dead id to the cap.
        if (current.state === "unknown") {
          untrackVpnJob(job);
          if (!cancelled) setJobStatus("The VPN job is no longer known; it may have been cleared by a restart.");
          return;
        }
        // Terminal state reached: stop polling rather than holding the 1s
        // interval open forever. Lockdown states are terminal too: the
        // tunnel is gone and the firewall verdict (blocked vs open) is final.
        if (TERMINAL_VPN_STATES.has(current.state)) {
          if (current.state === "connected") setSummary((value) => value ? { ...value, vpnConnected: true, vpnName: gateway } : value);
          if (current.state === "failed_lockdown_open" || current.state === "connected_firewall_open" || current.state === "complete_firewall_open") {
            setJobStatus(`Action needed: ${current.detail}`);
          }
          // Dead tunnels release the tracked slot; live ones (connected,
          // connected_firewall_open) stay tracked so Disconnect keeps
          // working — including after a reload.
          if (current.state !== "connected" && current.state !== "connected_firewall_open") {
            untrackVpnJob(job);
          }
          return;
        }
      }
      // Safety cap: 300 polls, backing off from 1s to 5s after the first
      // minute so a wedged backend can't spin the UI forever.
      if (polls >= 300) {
        if (!cancelled) setJobStatus((value) => value ?? "VPN status is still pending; refresh the connection check.");
        return;
      }
      timer = window.setTimeout(() => void poll(), polls < 60 ? 1000 : 5000);
    };
    void poll();
    return () => { cancelled = true; if (timer !== undefined) window.clearTimeout(timer); };
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
            try {
            const active = getInFlightJob("vpn");
            if (active && active !== job) {
              setJob(active);
              return "A VPN connection is already active; disconnect it before starting another.";
            }
            const nextJob = await startVpnConnection({ gateway: gateway.trim(), protocol, osEmulation, username: username.trim(), password });
            setJob(nextJob);
            return "VPN connection started. Complete SAML sign-in if the secure window appears.";
          } finally {
            // Never retain the plaintext password: clear it whether the
            // connect path succeeded or threw.
            setPassword("");
          }})} />
          {job && <ActionButton label="Disconnect" disabled={busy !== null} onClick={() => run("disconnect", "Disconnecting VPN…", async () => { const detail = await disconnectVpnConnection(job); setJobStatus(detail); setSummary((value) => value ? { ...value, vpnConnected: false, vpnName: "" } : value); setJob(null); return detail; })} />}
          {job && !summary?.vpnConnected && <ActionButton label={busy === "cancel" ? "Cancelling…" : "Cancel"} disabled={busy !== null} onClick={() => run("cancel", "Cancelling VPN…", async () => { const detail = await cancelVpnConnection(); setJobStatus(detail); setJob(null); return detail; })} />}
        </div>
        <p className="card-copy" style={{ fontSize: 12, marginTop: 12 }}>
          VPN profiles, openconnect, and SAML sign-in are handled by native Rust commands. Credentials and authentication tokens are never shown in status text.
        </p>
        <div style={{ marginTop: 12, borderTop: "1px solid var(--hairline)", paddingTop: 12 }}>
          <p className="card-copy" style={{ fontSize: 13, fontWeight: 600 }}>VPN protection</p>
          {protection ? (
            <div style={{ display: "flex", gap: 16, flexWrap: "wrap", marginTop: 8 }}>
              <label style={{ display: "flex", gap: 8, alignItems: "center", fontSize: 12 }}>
                <input
                  type="checkbox"
                  checked={protection.vpn_fail_closed}
                  disabled={busy !== null}
                  onChange={() => {
                    const next = { vpnFailClosed: !protection.vpn_fail_closed, vpnDnsExclusive: protection.vpn_dns_exclusive };
                    void run("vpn-protection", "Saving VPN protection…", async () => {
                      const detail = await setVpnProtection(next);
                      setProtection(await fetchVpnProtectionStatus());
                      return detail;
                    });
                  }}
                />
                Fail-closed: block the network if the tunnel drops
              </label>
              <label style={{ display: "flex", gap: 8, alignItems: "center", fontSize: 12 }}>
                <input
                  type="checkbox"
                  checked={protection.vpn_dns_exclusive}
                  disabled={busy !== null}
                  onChange={() => {
                    const next = { vpnFailClosed: protection.vpn_fail_closed, vpnDnsExclusive: !protection.vpn_dns_exclusive };
                    void run("vpn-protection", "Saving VPN protection…", async () => {
                      const detail = await setVpnProtection(next);
                      setProtection(await fetchVpnProtectionStatus());
                      return detail;
                    });
                  }}
                />
                Exclusive DNS: pin tunnel links to the VPN resolver
              </label>
            </div>
          ) : (
            <p className="card-copy" style={{ fontSize: 12, marginTop: 8 }}>Protection toggles are available from the installed Kyth Hub.</p>
          )}
          {protection && (
            <p className="card-copy" style={{ fontSize: 12, marginTop: 8 }}>
              Fail-closed is {protection.vpn_fail_closed ? "on — an unexpected drop blocks the network" : "off — traffic may return to the LAN on a drop"} · Exclusive DNS is {protection.vpn_dns_exclusive ? "on" : "off"} · Restores zone {protection.firewall_zone} on clean disconnect.
            </p>
          )}
        </div>
        {jobStatus && <p className="card-copy" style={{ fontSize: 12, marginTop: 8 }}>{jobStatus}</p>}
        <ActionStatus status={status} />
      </div>
    </LiveSectionCard>
  );
}
