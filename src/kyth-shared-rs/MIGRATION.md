# Migrating kyth_shared to Rust

`src/kyth_shared` (Python) is ~200 modules covering everything from GPU
switching and VPN connection management to installer disk partitioning,
SELinux policy, and systemd unit management. Porting all of it in one pass
isn't realistic, and doing it carelessly is actively dangerous — a lot of
it is exactly what CLAUDE.md already calls out as high-risk (installer,
GPU setup, anything privileged). This crate is not that port. It's the
starting point for one, done incrementally, module by module, read-only
before mutating.

## What's ported so far

The read-only bridges and pure helpers the Kyth Hub's Tauri shell
(`src/kyth-hub-web/src-tauri`) used to shell out to Python subprocesses
for — see `src/kyth-hub-web/src-tauri/src/main.rs`'s `probe_backend`,
`guardian_snapshot`, `hardware_snapshot`, `storage_snapshot` commands:

| This crate | Ports the read path of | Behavior deliberately NOT ported |
|---|---|---|
| `system::probe` | `kyth_shared.system.probe` | The collector/write side (`collect_snapshot`, `write_cache_file`) — `kyth-probe.service` stays Python and keeps writing the cache this reads. |
| `guardian` | `kyth_shared.guardian` | `collect_symptoms()`/`inspect()` — the live probe sweep (a dozen-plus subprocess calls across audio/network/bluetooth/portal/...). Also not ported: `execute_recipe`, `save_state`, anything that acts. |
| `system::gpu` | `kyth_shared.system.gpu` | `loaded_kernel_modules`, `rpm_package_installed`, `query_nvidia_smi` — only `lspci_gpu_lines` had a caller. |
| `system::storage` | (new — was inline Python in the retired `storage_bridge.py`, not really "kyth_shared") | — |
| `system::boot_health` | read/policy surface of `kyth_shared.boot_health` | State transitions, atomic persistence, boot verification, and rollback remain Python-owned. |
| `diagnostics_scrub` | `kyth_shared.diagnostics_scrub.scrub_logs` | Collection, upload, and report composition remain outside the crate. |

Every function ported is a pure read against on-disk state or a single
cheap subprocess call (`lspci`) — nothing here needs root, nothing mutates
anything, nothing runs a live multi-probe sweep. That boundary is
deliberate and load-bearing: it's what makes calling straight into this
crate from a long-running GUI process safe by construction, the same way
the retired Python bridge scripts were safe as one-shot subprocesses.
Don't add a mutating or heavy-probe function to this crate without
re-thinking that boundary first.

## How more of it moves over

One module (or one function) at a time, in this order of preference:

1. **Read-only first.** A function that reads a file, a cache, or runs one
   cheap command and returns data is a good candidate. A function that
   writes state, executes a repair, or runs a probe sweep is not — do
   those later, once there's a real reason (a Rust caller that needs it)
   and real test coverage proving parity with the Python original.
2. **Port faithfully, not "improved."** Match the Python original's
   behavior exactly, including its quirks (see `system::gpu`'s doc comment
   for a real example — `lspci_gpu_lines`'s substring-match gotcha is
   preserved on purpose). Fix bugs as a separate, deliberate, reviewed
   change — not silently as part of a port, where it's easy to miss that
   the behavior changed at all.
3. **Test parity, not just "it compiles."** Every module here has
   `#[cfg(test)]` unit tests exercising the same scenarios the retired
   Python bridge tests (`tests/test_kyth_hub_shell_bridges.py`, since
   deleted — check git history for the shape) covered, using an explicit
   path/state parameter rather than mutating process-global env vars (see
   `system::probe::read_section_in` / `guardian::load_state_from`) — keeps
   tests parallel-safe and avoids flakiness from shared mutable env state.
4. **The Python module stays authoritative until its Rust port is proven.**
   Nothing here deletes or stops calling the Python original elsewhere in
   the codebase (kyth-welcome, ujust recipes, systemd units all keep using
   `kyth_shared` directly) — this crate is additive, a second consumer path
   for the Tauri shell specifically, not a replacement deployed everywhere
   at once.

## Why a separate crate instead of folding into kyth-hub-shell

Because the Tauri shell isn't going to be the only Rust consumer forever —
keeping this as its own crate (`kyth-shared`, a plain path dependency, no
workspace yet — see `src-tauri/Cargo.toml`) means the next Rust thing that
needs `kyth_shared` reads doesn't need to depend on a GUI shell binary to
get them.
