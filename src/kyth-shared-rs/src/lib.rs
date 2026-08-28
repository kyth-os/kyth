//! Rust port of `kyth_shared` (`src/kyth_shared`) — the Python library
//! ~200 kyth-welcome pages, ujust recipes, and systemd units share for
//! host tuning. Porting all of it in one pass isn't realistic or safe:
//! much of it touches privileged/hardware operations (GPU switching, VPN,
//! installer disk ops) — exactly the kind of thing CLAUDE.md already
//! flags as high-risk. See `MIGRATION.md` (repo root of this crate) for
//! the actual scope and how more of `kyth_shared` moves over.
//!
//! This first slice ports exactly what was already proven safe as
//! read-only bridges shelled out to from the Kyth Hub's Tauri shell
//! (`src-tauri/backend/*.py`) — now retired in favor of calling these
//! modules directly, in-process, no subprocess/JSON round trip. Every
//! module here is read-only against real on-disk/system state: nothing
//! mutates, nothing needs root, nothing runs a "live" probe sweep (see
//! `guardian::load_state`'s docs for why that boundary matters).

pub mod guardian;
pub mod system;
