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

## Resource behavior

The user timer performs a bounded check every 15 minutes, while a systemd path
unit reacts when the shared user probe cache changes. Both start a oneshot
process; nothing polls continuously. The service runs at low CPU and I/O
priority with memory and CPU limits.

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
kyth-guardian --json check
kyth-guardian --json investigate
kyth-guardian --json history
kyth-guardian enable
kyth-guardian disable
kyth-guardian auto-fix on
kyth-guardian model install
kyth-guardian model remove
```

The global `--json` option precedes the command.
