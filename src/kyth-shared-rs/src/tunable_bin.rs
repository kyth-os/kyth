//! Read-only native tunable registry dispatcher.
//!
//! Mutation verbs are intentionally rejected until each tunable family has a
//! dedicated fixed-operation executor and rollback proof.

use std::env;

fn usage() -> ! {
    eprintln!("Usage: kyth-tunable --list | kyth-tunable <name> status");
    std::process::exit(2);
}

fn main() {
    let args: Vec<String> = env::args().skip(1).collect();
    let registry = kyth_shared::system::tunable_registry::load_registry(None::<&str>);
    if args == ["--list"] {
        for spec in registry.values() {
            println!("{}\t{}\t{}", spec.name, spec.kind, spec.module);
        }
        return;
    }
    let (name, verb) = match args.as_slice() {
        [name] => (name.as_str(), "status"),
        [name, verb] => (name.as_str(), verb.as_str()),
        _ => usage(),
    };
    let Some(spec) = kyth_shared::system::tunable_registry::get_spec(name, None::<&str>) else {
        eprintln!("Unknown tunable: {name}");
        std::process::exit(1);
    };
    if verb != "status" {
        eprintln!("Mutation verb '{verb}' is not available in the read-only native dispatcher");
        std::process::exit(3);
    }
    let drop_in = format!("/etc/sysctl.d/99-kyth-{}.conf", spec.name);
    let active = if spec.kind == "sysctl" {
        if std::path::Path::new(&drop_in).is_file() {
            "configured"
        } else {
            "absent"
        }
    } else {
        "unknown"
    };
    println!("profile=balanced active={active} kind={}", spec.kind);
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
}
