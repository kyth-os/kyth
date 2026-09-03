//! Read-only native tunable registry dispatcher.
//!
//! Mutation verbs are intentionally rejected until each tunable family has a
//! dedicated fixed-operation executor and rollback proof.

use std::{env, path::PathBuf};

fn usage() -> ! {
    eprintln!("Usage: kyth-tunable --list | kyth-tunable <name> [status|render] [--config PATH] [--dest PATH] [--profile PROFILE]");
    std::process::exit(2);
}

fn option(args: &[String], name: &str) -> Option<PathBuf> {
    args.windows(2)
        .find(|pair| pair[0] == name)
        .map(|pair| PathBuf::from(&pair[1]))
}

fn profile_option(args: &[String]) -> Option<kyth_shared::system::tuning_profile::Profile> {
    args.windows(2)
        .find(|pair| pair[0] == "--profile")
        .map(|pair| kyth_shared::system::sysctl_profiles::normalize_profile(Some(&pair[1])))
}

fn positional_args(args: &[String]) -> Vec<String> {
    let mut positional = Vec::new();
    let mut skip_value = false;
    for arg in args {
        if skip_value {
            skip_value = false;
        } else if matches!(arg.as_str(), "--config" | "--dest" | "--profile") {
            skip_value = true;
        } else {
            positional.push(arg.clone());
        }
    }
    positional
}

fn main() {
    let argv0 = env::args().next().unwrap_or_else(|| "kyth-tunable".into());
    let invoked_name = std::path::Path::new(&argv0)
        .file_name()
        .and_then(|v| v.to_str())
        .unwrap_or("kyth-tunable");
    let raw_args: Vec<String> = env::args().skip(1).collect();
    let args = positional_args(&raw_args);
    let registry = kyth_shared::system::tunable_registry::load_registry(None::<&str>);
    if args == ["--list"] {
        for spec in registry.values() {
            println!("{}\t{}\t{}", spec.name, spec.kind, spec.module);
        }
        return;
    }
    let (name, verb) = match args.as_slice() {
        [] if invoked_name != "kyth-tunable" => (invoked_name, "status"),
        [verb] if invoked_name != "kyth-tunable" => (invoked_name, verb.as_str()),
        [name] => (name.as_str(), "status"),
        [name, verb] => (name.as_str(), verb.as_str()),
        _ => usage(),
    };
    let Some(spec) = kyth_shared::system::tunable_registry::get_spec(name, None::<&str>) else {
        eprintln!("Unknown tunable: {name}");
        std::process::exit(1);
    };
    if !matches!(verb, "status" | "render") {
        eprintln!("Mutation verb '{verb}' is not available in the read-only native dispatcher");
        std::process::exit(3);
    }
    let config = option(&raw_args, "--config");
    let destination = option(&raw_args, "--dest");
    let profile = profile_option(&raw_args);
    if verb == "render" {
        if spec.kind != "sysctl" {
            eprintln!(
                "render is unavailable for model-only tunable '{}'; no file was written",
                spec.name
            );
            std::process::exit(4);
        }
        let Some(result) = kyth_shared::system::sysctl_profiles::generate_tunable(
            &spec.name,
            config.as_deref(),
            destination.as_deref(),
            profile,
        ) else {
            eprintln!(
                "No native render model exists for '{}'; no file was written",
                spec.name
            );
            std::process::exit(4);
        };
        match result {
            Ok(Some(path)) => println!("rendered={}", path.display()),
            Ok(None) => println!("rendered=none"),
            Err(error) => {
                eprintln!("render failed: {error}");
                std::process::exit(1);
            }
        }
        return;
    }
    let active_path = destination.as_deref();
    let normalized =
        kyth_shared::system::sysctl_profiles::load_tunable(&spec.name, config.as_deref());
    let active = kyth_shared::system::sysctl_profiles::status_tunable(&spec.name, active_path);
    match (normalized, active) {
        (Some(profile), Some(active)) => println!(
            "profile={} active={} kind={}",
            profile.as_str(),
            active.as_str(),
            spec.kind
        ),
        _ => println!("profile=unknown active=unknown kind={}", spec.kind),
    }
}

#[cfg(test)]
mod tests {
    #[test]
    fn registry_has_expected_complete_split() {
        let path = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("../../build_files/config/tunables.toml");
        let specs = kyth_shared::system::tunable_registry::list_tunables(Some(&path));
        assert_eq!(specs.len(), 94);
        assert_eq!(
            specs.iter().filter(|spec| spec.kind == "sysctl").count(),
            49
        );
        assert_eq!(specs.iter().filter(|spec| spec.kind == "other").count(), 45);
    }

    #[test]
    fn native_render_models_are_explicitly_counted() {
        let specs = kyth_shared::system::tunable_registry::list_tunables(Some(
            &std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
                .join("../../build_files/config/tunables.toml"),
        ));
        let modeled = specs
            .iter()
            .filter(|spec| {
                kyth_shared::system::sysctl_profiles::profile_config_for_tunable(&spec.name)
                    .is_some()
            })
            .count();
        assert_eq!(modeled, 44);
    }
}
