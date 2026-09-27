//! Packaging-only KRunner entry generator from the React route manifest.
//!
//! Every entry launches the same Tauri shell, whose Wayland app-id is the
//! bundle identifier (`com.kythos.hub` in `src-tauri/tauri.conf.json`), so
//! every generated entry must declare it as `StartupWMClass` — otherwise
//! Plasma cannot group the window under the Hub icon and shows a generic
//! Wayland icon instead.

use serde::Deserialize;
use std::path::PathBuf;

/// Wayland app-id of the Tauri Hub shell; must match the bundle identifier.
pub const HUB_APP_ID: &str = "com.kythos.hub";

#[derive(Deserialize)]
struct Manifest {
    destinations: Vec<Destination>,
}
#[derive(Deserialize)]
struct Destination {
    sections: Vec<Section>,
}
#[derive(Deserialize)]
struct Section {
    key: String,
    title: String,
    description: String,
}

fn slug(value: &str) -> String {
    let mut result = String::new();
    let mut separator = false;
    for ch in value.chars() {
        if ch.is_ascii_alphanumeric() {
            if separator && !result.is_empty() {
                result.push('-');
            }
            result.push(ch.to_ascii_lowercase());
            separator = false;
        } else {
            separator = true;
        }
    }
    if result.is_empty() {
        "page".into()
    } else {
        result
    }
}

fn entry_content(section: &Section) -> String {
    format!("[Desktop Entry]\nType=Application\nNoDisplay=true\nName=Kyth Hub: {}\nComment={}\nKeywords={};{};\nExec=/usr/bin/kyth-welcome-launch --page \"{}\"\nIcon=kyth\nTerminal=false\nCategories=Settings;\nStartupWMClass={}\nX-KDE-StartupNotify=false\n", section.title, section.description, section.title, section.key, section.key, HUB_APP_ID)
}

fn entry_filename(section: &Section) -> String {
    format!("kyth-hub-{}.desktop", slug(&section.key))
}

fn main() -> Result<(), String> {
    let args = std::env::args().skip(1).collect::<Vec<_>>();
    if args.len() != 2 {
        return Err("usage: kyth-hub-desktop-entries MANIFEST DEST_DIR".into());
    }
    let manifest: Manifest =
        serde_json::from_str(&std::fs::read_to_string(&args[0]).map_err(|e| e.to_string())?)
            .map_err(|e| e.to_string())?;
    let destination = PathBuf::from(&args[1]);
    std::fs::create_dir_all(&destination).map_err(|e| e.to_string())?;
    for section in manifest
        .destinations
        .into_iter()
        .flat_map(|destination| destination.sections)
    {
        let content = entry_content(&section);
        let path = destination.join(entry_filename(&section));
        kyth_shared::atomic_io::atomic_write_text(path, &content, Some(0o644))
            .map_err(|e| e.to_string())?;
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn sample() -> Section {
        Section {
            key: "Update".into(),
            title: "Updates".into(),
            description: "Check OS updates.".into(),
        }
    }

    #[test]
    fn generated_entry_groups_under_the_hub_icon() {
        // Regression pin: without StartupWMClass=com.kythos.hub, Plasma
        // cannot match the Tauri window to any entry and shows a generic
        // Wayland icon in the task manager.
        let content = entry_content(&sample());
        assert!(
            content.contains(&format!("StartupWMClass={HUB_APP_ID}\n")),
            "generated entry must declare the Hub app-id: {content}"
        );
    }

    #[test]
    fn generated_entry_keeps_launch_contract() {
        let content = entry_content(&sample());
        assert!(content.contains("Exec=/usr/bin/kyth-welcome-launch --page \"Update\"\n"));
        assert!(content.contains("Icon=kyth\n"));
        assert!(content.contains("NoDisplay=true\n"));
        assert_eq!(entry_filename(&sample()), "kyth-hub-update.desktop");
    }
}
