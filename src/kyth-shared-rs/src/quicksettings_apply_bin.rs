//! Native replacement for the Python `kyth-apply-quicksettings` launcher.
//!
//! Applies the QuickSettings brightness via PowerDevil over the available
//! `qdbus6`/`qdbus-qt6`/`qdbus` binary and stamps the best-effort TTL marker.
//! Always exits `0`; missing or failed `qdbus`
//! simply records no note. One deliberate deviation: an unparseable
//! `brightness` value falls back to `80` instead of aborting with a
//! traceback — crashing on a user config typo is a bug, not a contract.
//! `quicksettings.py` stays as the Phase 3 fixture.

use std::path::Path;
use std::time::{Duration, SystemTime, UNIX_EPOCH};

use kyth_shared::atomic_io::atomic_write_text;
use kyth_shared::system::plasma_drift::qdbus_candidates;
use kyth_shared::system::process::{find_executable, run_bounded_success};
use kyth_shared::system::quicksettings::{brightness_argv, config_path, load, TTL_PATH, TTL_SECS};

fn main() -> std::process::ExitCode {
    let config = load(config_path(None::<&Path>));
    let mut applied = Vec::new();
    for candidate in qdbus_candidates() {
        let Some(binary) = find_executable(candidate) else {
            continue;
        };
        let argv = brightness_argv(&binary.to_string_lossy(), config.brightness);
        if run_bounded_success(&argv, Duration::from_secs(5)) {
            applied.push("brightness".to_string());
            break;
        }
    }
    if let Ok(now) = SystemTime::now().duration_since(UNIX_EPOCH) {
        let _ = atomic_write_text(TTL_PATH, &(now.as_secs() + TTL_SECS).to_string(), None);
    }
    println!("kyth-apply-quicksettings: {}", applied.len());
    std::process::ExitCode::SUCCESS
}
