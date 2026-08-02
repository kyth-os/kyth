# KythOS Stability Principles

KythOS runs close to the edge, but never without a way back.

The project personality is: Performance, Stability, Reliability, Kyth. Those
words are not four equal slogans. They are an engineering stack:

1. Reliability: the user can recover.
2. Stability: the desktop stays calm.
3. Performance: the machine gets fast when it matters.
4. Kyth: the system is opinionated, visible, and humane.

## Reliability

Reliability means every risky feature has a recovery path. Atomic updates,
rollback deployments, post-update checks, and System Hub diagnostics are not
extras; they are the reason KythOS can carry newer kernels, sched-ext, NTSYNC,
gaming helpers, and hardware-specific defaults without turning daily use into a
coin toss.

Engineering rules:

- Boot, login, network, audio, GPU, update, and installer changes need a smoke
  check or a clear diagnostic path.
- Background automation must write readable status when practical.
- A cutting-edge default should have an obvious disable, retry, or rollback path.
- Release validation should always include update, rollback, suspend/resume,
  network reconnect, audio, Vulkan, and System Hub navigation.
- A repeatedly unhealthy image digest must be quarantined so a mutable channel
  tag cannot immediately reinstall the deployment greenboot rolled back.

## Stability

Stability means the desktop should not surprise the user. The machine may be
aggressive while a game is running, but idle desktop behavior should be quiet,
predictable, and easy to explain.

Engineering rules:

- Background jobs should be delayed after boot, low priority, and cancellable or
  retryable where possible.
- Global environment variables and system-wide hooks are suspect by default.
  Prefer per-app overrides, launch presets, or System Hub toggles.
- Performance mode must be stateful: save the user's current state before
  changing power profiles, compositor behavior, or CPU policy, then restore it.
- A launcher being open is not the same as a game running.

## Performance

Performance means KythOS is fast in the moments users feel: game launch,
shader-heavy loads, frame pacing, network play, update staging, suspend/resume,
and recovery after something breaks.

Engineering rules:

- Prefer targeted performance activation over always-on heat.
- Keep gaming fast paths available: GameMode, sched-ext, NTSYNC, Gamescope,
  MangoHud, vkBasalt, GE-Proton, and hardware helpers.
- Validate performance tweaks against desktop side effects, not only frame rate.
- Document when a tuning choice is experimental or hardware-sensitive.

## Kyth

KythOS should feel opinionated without being mysterious. The system can make
strong choices, but it should show its work.

Engineering rules:

- System Hub should explain what mode the system is in and why.
- Repair tools should prefer narrow fixes over broad resets.
- Diagnostics should turn hidden state into readable facts.
- User-facing defaults should be useful on day one and reversible on day two.

## Default Checklist

Before accepting a change that touches stability-sensitive behavior, ask:

- Can the user recover if this goes wrong?
- Does this run during login, boot, gameplay, suspend, or update activation?
- Does it alter global app behavior?
- Is it low priority if it runs in the background?
- Can System Hub or `kyth-smoke-check` explain the resulting state?
- Does it preserve KythOS' cutting-edge character without making the desktop
  noisy, hot, or brittle?
