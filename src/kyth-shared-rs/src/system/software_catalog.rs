//! Static App Store catalogs — ports `src/kyth-welcome/services/software_catalogs.py`.
//! Pure data, no I/O, no root. The Python page composes these into the
//! "Starter Packs" / "Familiar Apps" choosers; the web Hub reads the same
//! lists via `starter_packs` / `familiar_apps` Tauri commands so a single
//! place can evolve curated app IDs without touching widget code.

use serde::Serialize;

#[derive(Debug, Clone, Serialize)]
pub struct CatalogApp {
    pub id: String,
    pub label: String,
    pub selected: bool,
    pub description: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct StarterPack {
    pub name: String,
    pub desc: String,
    pub apps: Vec<CatalogApp>,
}

pub fn starter_packs() -> Vec<StarterPack> {
    vec![
        StarterPack {
            name: "Gaming".to_string(),
            desc: "Steam, Epic/GOG, compatibility launchers, saves, and standalone .exe support.".to_string(),
            apps: vec![
                CatalogApp { id: "com.valvesoftware.Steam".to_string(), label: "Steam".to_string(), selected: true, description: "Digital game store and library for Windows and Linux-native titles.".to_string() },
                CatalogApp { id: "com.heroicgameslauncher.hgl".to_string(), label: "Heroic Games Launcher".to_string(), selected: true, description: "Launcher for Epic Games Store and GOG libraries.".to_string() },
                CatalogApp { id: "net.lutris.Lutris".to_string(), label: "Lutris".to_string(), selected: true, description: "Open-source game manager for Windows, GOG, Amazon, and emulated titles.".to_string() },
                CatalogApp { id: "com.usebottles.bottles".to_string(), label: "Bottles".to_string(), selected: true, description: "Run Windows software and games in isolated, sandboxed prefixes.".to_string() },
                CatalogApp { id: "com.github.mtkennerly.ludusavi".to_string(), label: "Ludusavi".to_string(), selected: true, description: "Back up and restore PC game save files across hundreds of titles.".to_string() },
            ],
        },
        StarterPack {
            name: "Creator".to_string(),
            desc: "Streaming, editing, audio, images, and 3D creation.".to_string(),
            apps: vec![
                CatalogApp { id: "com.obsproject.Studio".to_string(), label: "OBS Studio".to_string(), selected: true, description: "Screen recording and live streaming with obs-vkcapture-ready game capture.".to_string() },
                CatalogApp { id: "org.kde.kdenlive".to_string(), label: "Kdenlive".to_string(), selected: true, description: "Open-source non-linear video editor.".to_string() },
                CatalogApp { id: "org.audacityteam.Audacity".to_string(), label: "Audacity".to_string(), selected: true, description: "Multi-track audio editor and recorder.".to_string() },
                CatalogApp { id: "org.gimp.GIMP".to_string(), label: "GIMP".to_string(), selected: true, description: "GNU Image Manipulation Program.".to_string() },
                CatalogApp { id: "org.blender.Blender".to_string(), label: "Blender".to_string(), selected: true, description: "3D modeling, animation, and rendering suite.".to_string() },
            ],
        },
        StarterPack {
            name: "Everyday".to_string(),
            desc: "Browser, chat, media, passwords, app management, and local file sharing.".to_string(),
            apps: vec![
                CatalogApp { id: "com.brave.Browser".to_string(), label: "Brave Browser".to_string(), selected: true, description: "Privacy-focused web browser.".to_string() },
                CatalogApp { id: "com.discordapp.Discord".to_string(), label: "Discord".to_string(), selected: true, description: "Voice, video, and text chat for communities.".to_string() },
                CatalogApp { id: "org.videolan.VLC".to_string(), label: "VLC".to_string(), selected: true, description: "Plays virtually any video or audio file format.".to_string() },
                CatalogApp { id: "com.spotify.Client".to_string(), label: "Spotify".to_string(), selected: true, description: "Stream music, podcasts, and playlists.".to_string() },
                CatalogApp { id: "org.localsend.localsend_app".to_string(), label: "LocalSend".to_string(), selected: true, description: "Send files to nearby devices over the local network.".to_string() },
            ],
        },
    ]
}

#[derive(Debug, Clone, Serialize)]
pub struct FamiliarApp {
    pub windows_name: String,
    pub description: String,
    pub flatpak_id: String,
}

/// Curated “Windows → Koji” map — same list as `FAMILIAR_APPS` in Python, trimmed to
/// the most-searched entries so the bridge stays fast. Full list remains in Python for
/// the Qt Hub’s typeahead; this is enough for the web Hub’s fallback chooser.
pub fn familiar_apps() -> Vec<FamiliarApp> {
    vec![
        FamiliarApp { windows_name: "Photoshop".to_string(), description: "Use GIMP for photo editing and compositing.".to_string(), flatpak_id: "org.gimp.GIMP".to_string() },
        FamiliarApp { windows_name: "Office".to_string(), description: "LibreOffice is the drop-in Office suite.".to_string(), flatpak_id: "org.libreoffice.LibreOffice".to_string() },
        FamiliarApp { windows_name: "Steam".to_string(), description: "Install Steam from Flatpak.".to_string(), flatpak_id: "com.valvesoftware.Steam".to_string() },
        FamiliarApp { windows_name: "Discord".to_string(), description: "Install Discord from Flatpak.".to_string(), flatpak_id: "com.discordapp.Discord".to_string() },
        FamiliarApp { windows_name: "Spotify".to_string(), description: "Install Spotify from Flatpak.".to_string(), flatpak_id: "com.spotify.Client".to_string() },
        FamiliarApp { windows_name: "VLC".to_string(), description: "Install VLC from Flatpak — plays everything.".to_string(), flatpak_id: "org.videolan.VLC".to_string() },
        FamiliarApp { windows_name: "Chrome".to_string(), description: "Use Brave Browser for a familiar Chromium experience.".to_string(), flatpak_id: "com.brave.Browser".to_string() },
        FamiliarApp { windows_name: "GeForce Experience".to_string(), description: "NVIDIA driver settings live in the Control Center — no extra app needed.".to_string(), flatpak_id: "".to_string() },
    ]
}
