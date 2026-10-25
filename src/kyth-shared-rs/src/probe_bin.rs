use std::env;

fn usage() {
    eprintln!("usage: kyth-probe [--system] [--print|--print-only] [-v|--verbose]");
}

fn main() -> std::process::ExitCode {
    let mut system = false;
    let mut print_json = false;
    let mut print_only = false;
    for argument in env::args().skip(1) {
        match argument.as_str() {
            "--system" => system = true,
            "--print" => print_json = true,
            "--print-only" => {
                print_json = true;
                print_only = true;
            }
            "-v" | "--verbose" => {}
            "-h" | "--help" => {
                usage();
                return std::process::ExitCode::SUCCESS;
            }
            _ => {
                usage();
                return std::process::ExitCode::from(2);
            }
        }
    }

    let fresh = if system {
        serde_json::Map::new()
    } else {
        kyth_shared::system::probe::fresh_system_sections()
    };
    let fresh_keys = fresh.keys().map(String::as_str).collect::<Vec<_>>();
    let mut skip = kyth_shared::system::probe::cacheable_sections_to_skip(&fresh_keys);
    if system {
        // P1: the two network-backed `flatpak remote-ls --updates` queries
        // (30s timeout each) stay off the boot-critical system probe. The
        // user timer refreshes this section within 10 minutes of login, and
        // the Hub falls back to a live query for a missing section.
        skip.extend(kyth_shared::system::probe::deferred_system_sections());
    }
    // F6: persist each completed section group as it lands. Collection is
    // otherwise all-or-nothing under the service's 120s TimeoutStartSec —
    // a slow machine killed mid-cycle would never refresh its cache at
    // all. The final update_sections below still writes the complete,
    // merged document; the streamed writes only make partial progress
    // durable. Best-effort: a failed batch write is retried implicitly by
    // that final write, so errors here are ignored.
    let mut persist_batch = |batch: &serde_json::Map<String, serde_json::Value>| {
        let _ = kyth_shared::system::probe::update_sections(batch, None, system);
    };
    let mut discard_batch = |_: &serde_json::Map<String, serde_json::Value>| {};
    let sink: &mut dyn FnMut(&serde_json::Map<String, serde_json::Value>) = if print_only {
        &mut discard_batch
    } else {
        &mut persist_batch
    };
    let mut sections = kyth_shared::system::probe::collect_snapshot_streaming(&skip, sink);
    kyth_shared::system::probe::merge_fresh_sections(&mut sections, fresh);
    if print_only {
        println!(
            "{}",
            serde_json::to_string_pretty(&sections).unwrap_or_else(|_| "{}".into())
        );
        return std::process::ExitCode::SUCCESS;
    }
    match kyth_shared::system::probe::update_sections(&sections, None, system) {
        Ok(path) => {
            eprintln!(
                "INFO: Wrote probe cache to {} ({} sections)",
                path.display(),
                sections.len()
            );
            if print_json {
                let value = serde_json::json!({"path": path, "sections": sections});
                println!(
                    "{}",
                    serde_json::to_string_pretty(&value).unwrap_or_else(|_| "{}".into())
                );
            }
            std::process::ExitCode::SUCCESS
        }
        Err(error) => {
            eprintln!("ERROR: could not write probe cache: {error}");
            std::process::ExitCode::from(1)
        }
    }
}
