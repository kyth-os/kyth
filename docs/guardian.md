# Kyth Guardian

Kyth Guardian is a local, bounded repair assistant. It combines inexpensive
deterministic health checks with an optional small language model. The model is
not a daemon and is not an execution engine: it starts only for an ambiguous
incident, selects one identifier from Kyth's fixed repair registry, returns a
schema-constrained response, and exits.

## Safety boundary

Guardian owns every executable and argument in its repair registry. Model
output cannot add a command, alter its arguments, install software, delete
files, reboot, update, roll back, or bypass authentication. Unknown recipes,
unknown probes, low confidence, malformed output, and timeouts become advice
only. Automatic repair is off until the user enables it and is limited to
reversible unprivileged recipes after two consecutive failures and a cooldown.

Update quarantine and rollback remain exclusively controlled by Kyth's boot
health system. Guardian only reports that state and points to the existing
recovery workflow.

VPN repair only targets NetworkManager profiles with autoconnect enabled that
failed to come up while the network is otherwise connected. Having a VPN
profile and leaving it disconnected is not treated as a fault.

## Resource behavior

The user timer performs a bounded check every 15 minutes, while a systemd path
unit reacts when the shared user probe cache changes. Both start a oneshot
process; nothing polls continuously. The service runs at low CPU and I/O
priority with memory and CPU limits. `ProtectSystem=strict` is paired with
`StateDirectory=kyth` so occurrence counters and history actually survive a
timer run — without that, background auto-fix can never reach two consecutive
failures.

Recipes (allowlist). Background auto-fix still requires `risk=safe`, no auth, two
consecutive failures, and a cooldown. **Fix My System** / `kyth-guardian fix`
applies the same allowlist on click (including confirm recipes that may prompt
for permission) without waiting for two timer hits. Gaming, capture, updates,
low battery, and thermal pressure still pause execution.

| id | title | risk | auto | cooldown |
|---|---|---|---|---|
| `audio.restart` | Restart audio services | safe | yes | 15m |
| `audio.sink-fallback` | Restore default audio sink | safe | yes | 15m |
| `network.restart-user` | Restart NetworkManager user integration | safe | yes | 15m |
| `network.captive-fix` | Re-toggle networking for captive portals | safe | yes | 30m |
| `network.vpn-fix` | Restart always-on VPN | safe | yes | 30m |
| `network.dns-flush` | Flush DNS cache | safe | yes | 30m |
| `flatpak.refresh-metadata` | Refresh Flatpak metadata | safe | yes | 30m |
| `portal.restart-user` | Restart desktop portals | safe | yes | 15m |
| `plasma.restart-user` | Restart Plasma shell | safe | yes | 15m |
| `storage.maint` | Run storage maintenance (gated scrub/balance) | safe | no | 24h |
| `firmware.refresh` | Refresh firmware metadata (flock) | safe | yes | 12h |
| `display.reconfigure` | Re-apply display outputs | safe | yes | 6h |
| `power.profile-fix` | Reset power profile | safe | yes | 1h |
| `disk.review` | Review storage usage (advisory) | advisory | no | 1h |
| `thermal.notify` | Thermal throttling (advisory) | advisory | no | 1h |
| `storage.smart-warn` | SMART disk health (advisory) | advisory | no | 24h |
| `memory.pressure-relief` | Memory pressure (advisory) | advisory | no | 1h |
| `flatpak.repair-user` | Repair user Flatpak data | confirm | no | 1h |
| `bluetooth.restart` | Restart Bluetooth | confirm | no | 30m |
| `controller.repair` | Restart system joycond | confirm | no | 6h |
| `update.review-health` | Review update health | advisory | no | 1h |

The optional Apache-2.0 Q4 model is about 1.04 GiB. Its manifest is part of the
signed Kyth image and pins the URL, byte size, SHA-256, license, prompt version,
and Guardian compatibility version. Downloads are written atomically and are
not installed unless their size and digest match. `llama-cli` runs CPU-only
with a 2,048-token context, 256-token response limit, and 30-second timeout.
Inference is suppressed during gaming or capture, foreground updates, critical
battery, memory pressure, and thermal pressure.

## Privacy and operation

Evidence is bounded and redacted before it reaches the model or history. Kyth
removes credentials, tokens, SSIDs, addresses, hardware addresses, usernames,
home paths, and filenames. Prompts are not retained and nothing is uploaded.
History contains only sanitized evidence, recipe identifiers, model metadata,
confidence, actions, and verification results; it rotates after 100 records or
30 days.

System Hub exposes controls on **System → Guardian** (self-healing dashboard). The Repair page links there. The equivalent CLI is:

```bash
kyth-guardian --json status
kyth-guardian --json inspect
kyth-guardian --json check
kyth-guardian --json investigate
kyth-guardian --json fix
kyth-guardian --json fix audio.restart
kyth-guardian --json history
kyth-guardian enable
kyth-guardian disable
kyth-guardian auto-fix on
kyth-guardian model install
kyth-guardian model remove
```

`check` is the timer path (auto-fix only after two consecutive failures). `inspect`
is the read-only snapshot used by System Hub live health — it never writes
history or occurrence counters, so opening the page cannot accelerate auto-fix.
`fix` is the user-initiated path used by System Hub → Guardian → Fix My System
or a per-recipe **Apply** button. Optional recipe ids apply that repair now:

```bash
kyth-guardian --json inspect
kyth-guardian --json fix
kyth-guardian --json fix audio.restart
```

The global `--json` option precedes the command.
