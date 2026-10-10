/** v1 software selection catalog: curated Flatpak bundles + individual picks.
 *
 * Scoped tight per design: 4 bundles, ~12 individual apps, all Flatpak.
 * Distrobox-container-as-component is deferred until the Flatpak path proves itself.
 */

export interface FlatpakApp {
  id: string;
  name: string;
  description: string;
}

export interface SoftwareBundle {
  id: string;
  name: string;
  description: string;
  apps: FlatpakApp[];
}

export const SOFTWARE_BUNDLES: SoftwareBundle[] = [
  {
    id: "gaming",
    name: "Gaming",
    description: "Launchers and chat for your game library",
    apps: [
      { id: "com.valvesoftware.Steam", name: "Steam", description: "The biggest PC game store" },
      { id: "com.heroicgameslauncher.hgl", name: "Heroic", description: "Epic, GOG and Amazon games" },
      { id: "com.discordapp.Discord", name: "Discord", description: "Voice chat while you play" },
      { id: "org.prismlauncher.PrismLauncher", name: "Prism Launcher", description: "Minecraft launcher" },
    ],
  },
  {
    id: "development",
    name: "Development",
    description: "Editors and tools for building software",
    apps: [
      { id: "com.visualstudio.code", name: "VS Code", description: "Code editor" },
      { id: "io.dbeaver.DBeaverCommunity", name: "DBeaver", description: "Database browser" },
      { id: "io.podman_desktop.PodmanDesktop", name: "Podman Desktop", description: "Container management" },
    ],
  },
  {
    id: "creative",
    name: "Creative",
    description: "Make art, video and music",
    apps: [
      { id: "org.gimp.GIMP", name: "GIMP", description: "Image editor" },
      { id: "org.kde.kdenlive", name: "Kdenlive", description: "Video editor" },
      { id: "org.blender.Blender", name: "Blender", description: "3D modeling and animation" },
      { id: "org.audacityteam.Audacity", name: "Audacity", description: "Audio editor" },
    ],
  },
  {
    id: "productivity",
    name: "Productivity",
    description: "Office, browser and media",
    apps: [
      { id: "org.libreoffice.LibreOffice", name: "LibreOffice", description: "Office suite" },
      { id: "org.mozilla.firefox", name: "Firefox", description: "Web browser" },
      { id: "org.mozilla.Thunderbird", name: "Thunderbird", description: "Email client" },
      { id: "org.videolan.VLC", name: "VLC", description: "Media player" },
    ],
  },
];

/** Individual picks not covered by any bundle. */
export const INDIVIDUAL_APPS: FlatpakApp[] = [
  { id: "com.spotify.Client", name: "Spotify", description: "Music streaming" },
  { id: "org.telegram.desktop", name: "Telegram", description: "Messaging" },
  { id: "com.slack.Slack", name: "Slack", description: "Team chat" },
  { id: "us.zoom.Zoom", name: "Zoom", description: "Video calls" },
  { id: "org.keepassxc.KeePassXC", name: "KeePassXC", description: "Password manager" },
  { id: "org.gnome.Calculator", name: "Calculator", description: "Desktop calculator" },
  { id: "org.gnome.TextEditor", name: "Text Editor", description: "Simple text editor" },
  { id: "io.github.zen_browser.zen", name: "Zen Browser", description: "Minimalist browser" },
  { id: "com.github.tchx84.Flatseal", name: "Flatseal", description: "Flatpak permissions" },
  { id: "org.flameshot.Flameshot", name: "Flameshot", description: "Screenshots" },
  { id: "com.obsproject.Studio", name: "OBS Studio", description: "Streaming and recording" },
  { id: "org.inkscape.Inkscape", name: "Inkscape", description: "Vector graphics" },
];

/** All known app IDs, for validation. */
export const ALL_APP_IDS: Set<string> = new Set([
  ...SOFTWARE_BUNDLES.flatMap((b) => b.apps.map((a) => a.id)),
  ...INDIVIDUAL_APPS.map((a) => a.id),
]);
