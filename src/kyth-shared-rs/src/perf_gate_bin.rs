//! Native CLI for the runtime perf-gate recipe.

use std::env;
use std::path::Path;

use kyth_shared::system::perf_gate::{check, config_path, load, PerfGateResult};

const LEDGER: &str = "/var/cache/kyth/perf-ledger.jsonl";

fn print_result(result: &PerfGateResult) {
    println!(
        "{}",
        serde_json::to_string_pretty(result).unwrap_or_else(|_| "{}".into())
    );
}

fn usage() {
    eprintln!("usage: kyth-perf-gate [status] [--current-ms <milliseconds>]");
}

fn main() -> std::process::ExitCode {
    let mut current_ms = None;
    let mut args = env::args().skip(1);
    while let Some(argument) = args.next() {
        match argument.as_str() {
            "status" => {}
            "--current-ms" => {
                let Some(value) = args.next() else { usage(); return std::process::ExitCode::from(2); };
                current_ms = match value.parse::<f64>() {
                    Ok(value) => Some(value),
                    Err(_) => { usage(); return std::process::ExitCode::from(2); }
                };
            }
            "-h" | "--help" => { usage(); return std::process::ExitCode::SUCCESS; }
            _ => { usage(); return std::process::ExitCode::from(2); }
        }
    }
    let result = check(load(config_path(None::<&Path>)), current_ms, Path::new(LEDGER));
    print_result(&result);
    if result.enabled && !result.pass { std::process::ExitCode::from(1) } else { std::process::ExitCode::SUCCESS }
}
