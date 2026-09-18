//! Native replacement for the Python `kyth-batteryd` launcher.
//!
//! Charge-threshold daemon: every 30 seconds it reloads the battery
//! config, applies the charge-start/stop thresholds to every controllable
//! battery, and appends a health snapshot to the (capped) ledger when
//! health checks are on. The config comes from the explicit system path
//! `/etc/kyth/battery.toml` (which the Hub syncs the user's file to),
//! falling back to the per-user file. Desktops without a controllable
//! battery exit 0 with a single log line instead of looping forever.
//! `battery.py` stays as the Phase 3 fixture.

use std::path::{Path, PathBuf};
use std::time::Duration;

use kyth_shared::system::battery::{
    append_ledger, apply_thresholds_in, battery_config_path, controllable_batteries_in,
    load_battery_with_fallback, read_battery_health, system_battery_config_path, LEDGER_PATH,
};

const POWER_SUPPLY_ROOT: &str = "/sys/class/power_supply";

fn main() -> std::process::ExitCode {
    let system_path = system_battery_config_path();
    let user_path = battery_config_path(None::<PathBuf>);
    if controllable_batteries_in(Path::new(POWER_SUPPLY_ROOT)).is_empty() {
        eprintln!("kyth-batteryd: no controllable battery found; exiting");
        return std::process::ExitCode::SUCCESS;
    }
    let ledger = PathBuf::from(LEDGER_PATH);
    loop {
        let config = load_battery_with_fallback(&system_path, &user_path);
        apply_thresholds_in(
            Path::new(POWER_SUPPLY_ROOT),
            config.charge_start,
            config.charge_stop,
        );
        if config.health_check {
            let _ = append_ledger(&ledger, &read_battery_health(), &config);
        }
        std::thread::sleep(Duration::from_secs(30));
    }
}
