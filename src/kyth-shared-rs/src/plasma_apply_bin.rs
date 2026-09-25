//! Native replacement for the Python `kyth-apply-plasma` launcher.
//!
//! Applies `plasma.toml` drift via `kwriteconfig` (6 → 5 → plain fallback
//! chain, as the Python launcher ordered it), reconfigures KWin over the
//! first answering `qdbus`, and stamps the TTL marker. Always exits `0`;
//! a missing `kwriteconfig` skips silently with `0 keys`.
//! `plasma_drift.py` stays as the Phase 3 fixture.

use std::path::Path;
use std::time::{SystemTime, UNIX_EPOCH};

use kyth_shared::atomic_io::atomic_write_text;
use kyth_shared::system::plasma_drift::{
    apply_sections, config_path, kwriteconfig_candidates, load, qdbus_candidates, reconfigure_argv,
    run_timeout, TTL_PATH, TTL_SECS,
};
use kyth_shared::system::process::{find_executable, run_bounded_success};

fn first_binary(names: &[&str]) -> Option<String> {
    names
        .iter()
        .find_map(|name| find_executable(name).map(|path| path.to_string_lossy().into_owned()))
}

fn reconfigure_kwin() {
    for name in qdbus_candidates() {
        let Some(qdbus) = find_executable(name).map(|path| path.to_string_lossy().into_owned())
        else {
            continue;
        };
        if run_bounded_success(&reconfigure_argv(&qdbus), run_timeout()) {
            return;
        }
    }
}

fn main() -> std::process::ExitCode {
    let sections = load(config_path(None::<&Path>));
    let mut applied = Vec::new();
    if let Some(binary) = first_binary(&kwriteconfig_candidates()) {
        applied = apply_sections(&sections, &binary, &|argv| {
            run_bounded_success(argv, run_timeout())
        });
        reconfigure_kwin();
        if let Ok(now) = SystemTime::now().duration_since(UNIX_EPOCH) {
            let _ = atomic_write_text(TTL_PATH, &(now.as_secs() + TTL_SECS).to_string(), None);
        }
    }
    println!("kyth-apply-plasma: {} keys", applied.len());
    std::process::ExitCode::SUCCESS
}
