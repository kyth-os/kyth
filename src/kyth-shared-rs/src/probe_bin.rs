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
    let skip = kyth_shared::system::probe::cacheable_sections_to_skip(&fresh_keys);
    let mut sections = kyth_shared::system::probe::collect_snapshot_skipping(&skip);
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
