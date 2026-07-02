#!/bin/bash

set -euo pipefail

# ── Display / resolution auto-detection ──────────────────────────────────────
# First-login autostart: run kscreen-doctor to set all outputs to their
# preferred (auto) mode.  Works for both hardware and VMs.  Removes itself
# so it only fires once per user.
mkdir -p /etc/skel/.config/autostart
cat >/etc/skel/.config/autostart/kyth-set-resolution.desktop <<'RESEOF'
[Desktop Entry]
Type=Application
Name=KythOS: Set display resolution
Exec=/usr/bin/kyth-set-resolution
X-KDE-autostart-after=panel
Hidden=false
NoDisplay=true
RESEOF

cat >/usr/bin/kyth-set-resolution <<'SCRIPTEOF'
#!/usr/bin/env python3
# Set every connected output to its preferred (first-listed) mode.
# kscreen-doctor -o output format:
#   Output: 1 Virtual-1 enabled connected
#     Modes: 1:1920x1080@60  2:1280x720@60  ...
# Runs once on first login per user, then removes itself.

import os, re, subprocess, time

# Give KDE's display stack time to fully initialize before querying
time.sleep(3)

result = subprocess.run(['kscreen-doctor', '-o'], capture_output=True, text=True)

current_output = None
for line in result.stdout.splitlines():
    line = line.strip()
    # Match "Output: 1 Virtual-1 enabled connected" — name is the second word
    m = re.match(r'^Output:\s+\d+\s+(\S+)', line)
    if m:
        current_output = m.group(1)
        continue
    # Match "Modes: 1:1920x1080@60  2:..." — first mode is the preferred resolution
    if current_output and re.match(r'^Modes:', line):
        modes = re.findall(r'\d+:(\d+x\d+@[\d.]+)', line)
        if modes:
            subprocess.run([
                'kscreen-doctor',
                f'output.{current_output}.enable',
                f'output.{current_output}.mode.{modes[0]}',
            ], check=False)
        current_output = None

autostart = os.path.expanduser('~/.config/autostart/kyth-set-resolution.desktop')
try:
    os.unlink(autostart)
except OSError:
    pass
SCRIPTEOF
chmod +x /usr/bin/kyth-set-resolution

write_kyth_os_release() {
	local target=$1
	mkdir -p "$(dirname "${target}")"
	cat >"${target}" <<'EOF'
NAME="KythOS"
PRETTY_NAME="KythOS 44"
ID=kythos
VERSION="44"
VERSION_ID="44"
ANSI_COLOR="0;34"
LOGO=kyth
HOME_URL="https://github.com/mrtrick37/kyth"
SUPPORT_URL="https://github.com/mrtrick37/kyth/discussions"
BUG_REPORT_URL="https://github.com/mrtrick37/kyth/issues"
EOF
}

# Ensure the built image advertises the KythOS product name. Some boot/installer
# menus and early-boot overlays derive their display strings from os-release.
# Fedora keeps the canonical file in /usr/lib, while some consumers read /etc
# directly, so write both with only KythOS product identity.
write_kyth_os_release /usr/lib/os-release
rm -f /etc/os-release
write_kyth_os_release /etc/os-release

# ── Topgrade config for all new users ────────────────────────────────────────
# Disable rpm-ostree step: on a bootc system rpm-ostree upgrade pulls from the
# upstream Kinoite ostree remote, not the KythOS container registry.
# Replace it with a bootc upgrade custom step so topgrade does the right thing.
mkdir -p /etc/skel/.config
cat >/etc/skel/.config/topgrade.toml <<'TOPGRADEEOF'
[misc]
# system (dnf5) is read-only on bootc — disable it; bootc upgrade is used instead.
# distrobox: disabled because distrobox-upgrade --all fails without a PTY.
#   Update containers manually with: distrobox-upgrade --all
# containers: podman container updates fail on a bootc read-only system.
# toolbx: kyth-dev is managed via ujust, not topgrade; toolbx version-compat
#   checks will fail the whole topgrade run if the container needs recreation.
# topgrade is baked into the KythOS image; refresh it through image updates.
no_self_update = true
disable = ["system", "distrobox", "containers", "toolbx"]

[commands]
# -n makes sudo fail fast if it can't run non-interactively, rather than hanging
# waiting for a password. NOPASSWD is granted in /etc/sudoers.d/kyth-bootc.
"KythOS system update" = "sudo -n bootc upgrade"
"KythOS rclone update" = "sudo -n /usr/bin/kyth-rclone-update"
TOPGRADEEOF

# ── Default shell environment for all new users ───────────────────────────────
# /etc/skel/.zshrc seeds a polished zsh experience out-of-box. Every tool
# integration is conditional so the file works identically whether the optional
# packages were installed or not.
# Also seeds /etc/skel/.bashrc with the same modern tool aliases for bash users.
cat >/etc/skel/.zshrc <<'ZSHRCEOF'
# KythOS default zsh config — edit freely, it's yours.

# History: large buffer, no duplicates, shared across sessions
HISTFILE=~/.zsh_history
HISTSIZE=100000
SAVEHIST=100000
setopt HIST_IGNORE_DUPS HIST_IGNORE_SPACE SHARE_HISTORY INC_APPEND_HISTORY

# Modern tool aliases — each falls back gracefully when the tool is absent
if command -v eza >/dev/null 2>&1; then
    alias ls='eza --group-directories-first --icons=auto'
    alias ll='eza -la --group-directories-first --icons=auto'
    alias lt='eza --tree --group-directories-first'
else
    alias ll='ls -la'
fi
command -v bat  >/dev/null 2>&1 && alias cat='bat --paging=never'
command -v rg   >/dev/null 2>&1 && alias search='rg'

# zsh-autosuggestions (fish-like inline suggestions)
[[ -f /usr/share/zsh-autosuggestions/zsh-autosuggestions.zsh ]] &&
    source /usr/share/zsh-autosuggestions/zsh-autosuggestions.zsh

# fzf key bindings (Ctrl+R history, Ctrl+T file picker, Alt+C cd)
[[ -f /usr/share/fzf/shell/key-bindings.zsh ]] &&
    source /usr/share/fzf/shell/key-bindings.zsh
[[ -f /usr/share/fzf/shell/completion.zsh ]] &&
    source /usr/share/fzf/shell/completion.zsh

# zoxide — smarter cd with frecency-ranked jump (z foo, zi interactive)
command -v zoxide >/dev/null 2>&1 && eval "$(zoxide init zsh)"

# Starship prompt — must come last to override any prompt set above
command -v starship >/dev/null 2>&1 && eval "$(starship init zsh)"

# zsh-syntax-highlighting — must be sourced after all other init (Zle hook)
[[ -f /usr/share/zsh-syntax-highlighting/zsh-syntax-highlighting.zsh ]] &&
    source /usr/share/zsh-syntax-highlighting/zsh-syntax-highlighting.zsh
ZSHRCEOF

# Also seed a .bashrc that picks up the same modern tool aliases so bash
# users benefit without switching shells.
cat >/etc/skel/.bashrc <<'BASHRCEOF'
# KythOS default bash config — edit freely, it's yours.

# Source system-wide config (Fedora bash completion, PATH additions, etc.)
[[ -f /etc/bashrc ]] && source /etc/bashrc

# Sensible history defaults
HISTSIZE=100000
HISTFILESIZE=200000
HISTCONTROL=ignoredups:erasedups
shopt -s histappend

# Modern tool aliases
if command -v eza >/dev/null 2>&1; then
    alias ls='eza --group-directories-first --icons=auto'
    alias ll='eza -la --group-directories-first --icons=auto'
    alias lt='eza --tree --group-directories-first'
else
    alias ll='ls -la'
fi
command -v bat  >/dev/null 2>&1 && alias cat='bat --paging=never'
command -v rg   >/dev/null 2>&1 && alias search='rg'

# fzf key bindings
[[ -f /usr/share/fzf/shell/key-bindings.bash ]] &&
    source /usr/share/fzf/shell/key-bindings.bash

# zoxide
command -v zoxide >/dev/null 2>&1 && eval "$(zoxide init bash)"

# Starship prompt
command -v starship >/dev/null 2>&1 && eval "$(starship init bash)"
BASHRCEOF

# System-wide git-delta pager config — makes `git diff`, `git log`, and
# `git show` output beautiful syntax-highlighted diffs with line numbers.
# delta is the pager; any user can override in their own ~/.gitconfig.
cat >/etc/gitconfig <<'GITCONFIGEOF'
[core]
    pager = delta

[interactive]
    diffFilter = delta --color-only

[delta]
    navigate = true
    dark = true
    line-numbers = true
    syntax-theme = OneHalfDark

[merge]
    conflictstyle = diff3

[diff]
    colorMoved = default
GITCONFIGEOF

# ── Fish shell default config ──────────────────────────────────────────────────
# Fish has out-of-box syntax highlighting and autosuggestions — no plugins needed.
# New users who choose fish (chsh -s /usr/bin/fish) get a polished experience.
mkdir -p /etc/skel/.config/fish
cat >/etc/skel/.config/fish/config.fish <<'FISHCONFIGEOF'
# KythOS fish config — edit freely, it's yours.

# Starship cross-shell prompt
if command -q starship
    starship init fish | source
end

# Smarter cd (zoxide) — tracks frecency, `z dir` jumps to most-used match
if command -q zoxide
    zoxide init fish | source
end

# fzf key bindings (Ctrl+R history search, Ctrl+T file search, Alt+C cd)
if test -f /usr/share/fzf/shell/key-bindings.fish
    source /usr/share/fzf/shell/key-bindings.fish
end

# Modern CLI aliases with graceful fallbacks
if command -q eza
    alias ls='eza --color=auto --group-directories-first --icons=auto'
    alias ll='eza -la --color=auto --group-directories-first --icons=auto --git'
    alias lt='eza --tree --color=auto --icons=auto -L 2'
end
if command -q bat
    alias cat='bat --paging=never'
end
if command -q rg
    alias search='rg'
end

# Abbreviations (fish's smarter alias — expands on Enter, not inline)
abbr --add g    git
abbr --add gst  'git status'
abbr --add gd   'git diff'
abbr --add gcm  'git commit -m'
abbr --add gp   'git push'
abbr --add gl   'git log --oneline --graph --decorate -20'

# History: keep a large, deduplicated history
set -U fish_history_size 100000

# Suppress the fish greeting
set -U fish_greeting ""
FISHCONFIGEOF

# ── KythDark color scheme ─────────────────────────────────────────────────────
# Tokyo Night-derived palette: #0c0e16 dark slate base, #4f8cff Kyth blue accent.
# All nine Color:* sections share the same palette so colors are consistent
# across button, view, window, selection, tooltip, and header contexts.
mkdir -p /usr/share/color-schemes
cat >/usr/share/color-schemes/KythDark.colors <<'KYTHCOLORSEOF'
[ColorEffects:Disabled]
Color=56,56,56
ColorAmount=0
ColorEffect=0
ContrastAmount=0.65
ContrastEffect=1
IntensityAmount=0.1
IntensityEffect=2

[ColorEffects:Inactive]
ChangeSelectionColor=true
Color=112,111,110
ColorAmount=0.025
ColorEffect=2
ContrastAmount=0.1
ContrastEffect=2
Enable=false
IntensityAmount=0
IntensityEffect=0

[Colors:Button]
BackgroundAlternate=22,24,36
BackgroundNormal=18,20,31
DecorationFocus=79,140,255
DecorationHover=143,184,255
ForegroundActive=192,202,245
ForegroundInactive=86,95,137
ForegroundLink=143,184,255
ForegroundNegative=247,118,142
ForegroundNeutral=224,175,104
ForegroundNormal=192,202,245
ForegroundPositive=158,206,106
ForegroundVisited=143,184,255

[Colors:Complementary]
BackgroundAlternate=22,24,36
BackgroundNormal=12,14,22
DecorationFocus=79,140,255
DecorationHover=143,184,255
ForegroundActive=192,202,245
ForegroundInactive=86,95,137
ForegroundLink=143,184,255
ForegroundNegative=247,118,142
ForegroundNeutral=224,175,104
ForegroundNormal=192,202,245
ForegroundPositive=158,206,106
ForegroundVisited=143,184,255

[Colors:Header]
BackgroundAlternate=18,20,31
BackgroundNormal=12,14,22
DecorationFocus=79,140,255
DecorationHover=143,184,255
ForegroundActive=192,202,245
ForegroundInactive=86,95,137
ForegroundLink=143,184,255
ForegroundNegative=247,118,142
ForegroundNeutral=224,175,104
ForegroundNormal=192,202,245
ForegroundPositive=158,206,106
ForegroundVisited=143,184,255

[Colors:Selection]
BackgroundAlternate=79,140,255
BackgroundNormal=79,140,255
DecorationFocus=79,140,255
DecorationHover=143,184,255
ForegroundActive=255,255,255
ForegroundInactive=204,204,204
ForegroundLink=143,184,255
ForegroundNegative=247,118,142
ForegroundNeutral=224,175,104
ForegroundNormal=255,255,255
ForegroundPositive=158,206,106
ForegroundVisited=143,184,255

[Colors:Tooltip]
BackgroundAlternate=18,20,31
BackgroundNormal=12,14,22
DecorationFocus=79,140,255
DecorationHover=143,184,255
ForegroundActive=192,202,245
ForegroundInactive=86,95,137
ForegroundLink=143,184,255
ForegroundNegative=247,118,142
ForegroundNeutral=224,175,104
ForegroundNormal=192,202,245
ForegroundPositive=158,206,106
ForegroundVisited=143,184,255

[Colors:View]
BackgroundAlternate=18,20,31
BackgroundNormal=12,14,22
DecorationFocus=79,140,255
DecorationHover=143,184,255
ForegroundActive=192,202,245
ForegroundInactive=86,95,137
ForegroundLink=143,184,255
ForegroundNegative=247,118,142
ForegroundNeutral=224,175,104
ForegroundNormal=192,202,245
ForegroundPositive=158,206,106
ForegroundVisited=143,184,255

[Colors:Window]
BackgroundAlternate=18,20,31
BackgroundNormal=12,14,22
DecorationFocus=79,140,255
DecorationHover=143,184,255
ForegroundActive=192,202,245
ForegroundInactive=86,95,137
ForegroundLink=143,184,255
ForegroundNegative=247,118,142
ForegroundNeutral=224,175,104
ForegroundNormal=192,202,245
ForegroundPositive=158,206,106
ForegroundVisited=143,184,255

[General]
ColorScheme=KythDark
Name=Kyth Dark
shadeSortColumn=true

[KDE]
contrast=4
KYTHCOLORSEOF

# ── Kyth Dark Plasma shell theme (frosted glass panel) ────────────────────────
# Minimal theme that overrides only the panel background SVG; all other assets
# fall back to breeze-dark via X-Plasma-Fallback-Theme.  The panel-background
# SVG uses fill-opacity=0.82 so KWin's blur effect shines through, producing
# a frosted glass look. A thin teal top-edge accent line ties the panel to
# the KythDark color accent and System Hub visual language.
mkdir -p /usr/share/plasma/desktoptheme/kyth-dark/widgets

cat >/usr/share/plasma/desktoptheme/kyth-dark/metadata.json <<'KYTHMETAEOF'
{
    "KPlugin": {
        "Authors": [{"Name": "KythOS"}],
        "Description": "KythOS dark plasma theme with frosted glass panel",
        "Id": "kyth-dark",
        "License": "Apache-2.0",
        "Name": "Kyth Dark",
        "Version": "1.0"
    },
    "X-Plasma-API": "5.0",
    "X-Plasma-Fallback-Theme": "breeze-dark"
}
KYTHMETAEOF

# panel-background.svg — 9-patch panel background.
# Coordinates: 100×100 canvas, 4px borders, semi-transparent dark slate fill.
# The hint-* elements encode margin widths for the Plasma SVG renderer;
# they are invisible (fill:none) and exist only to carry the numeric hint.
# A 1px teal accent line runs along the top edge of the panel.
cat >/usr/share/plasma/desktoptheme/kyth-dark/widgets/panel-background.svg <<'KYTHPANELSVGEOF'
<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100">
  <!-- Margin hints (invisible, encode border widths for the 9-patch renderer) -->
  <rect id="hint-left-margin"   x="0"  y="49" width="4"  height="1" fill="none"/>
  <rect id="hint-right-margin"  x="96" y="49" width="4"  height="1" fill="none"/>
  <rect id="hint-top-margin"    x="49" y="0"  width="1"  height="5" fill="none"/>
  <rect id="hint-bottom-margin" x="49" y="96" width="1"  height="4" fill="none"/>
  <!-- Teal top accent line (1px, spans the full width across the top border) -->
  <rect id="top"         x="4"  y="0"  width="92" height="1"  fill="#4f8cff" fill-opacity="0.70"/>
  <!-- 9-patch fill regions: semi-transparent dark slate -->
  <rect id="topleft"     x="0"  y="0"  width="4"  height="5"  fill="#0c0e16" fill-opacity="0.9"/>
  <rect id="topright"    x="96" y="0"  width="4"  height="5"  fill="#0c0e16" fill-opacity="0.9"/>
  <rect id="left"        x="0"  y="5"  width="4"  height="91" fill="#0c0e16" fill-opacity="0.9"/>
  <rect id="center"      x="4"  y="1"  width="92" height="95" fill="#0c0e16" fill-opacity="0.9"/>
  <rect id="right"       x="96" y="5"  width="4"  height="91" fill="#0c0e16" fill-opacity="0.9"/>
<rect id="bottomleft"  x="0"  y="96" width="4"  height="4"  fill="#0c0e16" fill-opacity="0.9"/>
  <rect id="bottom"      x="4"  y="96" width="92" height="4"  fill="#0c0e16" fill-opacity="0.9"/>
  <rect id="bottomright" x="96" y="96" width="4"  height="4"  fill="#0c0e16" fill-opacity="0.9"/>
</svg>
KYTHPANELSVGEOF

# ── Default KDE theme for all new users via /etc/skel ─────────────────────────
mkdir -p /etc/skel/.config
mkdir -p /etc/skel/Screenshots
cat >/etc/skel/Screenshots/.directory <<'SKELSHOTSDIREEOF'
[Desktop Entry]
Icon=folder-pictures
Name=Screenshots
SKELSHOTSDIREEOF

cat >/etc/skel/.config/kdeglobals <<'KDEEOF'
[General]
ColorScheme=KythDark
font=Inter,10,-1,5,400,0,0,0,0,0,Regular
fixed=Cascadia Code,10,-1,5,400,0,0,0,0,0,Regular
smallestReadableFont=Inter,8,-1,5,400,0,0,0,0,0,Regular
toolBarFont=Inter,9,-1,5,400,0,0,0,0,0,Regular
menuFont=Inter,10,-1,5,400,0,0,0,0,0,Regular

[Icons]
Theme=Papirus-Dark

[KDE]
LookAndFeelPackage=org.kde.breezedark.desktop
KDEEOF

# Keep server-side titlebars on the familiar minimize, maximize, close trio.
# IAX is KWin's button code sequence for underscore, box, and X.
cat >/etc/skel/.config/kwinrc <<'KWINDECORATIONEOF'
[org.kde.kdecoration2]
ButtonsOnLeft=
ButtonsOnRight=IAX
library=org.kde.breeze
theme=Breeze
KWINDECORATIONEOF

# Breeze GTK normally renders minimize/maximize as down/up chevrons. Replace
# both the GTK 3/4 symbolic assets and Chromium compatibility PNGs so
# client-side titlebars use the same underscore, box, and X as KWin.
window_control_src=/ctx/branding/window-controls
window_control_css=/tmp/kyth-window-controls.css

render_window_control() {
	local source=$1
	local output=$2
	local size=$3
	local background=$4
	local foreground=$5
	cat >"${window_control_css}" <<EOF
.background { fill: ${background}; }
.glyph { fill: ${foreground}; }
EOF
	rsvg-convert -w "${size}" -h "${size}" --stylesheet "${window_control_css}" \
		"${source}" -o "${output}"
}

for gtk_theme in Breeze Breeze-Dark; do
	gtk_assets="/usr/share/themes/${gtk_theme}/assets"
	[[ -d "${gtk_assets}" ]] || continue

	for state in symbolic hover-symbolic active-symbolic; do
		install -m 0644 "${window_control_src}/minimize.svg" \
			"${gtk_assets}/breeze-minimize-${state}.svg"
		install -m 0644 "${window_control_src}/maximize.svg" \
			"${gtk_assets}/breeze-maximize-${state}.svg"
		install -m 0644 "${window_control_src}/maximize.svg" \
			"${gtk_assets}/breeze-maximized-${state}.svg"
	done
	install -m 0644 "${window_control_src}/close.svg" \
		"${gtk_assets}/breeze-close-symbolic.svg"
	sed 's/#ffffff/#ff0404/' "${window_control_src}/close.svg" \
		>"${gtk_assets}/breeze-close-hover-symbolic.svg"
	sed 's/#ffffff/#ff0404/' "${window_control_src}/close.svg" \
		>"${gtk_assets}/breeze-close-active-symbolic.svg"

	if [[ "${gtk_theme}" == Breeze-Dark ]]; then
		normal_fg='rgba(252,252,252,0.91)'
		backdrop_fg='rgba(161,169,177,0.40)'
		hover_bg='#fcfcfc'
		hover_fg='#232629'
	else
		normal_fg='rgba(35,38,41,0.91)'
		backdrop_fg='rgba(112,125,138,0.72)'
		hover_bg='#232629'
		hover_fg='#fcfcfc'
	fi

	for scale in 1 2; do
		if ((scale == 1)); then
			size=18
			suffix=''
		else
			size=36
			suffix='@2'
		fi

		for control in minimize maximize; do
			source="${window_control_src}/${control}.svg"
			render_window_control "${source}" "${gtk_assets}/titlebutton-${control}${suffix}.png" \
				"${size}" none "${normal_fg}"
			render_window_control "${source}" "${gtk_assets}/titlebutton-${control}-hover${suffix}.png" \
				"${size}" "${hover_bg}" "${hover_fg}"
			render_window_control "${source}" "${gtk_assets}/titlebutton-${control}-active${suffix}.png" \
				"${size}" "${hover_bg}" "${hover_fg}"
			render_window_control "${source}" "${gtk_assets}/titlebutton-${control}-backdrop${suffix}.png" \
				"${size}" none "${backdrop_fg}"
		done

		for state in '' '-hover' '-active' '-backdrop'; do
			case "${state}" in
			-hover) close_fg='#ff667c' ;;
			-active) close_fg='#da4453' ;;
			-backdrop) close_fg="${backdrop_fg}" ;;
			*) close_fg="${normal_fg}" ;;
			esac
			render_window_control "${window_control_src}/close.svg" \
				"${gtk_assets}/titlebutton-close${state}${suffix}.png" \
				"${size}" none "${close_fg}"
		done

		for state in '' '-hover' '-active' '-backdrop'; do
			cp "${gtk_assets}/titlebutton-maximize${state}${suffix}.png" \
				"${gtk_assets}/titlebutton-maximize-maximized${state}${suffix}.png"
		done
	done
done
rm -f "${window_control_css}"

cat >/etc/skel/.config/plasmarc <<'PLASMAEOF'
[Theme]
name=kyth-dark
PLASMAEOF

# ── Kickoff favorites ─────────────────────────────────────────────────────────
# Pre-populate the Kickoff launcher favorites for new users.
# Brave and Discord are listed here even though they install via
# kyth-default-flatpaks.service at first boot — KDE silently omits entries
# whose desktop files don't exist yet and shows them automatically once the
# flatpak finishes installing.
cat >/etc/skel/.config/kickoffrc <<'KICKOFFEOF'
[Favorites]
FavoriteURLs=applications:kyth-welcome.desktop,applications:kyth-app-store.desktop,applications:steam.desktop,applications:com.brave.Browser.desktop,applications:com.discordapp.Discord.desktop,applications:org.kde.konsole.desktop

[General]
highlightNewlyInstalledApps=false
KICKOFFEOF
mkdir -p /etc/xdg
install -m 0644 /etc/skel/.config/kickoffrc /etc/xdg/kickoffrc

# ── Screen lock timeout ───────────────────────────────────────────────────────
# Default auto-lock after 15 minutes of inactivity. KDE's stock default is 5
# minutes which is too aggressive for a desktop/gaming workstation.
cat >/etc/skel/.config/kscreenlockerrc <<'SCREENLOCKEOF'
[Daemon]
Autolock=true
LockGracePeriod=5
LockOnResume=true
Timeout=15

[Greeter][Wallpaper][org.kde.image][General]
Image=/usr/share/wallpapers/kyth/contents/images/1920x1080.svg
SCREENLOCKEOF

# ── Plasma / PowerDevil hardening ─────────────────────────────────────────────
# KDE documents POWERDEVIL_NO_DDCUTIL=1 as a supported workaround when
# PowerDevil's DDC/CI monitor integration causes instability. On KythOS's AMD
# laptop targets, repeated libddcutil/backlight activity has correlated with
# display-timeout/pageflip failures, so default to the safer path:
# keep PowerDevil running, but stop it from talking to external monitors via
# ddcutil. Tradeoff: external monitor brightness control via DDC/CI is disabled.
#
# Add a second guardrail at the libddcutil layer as well. This keeps any
# consumer that does load libddcutil from starting display-watch threads, which
# are a known source of instability on some monitor/GPU combinations.
mkdir -p /etc/xdg/plasma-workspace/env /etc/xdg/ddcutil
cat >/etc/environment.d/90-kyth-powerdevil.conf <<'POWERDEVILEOF'
POWERDEVIL_NO_DDCUTIL=1
POWERDEVILEOF
cat >/etc/xdg/plasma-workspace/env/90-kyth-powerdevil.sh <<'POWERDEVILSHEOF'
#!/bin/sh
export POWERDEVIL_NO_DDCUTIL=1
POWERDEVILSHEOF
chmod +x /etc/xdg/plasma-workspace/env/90-kyth-powerdevil.sh
cat >/etc/xdg/ddcutil/ddcutilrc <<'DDCUTILRCEOF'
[libddcutil]
options: --disable-watch-displays
DDCUTILRCEOF

# ── KythOS wallpaper package ────────────────────────────────────────────────────
# Install as a proper KDE wallpaper package so the L&F lookup 'Image=kyth' works.
mkdir -p /usr/share/wallpapers/kyth/contents/images
cp /ctx/wallpaper/kyth-wallpaper.svg \
	/usr/share/wallpapers/kyth/contents/images/1920x1080.svg
printf '{"KPlugin":{"Authors":[{"Name":"KythOS"}],"Id":"kyth","Name":"KythOS","License":"CC-BY-SA-4.0"},"KPackageStructure":"Wallpaper/Images"}\n' \
	>/usr/share/wallpapers/kyth/metadata.json

# Patch all L&F defaults (Fedora variants + Breeze) to use KythOS wallpaper.
# Fedora Kinoite ships org.fedoraproject.fedora*.desktop themes that set
# Image=Fedora; we replace that in every theme so no L&F can restore the
# stock Fedora rocket wallpaper.
find /usr/share/plasma/look-and-feel -name defaults | while read -r f; do
	sed -i 's/^Image=.*/Image=kyth/' "$f"
	grep -q '^Image=' "$f" || printf '\n[Wallpaper]\nImage=kyth\n' >>"$f"
done

# System-wide XDG fallback — applied to every user before their personal
# config exists, so first-boot always shows the KythOS wallpaper.
mkdir -p /etc/xdg
cat >/etc/xdg/plasma-org.kde.plasma.desktop-appletsrc <<'XDGPLASMAEOF'
[Containments][1][Wallpaper][org.kde.image][General]
Image=/usr/share/wallpapers/kyth/contents/images/1920x1080.svg
XDGPLASMAEOF

# ── Wayland/X11 auto-detect (runs before SDDM on every boot) ─────────────────
# kyth-configure-session detects VM vs bare metal and writes the SDDM session
# conf before the greeter starts. Bare metal gets Wayland (VRR, HDR, lower
# latency); VMs keep X11 so SDDM's Wayland compositor mode doesn't fail against
# virtual GPU drivers that lack DRM/KMS backend support.
# The script runs as SDDM's ExecStartPre — fast, idempotent, no flag file.
cat >/usr/bin/kyth-configure-session <<'CONFIGURESESIONEOF'
#!/bin/bash
mkdir -p /etc/sddm.conf.d
if systemd-detect-virt -q 2>/dev/null; then
    cat >/etc/sddm.conf.d/11-kyth-session.conf <<'EOF'
[General]
DisplayServer=x11
DefaultSession=plasmax11.desktop
EOF
else
    cat >/etc/sddm.conf.d/11-kyth-session.conf <<'EOF'
[General]
DisplayServer=wayland
DefaultSession=plasma.desktop
EOF
fi
CONFIGURESESIONEOF
chmod +x /usr/bin/kyth-configure-session

mkdir -p /usr/lib/systemd/system/sddm.service.d
cat >/usr/lib/systemd/system/sddm.service.d/10-kyth-detect-session.conf <<'SDDMDROPINEOF'
[Service]
ExecStartPre=/usr/bin/kyth-configure-session
SDDMDROPINEOF

# ── SDDM session type + login screen background ───────────────────────────────
# Force X11 display server. Kinoite 44 / KDE 6.6 defaults to a Wayland session;
# KWin Wayland requires a working DRM/GBM backend and can crash on VM GPUs
# without 3D acceleration, which drops the SPICE
# connection and makes the VM appear to close. X11 is stable on all hardware
# and VM GPU drivers; users can switch to Wayland from the session picker.
mkdir -p /etc/sddm.conf.d
cat >/etc/sddm.conf.d/10-kyth.conf <<'SDDMCONFEOF'
[General]
DisplayServer=x11
DefaultSession=plasmax11.desktop

[Theme]
Current=breeze

[X11]
SessionDir=/usr/share/xsessions
SDDMCONFEOF

# Software-rendering fallback for virtual machines: makes Plasma's X11 session
# usable when the VM display has no virgl/3D acceleration. Skipped on bare metal
# (systemd-detect-virt returns non-zero when not in a VM/container) and when
# kyth.hwgl=1 is in the cmdline to force hardware GL inside a VM.
mkdir -p /etc/skel/.config/plasma-workspace/env
cat >/etc/skel/.config/plasma-workspace/env/10-kyth-qemu-safe.sh <<'QEMUSAFEEOF'
#!/bin/sh
if systemd-detect-virt -q 2>/dev/null && ! grep -qw 'kyth.hwgl=1' /proc/cmdline 2>/dev/null; then
    export LIBGL_ALWAYS_SOFTWARE=1
    export GALLIUM_DRIVER=llvmpipe
    export MESA_LOADER_DRIVER_OVERRIDE=llvmpipe
    export QT_QUICK_BACKEND=software
fi
QEMUSAFEEOF
chmod +x /etc/skel/.config/plasma-workspace/env/10-kyth-qemu-safe.sh

# theme.conf.user overrides the breeze SDDM theme defaults without modifying
# the upstream theme files. The wallpaper is already installed above.
mkdir -p /usr/share/sddm/themes/breeze
cat >/usr/share/sddm/themes/breeze/theme.conf.user <<'SDDMEOF'
[General]
type=image
background=/usr/share/wallpapers/kyth/contents/images/1920x1080.svg
logo=/usr/share/pixmaps/kyth.svg
showlogo=shown
SDDMEOF

# Make enrolled fingerprints available to the login and screen-lock PAM stack.
# fprintd-pam provides the module; authselect activates it in Fedora's profile.
if command -v authselect >/dev/null 2>&1 && authselect current >/dev/null 2>&1; then
	authselect enable-feature with-fingerprint
fi

# ── KythOS icons ───────────────────────────────────────────────────────────────
# KDE Plasma 6 Kickoff looks up icons in this order:
#   start-here-kde-plasma → start-here-kde → start-here
# Boot and display-manager components resolve /etc/os-release LOGO=kyth through
# the same icon stack, while GRUB themes key off BLS grub_class names. Install
# both KythOS-native names and Fedora-compatible overrides so stale boot entries
# cannot render the inherited Fedora badge.
# Two failure modes to defeat:
#   1. fedora-logos ships PNGs at exact pixel sizes; Qt/Plasma prefers an
#      exact-size PNG over a scalable SVG, so the Fedora icon won at lookup.
#   2. The Kickoff plasmoid's default icon is "", which falls back to the theme
#      lookup — so a cached/stale Fedora logo survived into the applet.
# Fix: install PNGs at every standard size AND patch Kickoff's main.xml so the
# compiled-in default is kyth-kickoff, requiring no per-user config at all.

# Scalable SVGs (also used by the kyth-set-kickoff-icon first-login script)
for theme_dir in \
	/usr/share/icons/hicolor/scalable/apps \
	/usr/share/icons/breeze/apps/scalable \
	/usr/share/icons/breeze-dark/apps/scalable; do
	mkdir -p "${theme_dir}"
	cp /ctx/branding/kyth-logo-transparent.svg "${theme_dir}/kyth.svg"
	cp /ctx/branding/kyth-logo-transparent.svg "${theme_dir}/kyth-symbol.svg"
	cp /ctx/branding/kyth-kickoff.svg "${theme_dir}/kythos.svg"
	cp /ctx/branding/kyth-kickoff.svg "${theme_dir}/kyth-kickoff.svg"
	cp /ctx/branding/kyth-kickoff.svg "${theme_dir}/distributor-logo.svg"
	cp /ctx/branding/kyth-kickoff.svg "${theme_dir}/fedora-logo-icon.svg"
	cp /ctx/branding/kyth-kickoff.svg "${theme_dir}/start-here.svg"
	cp /ctx/branding/kyth-kickoff.svg "${theme_dir}/start-here-kde.svg"
	cp /ctx/branding/kyth-kickoff.svg "${theme_dir}/start-here-kde-plasma.svg"
done

# PNGs at every standard size — beats inherited exact-size Fedora PNGs at lookup
for sz in 16 22 24 32 48 64 128 256; do
	for base in /usr/share/icons/hicolor /usr/share/icons/breeze /usr/share/icons/breeze-dark; do
		dir="${base}/${sz}x${sz}/apps"
		mkdir -p "${dir}"
		rsvg-convert -w "${sz}" -h "${sz}" /ctx/branding/kyth-kickoff.svg \
			-o "${dir}/kyth-kickoff.png"
		rsvg-convert -w "${sz}" -h "${sz}" /ctx/branding/kyth-logo-transparent.svg \
			-o "${dir}/kyth.png"
		cp "${dir}/kyth-kickoff.png" "${dir}/kythos.png"
		cp "${dir}/kyth-kickoff.png" "${dir}/distributor-logo.png"
		cp "${dir}/kyth-kickoff.png" "${dir}/fedora-logo-icon.png"
		cp "${dir}/kyth-kickoff.png" "${dir}/start-here.png"
		cp "${dir}/kyth-kickoff.png" "${dir}/start-here-kde.png"
		cp "${dir}/kyth-kickoff.png" "${dir}/start-here-kde-plasma.png"
	done
done

# Extra legacy lookup locations used by boot menus, display managers, and older
# GTK/KDE code paths. The Fedora-named files intentionally contain KythOS art:
# some existing BLS snippets still say grub_class=fedora until the migration
# below has run.
mkdir -p /usr/share/pixmaps
cp /ctx/branding/kyth-logo-transparent.svg /usr/share/pixmaps/kyth.svg
cp /ctx/branding/kyth-kickoff.svg /usr/share/pixmaps/kythos.svg
cp /ctx/branding/kyth-kickoff.svg /usr/share/pixmaps/distributor-logo.svg
cp /ctx/branding/kyth-kickoff.svg /usr/share/pixmaps/fedora-logo-icon.svg
rsvg-convert -w 64 -h 64 /ctx/branding/kyth-logo-transparent.svg -o /usr/share/pixmaps/kyth.png
rsvg-convert -w 64 -h 64 /ctx/branding/kyth-kickoff.svg -o /usr/share/pixmaps/kythos.png
cp /usr/share/pixmaps/kythos.png /usr/share/pixmaps/distributor-logo.png
cp /usr/share/pixmaps/kythos.png /usr/share/pixmaps/fedora-logo-icon.png

for grub_icon_dir in \
	/boot/grub2/themes/system/icons \
	/boot/grub2/themes/starfield/icons \
	/usr/share/grub/themes/system/icons \
	/usr/share/grub/themes/starfield/icons; do
	mkdir -p "${grub_icon_dir}"
	for icon in kyth kythos fedora gnu-linux linux; do
		rsvg-convert -w 32 -h 32 /ctx/branding/kyth-kickoff.svg \
			-o "${grub_icon_dir}/${icon}.png"
	done
done

mkdir -p /etc/default
if [[ -f /etc/default/grub ]]; then
	if grep -q '^GRUB_DISTRIBUTOR=' /etc/default/grub; then
		sed -i 's/^GRUB_DISTRIBUTOR=.*/GRUB_DISTRIBUTOR="KythOS"/' /etc/default/grub
	else
		printf '\nGRUB_DISTRIBUTOR="KythOS"\n' >>/etc/default/grub
	fi
else
	printf 'GRUB_DISTRIBUTOR="KythOS"\n' >/etc/default/grub
fi

# Microsoft 365 web-app shortcut icons (referenced by the .desktop entries the
# kyth-welcome Work Setup page writes; without them Kickoff shows a generic globe).
for app in outlook word excel powerpoint onenote teams; do
	cp "/ctx/branding/m365/kyth-m365-${app}.svg" \
		/usr/share/icons/hicolor/scalable/apps/
	for sz in 16 22 24 32 48 64 128 256; do
		dir="/usr/share/icons/hicolor/${sz}x${sz}/apps"
		mkdir -p "${dir}"
		rsvg-convert -w "${sz}" -h "${sz}" "/ctx/branding/m365/kyth-m365-${app}.svg" \
			-o "${dir}/kyth-m365-${app}.png"
	done
done

# Clear any stale caches so the new icons take effect immediately on first boot.
rm -f /usr/share/icons/hicolor/icon-theme.cache
rm -f /usr/share/icons/breeze/icon-theme.cache
rm -f /usr/share/icons/breeze-dark/icon-theme.cache
gtk-update-icon-cache -f /usr/share/icons/hicolor/ 2>/dev/null || true
gtk-update-icon-cache -f /usr/share/icons/breeze/ 2>/dev/null || true
gtk-update-icon-cache -f /usr/share/icons/breeze-dark/ 2>/dev/null || true

# ── Kickoff plasmoid defaults ─────────────────────────────────────────────────
# Patch Kickoff's KConfig XML so every new widget instance defaults to
# kyth-kickoff and quiet newly-installed app badges before any per-user config
# file or first-login script exists.
# The empty <default></default> is the upstream fallback that causes Kickoff
# to use start-here-kde-plasma from the icon theme; we replace it with the
# named icon so the plasmoid's own default wins unconditionally.
_kickoff_cfg=/usr/share/plasma/plasmoids/org.kde.plasma.kickoff/contents/config/main.xml
if [[ -f "${_kickoff_cfg}" ]]; then
	sed -i \
		'/<entry name="icon" type="String">/,/<\/entry>/ {
            s|<default></default>|<default>kyth-kickoff</default>|
        }' \
		"${_kickoff_cfg}"
	sed -i \
		'/<entry name="highlightNewlyInstalledApps" type="Bool">/,/<\/entry>/ {
            s|<default>true</default>|<default>false</default>|
        }' \
		"${_kickoff_cfg}"
fi

# ── First-login script: polish Kickoff launcher defaults ──────────────────────
# Belt-and-suspenders: the icon theme install above should be enough, but this
# also writes the icon key directly into each user's Kickoff applet config in
# case the theme lookup is overridden by a previously cached value. It also
# disables Plasma's newly-installed app badges so KythOS launchers land in
# their categories without green dots or "New!" labels.
cat >/usr/bin/kyth-set-kickoff-icon <<'KICKOFEOF'
#!/usr/bin/env python3
import os, re, shutil, subprocess

aprc = os.path.expanduser("~/.config/plasma-org.kde.plasma.desktop-appletsrc")
autostart = os.path.expanduser("~/.config/autostart/kyth-set-kickoff-icon.desktop")
kwriteconfig = shutil.which('kwriteconfig6')

if kwriteconfig:
    subprocess.run([
        kwriteconfig, '--file', 'kickoffrc',
        '--group', 'General',
        '--key', 'highlightNewlyInstalledApps',
        '--type', 'bool', 'false',
    ], check=False)

if kwriteconfig and os.path.exists(aprc):
    content = open(aprc).read()
    for m in re.finditer(
        r'^\[Containments\]\[(\d+)\]\[Applets\]\[(\d+)\]',
        content, re.MULTILINE
    ):
        cont, applet = m.group(1), m.group(2)
        body_start = m.end()
        nxt = re.search(r'^\[', content[body_start:], re.MULTILINE)
        body = content[body_start: body_start + nxt.start()] if nxt else content[body_start:]
        if 'plugin=org.kde.plasma.kickoff' in body:
            subprocess.run([
                kwriteconfig, '--file', aprc,
                '--group', 'Containments', '--group', cont,
                '--group', 'Applets', '--group', applet,
                '--group', 'Configuration', '--group', 'General',
                '--key', 'icon', 'kyth-kickoff',
            ], check=False)
            subprocess.run([
                kwriteconfig, '--file', aprc,
                '--group', 'Containments', '--group', cont,
                '--group', 'Applets', '--group', applet,
                '--group', 'Configuration', '--group', 'General',
                '--key', 'highlightNewlyInstalledApps',
                '--type', 'bool', 'false',
            ], check=False)

try:
    os.unlink(autostart)
except OSError:
    pass
KICKOFEOF
chmod +x /usr/bin/kyth-set-kickoff-icon

mkdir -p /etc/skel/.config/autostart
cat >/etc/skel/.config/autostart/kyth-set-kickoff-icon.desktop <<'AUTOSTARTEOF'
[Desktop Entry]
Type=Application
Name=KythOS: Set Kickoff Icon
Exec=/usr/bin/kyth-set-kickoff-icon
X-KDE-autostart-after=panel
Hidden=false
NoDisplay=true
AUTOSTARTEOF

mkdir -p /etc/xdg/autostart
install -m 0644 /etc/skel/.config/autostart/kyth-set-kickoff-icon.desktop \
	/etc/xdg/autostart/kyth-set-kickoff-icon.desktop

# ── KythOS default Plasma layout preset ───────────────────────────────────────
# Applies the distinctive KythOS desktop shape: bottom taskbar, KythOS launcher,
# pinned everyday apps, system tray, clock, show-desktop target, wallpaper, and
# a restore marker. Run with --initial for fresh users and --force when the user
# explicitly clicks "Restore KythOS Layout" in System Hub.
cat >/usr/bin/kyth-apply-desktop-layout <<'LAYOUTEOF'
#!/usr/bin/env bash
set -euo pipefail

force=0
initial=0
layout_version="kyth-comfort-v3"
config_file="plasma-org.kde.plasma.desktop-appletsrc"

for arg in "$@"; do
    case "${arg}" in
        --force)
            force=1
            ;;
        --initial)
            initial=1
            ;;
        -h|--help)
            printf 'Usage: kyth-apply-desktop-layout [--initial|--force]\n'
            exit 0
            ;;
    esac
done

if [[ "${force}" != "1" ]]; then
    current=""
    legacy_current=""
    if command -v kreadconfig6 >/dev/null 2>&1; then
        current="$(kreadconfig6 --file "${config_file}" --group KythOS --key KythComfortLayout 2>/dev/null || true)"
        legacy_current="$(kreadconfig6 --file "${config_file}" --group KythOS --key WindowsFamiliarLayout 2>/dev/null || true)"
    fi
    if [[ "${current}" == "${layout_version}" || "${current}" == "kyth-comfort-v2" || "${legacy_current}" == "windows-familiar-v1" ]]; then
        exit 0
    fi
fi

if [[ "${force}" != "1" && "${initial}" != "1" ]]; then
    echo "Refusing to change an existing layout without --initial or --force." >&2
    exit 64
fi

qdbus_cmd=""
for candidate in qdbus6 qdbus-qt6 qdbus; do
    if command -v "${candidate}" >/dev/null 2>&1; then
        qdbus_cmd="${candidate}"
        break
    fi
done
if [[ -z "${qdbus_cmd}" ]]; then
    echo "qdbus6/qdbus-qt6/qdbus is not available; Plasma layout cannot be applied." >&2
    exit 75
fi

runtime_dir="${XDG_RUNTIME_DIR:-/tmp}"
[[ -d "${runtime_dir}" ]] || runtime_dir="/tmp"
script_file="$(mktemp "${runtime_dir}/kyth-layout.XXXXXX.js")"
trap 'rm -f "${script_file}"' EXIT

cat > "${script_file}" <<'JSEOF'
var launchers = [
    "applications:kyth-welcome.desktop",
    "applications:kyth-app-store.desktop",
    "applications:steam.desktop",
    "applications:com.brave.Browser.desktop",
    "applications:org.kde.dolphin.desktop",
    "applications:org.kde.konsole.desktop"
].join(",");

var trayItems = [
    "org.kde.plasma.networkmanagement",
    "org.kde.plasma.volume",
    "org.kde.plasma.bluetooth",
    "org.kde.plasma.battery",
    "org.kde.plasma.notifications",
    "org.kde.plasma.clipboard",
    "org.kde.plasma.devicenotifier",
    "org.kde.plasma.printmanager",
    "org.kde.kdeconnect"
].join(",");

var hiddenTrayItems = [
    "org.kde.plasma.keyboardindicator",
    "org.kde.plasma.mediacontroller"
].join(",");

function safeSet(object, key, value) {
    try {
        object[key] = value;
    } catch (e) {
    }
}

function writeConfig(object, groups, values) {
    try {
        object.currentConfigGroup = groups;
        for (var key in values) {
            object.writeConfig(key, values[key]);
        }
        object.reloadConfig();
    } catch (e) {
    }
}

function removeExistingPanels() {
    var ids = [];
    for (var i = 0; i < panelIds.length; ++i) {
        ids.push(panelIds[i]);
    }
    for (var i = 0; i < ids.length; ++i) {
        var panel = panelById(ids[i]);
        if (panel) {
            panel.remove();
        }
    }
}

function uniqueScreens() {
    var seen = [];
    var desktopsArray = desktops();
    for (var i = 0; i < desktopsArray.length; ++i) {
        var screen = desktopsArray[i].screen;
        if (seen.indexOf(screen) === -1) {
            seen.push(screen);
        }
    }
    if (seen.length === 0) {
        seen.push(0);
    }
    return seen;
}

function configureDesktops() {
    var desktopsArray = desktops();
    for (var i = 0; i < desktopsArray.length; ++i) {
        var desktop = desktopsArray[i];
        desktop.wallpaperPlugin = "org.kde.image";
        writeConfig(desktop, ["Wallpaper", "org.kde.image", "General"], {
            "Image": "/usr/share/wallpapers/kyth/contents/images/1920x1080.svg"
        });
        writeConfig(desktop, ["General"], {
            "ToolBoxButtonState": "topcenter"
        });
    }
}

function addKythDefaultPanel(screen) {
    var panel = new Panel;
    safeSet(panel, "screen", screen);
    panel.location = "bottom";
    panel.height = 42;
    safeSet(panel, "alignment", "center");
    safeSet(panel, "floating", false);
    safeSet(panel, "floatingApplets", false);

    var kickoff = panel.addWidget("org.kde.plasma.kickoff");
    writeConfig(kickoff, ["General"], {
        "icon": "kyth-kickoff",
        "favoritesPortedToKAstats": true,
        "alphaSort": true,
        "showActionButtonCaptions": true
    });

    var tasks = panel.addWidget("org.kde.plasma.icontasks");
    writeConfig(tasks, ["General"], {
        "launchers": launchers,
        "showOnlyCurrentDesktop": false,
        "showOnlyCurrentScreen": false,
        "showOnlyCurrentActivity": false,
        "groupingStrategy": 1,
        "maxStripes": 1,
        "showToolTips": true,
        "wheelEnabled": "AllTask",
        "indicateAudioStreams": true,
        "highlightWindows": true,
        "middleClickAction": "NewInstance"
    });

    panel.addWidget("org.kde.plasma.marginsseparator");

    var tray = panel.addWidget("org.kde.plasma.systemtray");
    writeConfig(tray, ["General"], {
        "extraItems": trayItems,
        "hiddenItems": hiddenTrayItems,
        "knownItems": trayItems + "," + hiddenTrayItems,
        "showAllItems": false
    });

    panel.addWidget("org.kde.plasma.panelspacer");

    var clock = panel.addWidget("org.kde.plasma.digitalclock");
    writeConfig(clock, ["Appearance"], {
        "showDate": false,
        "dateFormat": "shortDate",
        "showSeconds": false
    });

    panel.addWidget("org.kde.plasma.showdesktop");
}

removeExistingPanels();
configureDesktops();
var screens = uniqueScreens();
for (var i = 0; i < screens.length; ++i) {
    addKythDefaultPanel(screens[i]);
}
JSEOF

"${qdbus_cmd}" org.kde.plasmashell /PlasmaShell org.kde.PlasmaShell.evaluateScript "$(cat "${script_file}")" >/dev/null

if command -v kwriteconfig6 >/dev/null 2>&1; then
    kwriteconfig6 --file "${config_file}" --group KythOS --key KythComfortLayout "${layout_version}" >/dev/null 2>&1 || true
fi
LAYOUTEOF
chmod +x /usr/bin/kyth-apply-desktop-layout

# ── KythOS role presets ───────────────────────────────────────────────────────
# Lightweight, user-controlled presets for the home page focus picker. These
# alter prominence and pins only; they never remove apps or hide tools from
# search.
cat >/usr/bin/kyth-apply-role-preset <<'ROLEPRESETEOF'
#!/usr/bin/env bash
set -euo pipefail

profile="${1:-everyday}"
case "${profile}" in
    work|both|everyday)
        profile="everyday"
        launchers=(
            "applications:kyth-welcome.desktop"
            "applications:kyth-app-store.desktop"
            "applications:com.brave.Browser.desktop"
            "applications:org.kde.dolphin.desktop"
            "applications:org.libreoffice.LibreOffice.desktop"
            "applications:eu.betterbird.Betterbird.desktop"
            "applications:org.kde.konsole.desktop"
        )
        favorites=(
            "applications:kyth-welcome.desktop"
            "applications:kyth-app-store.desktop"
            "applications:com.brave.Browser.desktop"
            "applications:org.kde.dolphin.desktop"
            "applications:org.libreoffice.LibreOffice.desktop"
            "applications:eu.betterbird.Betterbird.desktop"
            "applications:org.kde.konsole.desktop"
        )
        ;;
    gaming)
        launchers=(
            "applications:kyth-welcome.desktop"
            "applications:kyth-app-store.desktop"
            "applications:steam.desktop"
            "applications:com.brave.Browser.desktop"
            "applications:dev.vencord.Vesktop.desktop"
            "applications:org.kde.dolphin.desktop"
            "applications:org.kde.konsole.desktop"
        )
        favorites=(
            "applications:kyth-welcome.desktop"
            "applications:kyth-app-store.desktop"
            "applications:steam.desktop"
            "applications:com.brave.Browser.desktop"
            "applications:dev.vencord.Vesktop.desktop"
            "applications:org.kde.dolphin.desktop"
            "applications:org.kde.konsole.desktop"
        )
        ;;
    *)
        echo "Usage: kyth-apply-role-preset [everyday|gaming]" >&2
        exit 64
        ;;
esac

profile_dir="${HOME}/.local/share/kyth"
mkdir -p "${profile_dir}"
printf '%s\n' "${profile}" > "${profile_dir}/profile"

join_by_comma() {
    local IFS=,
    printf '%s' "$*"
}
launcher_csv="$(join_by_comma "${launchers[@]}")"
favorite_csv="$(join_by_comma "${favorites[@]}")"
tray_csv="org.kde.plasma.networkmanagement,org.kde.plasma.volume,org.kde.plasma.bluetooth,org.kde.plasma.battery,org.kde.plasma.notifications,org.kde.plasma.clipboard,org.kde.plasma.devicenotifier,org.kde.plasma.printmanager,org.kde.kdeconnect"
hidden_tray_csv="org.kde.plasma.keyboardindicator,org.kde.plasma.mediacontroller"

if command -v kwriteconfig6 >/dev/null 2>&1; then
    kwriteconfig6 --file kickoffrc --group Favorites --key FavoriteURLs "${favorite_csv}"
    kwriteconfig6 --file plasma-discoverrc --group UpdatesNotifier --key UseNotifications --type bool false
fi

qdbus_cmd=""
for candidate in qdbus6 qdbus-qt6 qdbus; do
    if command -v "${candidate}" >/dev/null 2>&1; then
        qdbus_cmd="${candidate}"
        break
    fi
done

if [[ -n "${qdbus_cmd}" ]]; then
    runtime_dir="${XDG_RUNTIME_DIR:-/tmp}"
    [[ -d "${runtime_dir}" ]] || runtime_dir="/tmp"
    script_file="$(mktemp "${runtime_dir}/kyth-role-preset.XXXXXX.js")"
    trap 'rm -f "${script_file}"' EXIT
    cat > "${script_file}" <<JSEOF
var launchers = "${launcher_csv}";
var trayItems = "${tray_csv}";
var hiddenTrayItems = "${hidden_tray_csv}";

function writeConfig(object, groups, values) {
    try {
        object.currentConfigGroup = groups;
        for (var key in values) {
            object.writeConfig(key, values[key]);
        }
        object.reloadConfig();
    } catch (e) {
    }
}

for (var p = 0; p < panelIds.length; ++p) {
    var panel = panelById(panelIds[p]);
    if (!panel || !panel.widgets) {
        continue;
    }
    var widgets = panel.widgets();
    for (var i = 0; i < widgets.length; ++i) {
        var widget = widgets[i];
        if (widget.type === "org.kde.plasma.icontasks") {
            writeConfig(widget, ["General"], {
                "launchers": launchers,
                "showOnlyCurrentDesktop": false,
                "showOnlyCurrentScreen": false,
                "showOnlyCurrentActivity": false,
                "groupingStrategy": 1,
                "maxStripes": 1,
                "showToolTips": true,
                "wheelEnabled": "AllTask",
                "indicateAudioStreams": true,
                "highlightWindows": true,
                "middleClickAction": "NewInstance"
            });
        } else if (widget.type === "org.kde.plasma.systemtray") {
            writeConfig(widget, ["General"], {
                "extraItems": trayItems,
                "hiddenItems": hiddenTrayItems,
                "knownItems": trayItems + "," + hiddenTrayItems,
                "showAllItems": false
            });
        } else if (widget.type === "org.kde.plasma.digitalclock") {
            writeConfig(widget, ["Appearance"], {
                "showDate": false,
                "dateFormat": "shortDate",
                "showSeconds": false
            });
        }
    }
}
JSEOF
    "${qdbus_cmd}" org.kde.plasmashell /PlasmaShell org.kde.PlasmaShell.evaluateScript "$(cat "${script_file}")" >/dev/null 2>&1 || true
fi

if command -v kbuildsycoca6 >/dev/null 2>&1; then
    kbuildsycoca6 --noincremental >/dev/null 2>&1 || true
fi

echo "Applied ${profile} preset."
ROLEPRESETEOF
chmod +x /usr/bin/kyth-apply-role-preset

# ── User comfort polish ───────────────────────────────────────────────────────
# KDE stores several comfort preferences per-user. Bake a versioned, automatic
# polish pass into the image so new accounts get it from /etc/skel and existing
# accounts receive it once after an OS update.
cat >/usr/bin/kyth-user-polish <<'POLISHEOF'
#!/usr/bin/env bash
set -euo pipefail

version="v12"
stamp_dir="${HOME}/.local/share/kyth"
stamp="${stamp_dir}/user-polish-${version}"
old_autostart="${HOME}/.config/autostart/kyth-windows-friendly-defaults.desktop"
force=0
had_polish_stamp=0

for arg in "$@"; do
    case "${arg}" in
        --force)
            force=1
            ;;
        -h|--help)
            printf 'Usage: kyth-user-polish [--force]\n'
            exit 0
            ;;
    esac
done

if [[ -d "${stamp_dir}" ]] && compgen -G "${stamp_dir}/user-polish-*" >/dev/null; then
    had_polish_stamp=1
fi

if [[ -f "${stamp}" && "${force}" != "1" ]]; then
    rm -f "${old_autostart}" "${HOME}/.config/autostart/kyth-user-polish.desktop" 2>/dev/null || true
    exit 0
fi

mkdir -p "${stamp_dir}"

# Ensure common folders exist even when xdg-user-dirs did not run yet. Games is
# intentionally non-standard, but important for a gaming-first workstation where
# local launchers, save backups, mods, and exports need an obvious home.
if command -v xdg-user-dirs-update >/dev/null 2>&1; then
    xdg-user-dirs-update >/dev/null 2>&1 || true
fi
mkdir -p \
    "${HOME}/Desktop" \
    "${HOME}/Documents" \
    "${HOME}/Downloads" \
    "${HOME}/Games" \
    "${HOME}/Music" \
    "${HOME}/Pictures" \
    "${HOME}/Public" \
    "${HOME}/Screenshots" \
    "${HOME}/Templates" \
    "${HOME}/Videos"

if [[ ! -f "${HOME}/Games/.directory" ]]; then
    cat > "${HOME}/Games/.directory" <<'GAMESDIREEOF'
[Desktop Entry]
Icon=applications-games
Name=Games
GAMESDIREEOF
fi

if [[ ! -f "${HOME}/Screenshots/.directory" ]]; then
    cat > "${HOME}/Screenshots/.directory" <<'SHOTSDIREEOF'
[Desktop Entry]
Icon=folder-pictures
Name=Screenshots
SHOTSDIREEOF
fi

if [[ ! -f "${HOME}/Templates/Plain Text.txt" ]]; then
    printf '' > "${HOME}/Templates/Plain Text.txt"
fi

# File associations that make double-click behavior feel normal on day one.
# Use xdg-mime so existing user choices are updated per MIME type without
# clobbering unrelated custom associations.
mkdir -p "${HOME}/.config"

# BlueDevil persists adapter power state per-user and restores it after the
# system boot helper runs. Clear stale disabled state once so an OS update does
# not leave Bluetooth off at every login. Users can still disable it afterward.
bluedevil_config="${HOME}/.config/bluedevilglobalrc"
if [[ -f "${bluedevil_config}" ]]; then
    sed -i -E '/^[[:xdigit:]:]+_powered=false$/d' "${bluedevil_config}"
fi
if command -v bluetoothctl >/dev/null 2>&1; then
    bluetoothctl power on >/dev/null 2>&1 || true
fi

if command -v xdg-mime >/dev/null 2>&1; then
    while IFS='|' read -r desktop mime; do
        [[ -n "${desktop}" && -n "${mime}" ]] || continue
        xdg-mime default "${desktop}" "${mime}" >/dev/null 2>&1 || true
    done <<'MIMEDEFAULTS'
org.kde.okular.desktop|application/pdf
org.kde.okular.desktop|application/epub+zip
org.kde.gwenview.desktop|image/jpeg
org.kde.gwenview.desktop|image/png
org.kde.gwenview.desktop|image/gif
org.kde.gwenview.desktop|image/webp
org.videolan.VLC.desktop|video/mp4
org.videolan.VLC.desktop|video/x-matroska
org.videolan.VLC.desktop|video/x-msvideo
org.videolan.VLC.desktop|audio/mpeg
org.videolan.VLC.desktop|audio/flac
org.kde.kwrite.desktop|text/plain
org.kde.kwrite.desktop|text/markdown
org.kde.ark.desktop|application/zip
org.kde.ark.desktop|application/x-7z-compressed
org.kde.ark.desktop|application/x-rar
org.kde.ark.desktop|application/x-tar
kyth-exe-handler.desktop|application/x-ms-dos-executable
kyth-exe-handler.desktop|application/x-msdos-program
kyth-exe-handler.desktop|application/x-dosexec
kyth-exe-handler.desktop|application/x-msi
kyth-exe-handler.desktop|application/x-msdownload
kyth-exe-handler.desktop|application/vnd.microsoft.portable-executable
kyth-exe-handler.desktop|application/x-rpm
kyth-exe-handler.desktop|application/x-redhat-package-manager
com.brave.Browser.desktop|x-scheme-handler/http
com.brave.Browser.desktop|x-scheme-handler/https
com.getmailspring.Mailspring.desktop|x-scheme-handler/mailto
org.kde.dolphin.desktop|inode/directory
MIMEDEFAULTS
fi

# Dolphin Places sidebar: seed a comfortable everyday set without depending on
# fragile GUI state. Preserve existing customized places; add missing essentials.
mkdir -p "${HOME}/.local/share"
places_file="${HOME}/.local/share/user-places.xbel"
ensure_place() {
    local href=$1
    local title=$2
    local icon=$3
    grep -Fq "href=\"${href}\"" "${places_file}" 2>/dev/null && return 0
    local tmp_places="${places_file}.kyth-tmp"
    awk -v href="${href}" -v title="${title}" -v icon="${icon}" '
        /<\/xbel>/ && !done {
            print " <bookmark href=\"" href "\">"
            print "  <title>" title "</title>"
            print "  <info><metadata owner=\"http://freedesktop.org\"><bookmark:icon name=\"" icon "\" xmlns:bookmark=\"http://www.freedesktop.org/standards/desktop-bookmarks\"/></metadata></info>"
            print " </bookmark>"
            done=1
        }
        { print }
    ' "${places_file}" > "${tmp_places}" && mv "${tmp_places}" "${places_file}"
}
if [[ ! -f "${places_file}" ]]; then
    cat > "${places_file}" <<PLACESXBELEOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE xbel>
<xbel version="1.0">
 <bookmark href="file://${HOME}">
  <title>Home</title>
  <info><metadata owner="http://freedesktop.org"><bookmark:icon name="user-home" xmlns:bookmark="http://www.freedesktop.org/standards/desktop-bookmarks"/></metadata></info>
 </bookmark>
 <bookmark href="file://${HOME}/Desktop">
  <title>Desktop</title>
  <info><metadata owner="http://freedesktop.org"><bookmark:icon name="user-desktop" xmlns:bookmark="http://www.freedesktop.org/standards/desktop-bookmarks"/></metadata></info>
 </bookmark>
 <bookmark href="file://${HOME}/Documents">
  <title>Documents</title>
  <info><metadata owner="http://freedesktop.org"><bookmark:icon name="folder-documents" xmlns:bookmark="http://www.freedesktop.org/standards/desktop-bookmarks"/></metadata></info>
 </bookmark>
 <bookmark href="file://${HOME}/Downloads">
  <title>Downloads</title>
  <info><metadata owner="http://freedesktop.org"><bookmark:icon name="folder-download" xmlns:bookmark="http://www.freedesktop.org/standards/desktop-bookmarks"/></metadata></info>
 </bookmark>
 <bookmark href="file://${HOME}/Games">
  <title>Games</title>
  <info><metadata owner="http://freedesktop.org"><bookmark:icon name="applications-games" xmlns:bookmark="http://www.freedesktop.org/standards/desktop-bookmarks"/></metadata></info>
 </bookmark>
 <bookmark href="file://${HOME}/Music">
  <title>Music</title>
  <info><metadata owner="http://freedesktop.org"><bookmark:icon name="folder-music" xmlns:bookmark="http://www.freedesktop.org/standards/desktop-bookmarks"/></metadata></info>
 </bookmark>
 <bookmark href="file://${HOME}/Pictures">
  <title>Pictures</title>
  <info><metadata owner="http://freedesktop.org"><bookmark:icon name="folder-pictures" xmlns:bookmark="http://www.freedesktop.org/standards/desktop-bookmarks"/></metadata></info>
 </bookmark>
 <bookmark href="file://${HOME}/Screenshots">
  <title>Screenshots</title>
  <info><metadata owner="http://freedesktop.org"><bookmark:icon name="folder-pictures" xmlns:bookmark="http://www.freedesktop.org/standards/desktop-bookmarks"/></metadata></info>
 </bookmark>
 <bookmark href="file://${HOME}/Public">
  <title>Public</title>
  <info><metadata owner="http://freedesktop.org"><bookmark:icon name="folder-publicshare" xmlns:bookmark="http://www.freedesktop.org/standards/desktop-bookmarks"/></metadata></info>
 </bookmark>
 <bookmark href="file://${HOME}/Templates">
  <title>Templates</title>
  <info><metadata owner="http://freedesktop.org"><bookmark:icon name="folder-templates" xmlns:bookmark="http://www.freedesktop.org/standards/desktop-bookmarks"/></metadata></info>
 </bookmark>
 <bookmark href="file://${HOME}/Videos">
  <title>Videos</title>
  <info><metadata owner="http://freedesktop.org"><bookmark:icon name="folder-videos" xmlns:bookmark="http://www.freedesktop.org/standards/desktop-bookmarks"/></metadata></info>
 </bookmark>
 <bookmark href="trash:/">
  <title>Trash</title>
  <info><metadata owner="http://freedesktop.org"><bookmark:icon name="user-trash" xmlns:bookmark="http://www.freedesktop.org/standards/desktop-bookmarks"/></metadata></info>
 </bookmark>
 <bookmark href="network:/">
  <title>Network</title>
  <info><metadata owner="http://freedesktop.org"><bookmark:icon name="network-workgroup" xmlns:bookmark="http://www.freedesktop.org/standards/desktop-bookmarks"/></metadata></info>
 </bookmark>
</xbel>
PLACESXBELEOF
fi
ensure_place "file://${HOME}" "Home" "user-home"
ensure_place "file://${HOME}/Desktop" "Desktop" "user-desktop"
ensure_place "file://${HOME}/Documents" "Documents" "folder-documents"
ensure_place "file://${HOME}/Downloads" "Downloads" "folder-download"
ensure_place "file://${HOME}/Games" "Games" "applications-games"
ensure_place "file://${HOME}/Music" "Music" "folder-music"
ensure_place "file://${HOME}/Pictures" "Pictures" "folder-pictures"
ensure_place "file://${HOME}/Screenshots" "Screenshots" "folder-pictures"
ensure_place "file://${HOME}/Public" "Public" "folder-publicshare"
ensure_place "file://${HOME}/Templates" "Templates" "folder-templates"
ensure_place "file://${HOME}/Videos" "Videos" "folder-videos"
ensure_place "trash:/" "Trash" "user-trash"
ensure_place "network:/" "Network" "network-workgroup"

if command -v kwriteconfig6 >/dev/null 2>&1; then
    # Ensure KDE apps (Discover, System Settings, etc.) always display English.
    # KDE's locale stack reads plasma-localerc before falling back to LANG; without
    # an explicit entry some builds pick the first AppStream translation in the XML.
    kwriteconfig6 --file plasma-localerc --group Translations --key LANGUAGE "en_US"
    kwriteconfig6 --file plasma-localerc --group Formats --key LC_TIME "en_US.UTF-8"

    # KWallet should be opened by kwallet-pam with the login password, then stay
    # open for the session so browsers and editors do not ask again after boot.
    kwriteconfig6 --file kwalletrc --group Wallet --key Enabled --type bool true
    kwriteconfig6 --file kwalletrc --group Wallet --key "Default Wallet" kdewallet
    kwriteconfig6 --file kwalletrc --group Wallet --key "Local Wallet" kdewallet
    kwriteconfig6 --file kwalletrc --group Wallet --key "Use One Wallet" --type bool true
    kwriteconfig6 --file kwalletrc --group Wallet --key "Close When Idle" --type bool false
    kwriteconfig6 --file kwalletrc --group Wallet --key "Close on Screensaver" --type bool false
    kwriteconfig6 --file kwalletrc --group Wallet --key "Leave Open" --type bool true

    # KythOS visual identity. New users receive this from /etc/skel; this
    # keeps older or manually-created accounts aligned without repeatedly
    # clobbering a user's custom theme. The System Hub polish button passes
    # --force when the user explicitly asks to re-apply the KythOS look.
    current_color=""
    current_plasma_theme=""
    current_favorites=""
    if command -v kreadconfig6 >/dev/null 2>&1; then
        current_color="$(kreadconfig6 --file kdeglobals --group General --key ColorScheme 2>/dev/null || true)"
        current_plasma_theme="$(kreadconfig6 --file plasmarc --group Theme --key name 2>/dev/null || true)"
        current_favorites="$(kreadconfig6 --file kickoffrc --group Favorites --key FavoriteURLs 2>/dev/null || true)"
    fi
    apply_kyth_visuals=0
    if [[ "${force}" == "1" || ( -z "${current_color}" && -z "${current_plasma_theme}" ) ]]; then
        apply_kyth_visuals=1
    fi
    if [[ "${apply_kyth_visuals}" == "1" ]]; then
        kwriteconfig6 --file kdeglobals --group General --key ColorScheme KythDark
        kwriteconfig6 --file kdeglobals --group General --key font 'Inter,10,-1,5,400,0,0,0,0,0,Regular'
        kwriteconfig6 --file kdeglobals --group General --key fixed 'Cascadia Code,10,-1,5,400,0,0,0,0,0,Regular'
        kwriteconfig6 --file kdeglobals --group General --key smallestReadableFont 'Inter,8,-1,5,400,0,0,0,0,0,Regular'
        kwriteconfig6 --file kdeglobals --group General --key toolBarFont 'Inter,9,-1,5,400,0,0,0,0,0,Regular'
        kwriteconfig6 --file kdeglobals --group General --key menuFont 'Inter,10,-1,5,400,0,0,0,0,0,Regular'
        kwriteconfig6 --file kdeglobals --group Icons --key Theme Papirus-Dark
        kwriteconfig6 --file kdeglobals --group KDE --key LookAndFeelPackage org.kde.breezedark.desktop
        kwriteconfig6 --file plasmarc --group Theme --key name kyth-dark
        if [[ -r /usr/share/wallpapers/kyth/contents/images/1920x1080.svg ]]; then
            kwriteconfig6 --file plasma-org.kde.plasma.desktop-appletsrc \
                --group Containments --group 1 --group Wallpaper --group org.kde.image --group General \
                --key Image /usr/share/wallpapers/kyth/contents/images/1920x1080.svg
        fi
    fi
    if [[ "${force}" == "1" || -z "${current_favorites}" ]]; then
        kwriteconfig6 --file kickoffrc --group Favorites --key FavoriteURLs \
            'applications:kyth-welcome.desktop,applications:kyth-app-store.desktop,applications:steam.desktop,applications:com.brave.Browser.desktop,applications:com.discordapp.Discord.desktop,applications:org.kde.konsole.desktop'
    fi

    # Ctrl+Shift+Esc opens Mission Center when installed, with KDE System
    # Monitor as the always-available fallback.
    if flatpak info io.missioncenter.MissionCenter >/dev/null 2>&1; then
        kwriteconfig6 --file kglobalshortcutsrc \
            --group services --group io.missioncenter.MissionCenter.desktop \
            --key _launch 'Ctrl+Shift+Esc'
        kwriteconfig6 --file kglobalshortcutsrc \
            --group org.kde.plasma-systemmonitor.desktop \
            --key _launch 'none,none,System Monitor'
    else
        kwriteconfig6 --file kglobalshortcutsrc \
            --group org.kde.plasma-systemmonitor.desktop \
            --key _launch 'Ctrl+Shift+Esc,none,System Monitor'
    fi

    # Double-click to open files: predictable across Dolphin, desktop icons, and
    # file dialogs for people arriving from pointer-first desktops.
    kwriteconfig6 --file kdeglobals --group KDE --key SingleClick --type bool false

    # Keep Kickoff categories quiet after first-boot Flatpak/app installs.
    kwriteconfig6 --file kickoffrc \
        --group General \
        --key highlightNewlyInstalledApps \
        --type bool false

    # Clipboard history on Meta+V.
    # Klipper ships enabled but history is off by default; turn it on with a
    # 25-item buffer so paste history stays useful without turning into a log.
    kwriteconfig6 --file klipperrc --group General --key KeepClipboardContents --type bool true
    kwriteconfig6 --file klipperrc --group General --key MaxClipItems 25
    kwriteconfig6 --file kglobalshortcutsrc \
        --group org.kde.klipper.desktop \
        --key show_clipboard_history \
        'Meta+V,Ctrl+Alt+V,Show Clipboard History'

    # Meta+E opens the file manager and Meta+Shift+S starts a rectangular
    # screenshot. The Move From Windows page applies the same migration shortcuts;
    # its "Restore KDE Defaults" button remains the opt-out.
    kwriteconfig6 --file kglobalshortcutsrc \
        --group services --group org.kde.dolphin.desktop \
        --key _launch 'Meta+E'
    kwriteconfig6 --file kglobalshortcutsrc \
        --group org.kde.spectacle.desktop \
        --key RectangularRegionScreenShot \
        'Meta+Shift+S,Meta+Shift+S,Capture Rectangular Region'
    kwriteconfig6 --file spectaclerc --group General --key defaultSaveLocation "file://${HOME}/Screenshots"
    kwriteconfig6 --file spectaclerc --group General --key lastSaveAsLocation "file://${HOME}/Screenshots"
    kwriteconfig6 --file spectaclerc --group General --key useReleaseToCapture --type bool true
    kwriteconfig6 --file spectaclerc --group ImageSave --key translatedScreenshotsFolder "${HOME}/Screenshots"

    # Screen lock: keep the KythOS default calmer than upstream Plasma's stock
    # five-minute lock while still locking on resume.
    kwriteconfig6 --file kscreenlockerrc --group Daemon --key Autolock --type bool true
    kwriteconfig6 --file kscreenlockerrc --group Daemon --key LockGracePeriod 5
    kwriteconfig6 --file kscreenlockerrc --group Daemon --key LockOnResume --type bool true
    kwriteconfig6 --file kscreenlockerrc --group Daemon --key Timeout 15
    kwriteconfig6 --file kscreenlockerrc --group Greeter --group Wallpaper --group org.kde.image --group General \
        --key Image /usr/share/wallpapers/kyth/contents/images/1920x1080.svg

    # Alt+Tab window switcher: Thumbnail Grid gives a modern, scannable overview.
    # KWin ships it built in and made it the default in Plasma 6.4, but configs
    # carried over from earlier installs (or kyth's previous "thumbnails" strip
    # override) can still select an older layout — pin the grid explicitly.
    # TabBoxAlternative* sets the same layout for the reverse direction (Alt+Shift+Tab).
    kwriteconfig6 --file kwinrc --group TabBox --key LayoutName thumbnail_grid
    kwriteconfig6 --file kwinrc --group TabBox --key ShowDesktop --type bool false
    kwriteconfig6 --file kwinrc --group TabBoxAlternative --key LayoutName thumbnail_grid

    # Keep upgraded users on the same underscore, box, and X titlebar controls.
    kwriteconfig6 --file kwinrc --group org.kde.kdecoration2 --key ButtonsOnLeft ""
    kwriteconfig6 --file kwinrc --group org.kde.kdecoration2 --key ButtonsOnRight IAX
    kwriteconfig6 --file kwinrc --group org.kde.kdecoration2 --key library org.kde.breeze
    kwriteconfig6 --file kwinrc --group org.kde.kdecoration2 --key theme Breeze
    qdbus_cmd=""
    for candidate in qdbus6 qdbus-qt6 qdbus; do
        if command -v "${candidate}" >/dev/null 2>&1; then
            qdbus_cmd="${candidate}"
            break
        fi
    done
    if [[ -n "${qdbus_cmd}" ]]; then
        "${qdbus_cmd}" org.kde.KWin /KWin reconfigure >/dev/null 2>&1 || true
    fi

    # Desktop right-click menu: keep wallpaper/display personalization easy to
    # discover. KDE's default context menu puts display settings behind two clicks.
    kwriteconfig6 --file kwinrc --group Plugins --key desktopchangeosdEnabled --type bool false

    # Mixed refresh rate — compositor latency policy.
    # KWin Plasma 6 renders each output at its own refresh rate independently, but
    # defaults to "medium" latency which can cause visible tearing and flicker when
    # a window is dragged between a 144 Hz and 60 Hz display. "extreme" eliminates
    # the per-frame delay that causes the jitter without increasing CPU usage.
    kwriteconfig6 --file kwinrc --group Compositing --key LatencyPolicy extreme
    # Disable adaptive sync on secondary displays by default to prevent frame-rate
    # lock-step when the primary is in VRR mode and the secondary is fixed-refresh.
    kwriteconfig6 --file kwinrc --group Compositing --key AllowTearing --type bool false

    # KDE Discover update notifications — disabled in favour of kyth-update-notifier.
    # Having two independent "update available" badges (Discover + kyth tray) confuses
    # users who don't know which one covers what. The kyth tray handles both OS image
    # updates and Flatpak app updates; Discover's badge is redundant and contradictory.
    kwriteconfig6 --file plasma-discoverrc --group UpdatesNotifier --key UseNotifications --type bool false

    # Dolphin/File Explorer comfort: remember view properties per folder, keep
    # previews available, and use a visible location bar instead of breadcrumbs
    # for easier path copy/paste during support and migration.
    kwriteconfig6 --file dolphinrc --group General --key RememberOpenedTabs --type bool true
    kwriteconfig6 --file dolphinrc --group General --key ShowFullPath --type bool true
    kwriteconfig6 --file dolphinrc --group General --key UseTabForSplitViewSwitch --type bool true
    kwriteconfig6 --file dolphinrc --group General --key ShowSpaceInfo --type bool true
    kwriteconfig6 --file dolphinrc --group General --key BrowseThroughArchives --type bool true
    kwriteconfig6 --file dolphinrc --group General --key ShowToolTips --type bool true
    kwriteconfig6 --file dolphinrc --group DetailsMode --key PreviewSize 32
    kwriteconfig6 --file dolphinrc --group PreviewSettings --key Plugins \
        'audiothumbnail,comicbookthumbnail,cursorthumbnail,djvuthumbnail,ebookthumbnail,exrthumbnail,ffmpegthumbs,imagethumbnail,jpegthumbnail,kraorathumbnail,windowsexethumbnail'
fi

brave_desktop_src=""
for candidate in \
    /var/lib/flatpak/exports/share/applications/com.brave.Browser.desktop \
    /usr/share/applications/com.brave.Browser.desktop \
    /usr/local/share/applications/com.brave.Browser.desktop; do
    if [[ -f "${candidate}" ]]; then
        brave_desktop_src="${candidate}"
        break
    fi
done

if [[ -n "${brave_desktop_src}" ]]; then
    brave_desktop_dst="${HOME}/.local/share/applications/com.brave.Browser.desktop"
    mkdir -p "$(dirname "${brave_desktop_dst}")"
    cp "${brave_desktop_src}" "${brave_desktop_dst}"
    if ! grep -q -- '--password-store=basic' "${brave_desktop_dst}"; then
        sed -i -E '/^Exec=/ s#(com\.brave\.Browser)( |$)#\1 --password-store=basic\2#' "${brave_desktop_dst}"
        if ! grep -q '^Exec=.*flatpak run ' "${brave_desktop_dst}"; then
            sed -i -E '/^Exec=/ s#(brave-browser|brave)( |$)#\1 --password-store=basic\2#' "${brave_desktop_dst}"
        fi
    fi
fi

if command -v /usr/bin/kyth-set-kickoff-icon >/dev/null 2>&1; then
    /usr/bin/kyth-set-kickoff-icon >/dev/null 2>&1 || true
fi

if command -v /usr/bin/kyth-apply-desktop-layout >/dev/null 2>&1; then
    if [[ "${force}" == "1" ]]; then
        /usr/bin/kyth-apply-desktop-layout --force
    elif [[ "${had_polish_stamp}" == "0" ]]; then
        /usr/bin/kyth-apply-desktop-layout --initial >/dev/null 2>&1 || true
    fi
fi

if command -v kbuildsycoca6 >/dev/null 2>&1; then
    kbuildsycoca6 --noincremental >/dev/null 2>&1 || true
fi

if command -v /usr/bin/kyth-steam-game-export >/dev/null 2>&1; then
    /usr/bin/kyth-steam-game-export >/dev/null 2>&1 || true
fi

if command -v /usr/bin/kyth-web-app-categorize >/dev/null 2>&1; then
    /usr/bin/kyth-web-app-categorize >/dev/null 2>&1 || true
fi

if command -v /usr/bin/kyth-vscode-wallet >/dev/null 2>&1; then
    /usr/bin/kyth-vscode-wallet >/dev/null 2>&1 || true
fi

if command -v /usr/bin/kyth-apply-role-preset >/dev/null 2>&1 \
    && [[ "${force}" == "1" || "${had_polish_stamp}" == "0" ]]; then
    role_profile="everyday"
    if [[ -r "${HOME}/.local/share/kyth/profile" ]]; then
        role_profile="$(head -n 1 "${HOME}/.local/share/kyth/profile" 2>/dev/null || printf 'everyday')"
    fi
    /usr/bin/kyth-apply-role-preset "${role_profile}" >/dev/null 2>&1 || true
fi

if [[ -d "${HOME}/Desktop" && ( "${force}" == "1" || "${had_polish_stamp}" == "0" ) ]] \
    && [[ -f /usr/share/applications/kyth-welcome.desktop ]]; then
    cp /usr/share/applications/kyth-welcome.desktop "${HOME}/Desktop/kyth-welcome.desktop" || true
    chmod 0755 "${HOME}/Desktop/kyth-welcome.desktop" 2>/dev/null || true
fi

# Recycle Bin on the desktop for existing accounts. Seeded once per polish
# version — deleting it afterwards is respected until the next version bump.
if [[ -d "${HOME}/Desktop" && ! -e "${HOME}/Desktop/kyth-recycle-bin.desktop" ]] \
    && [[ -f /usr/share/kyth/kyth-recycle-bin.desktop ]]; then
    cp /usr/share/kyth/kyth-recycle-bin.desktop "${HOME}/Desktop/kyth-recycle-bin.desktop" || true
fi

touch "${stamp}"
rm -f "${old_autostart}" "${HOME}/.config/autostart/kyth-user-polish.desktop" 2>/dev/null || true
POLISHEOF
chmod +x /usr/bin/kyth-user-polish

# Backward-compatible command name used by existing docs, support notes, and
# old smoke-check output. It now runs the same build-integrated polish pass.
cat >/usr/bin/kyth-windows-friendly-defaults <<'WINDEFAULTEOF'
#!/usr/bin/env bash
exec /usr/bin/kyth-user-polish "$@"
WINDEFAULTEOF
chmod +x /usr/bin/kyth-windows-friendly-defaults

cat >/etc/skel/.config/autostart/kyth-user-polish.desktop <<'POLISHDESKTOPEOF'
[Desktop Entry]
Type=Application
Name=KythOS: User Comfort Polish
Exec=/usr/bin/kyth-user-polish
X-KDE-autostart-after=panel
Hidden=false
NoDisplay=true
POLISHDESKTOPEOF

# Global autostart means existing users receive new polish migrations after an
# OS update too; the version stamp above prevents repeated preference churn.
install -m 0644 /etc/skel/.config/autostart/kyth-user-polish.desktop \
	/etc/xdg/autostart/kyth-user-polish.desktop

# ── Web app launcher grouping ─────────────────────────────────────────────────
# Chromium-family browsers create PWA launchers without Categories=. KDE cannot
# classify those launchers and drops them into Lost and Found. Add a custom
# category only when the browser did not provide one, preserving any category a
# user assigns later with the menu editor.
cat >/usr/bin/kyth-web-app-categorize <<'WEBAPPCATEGORIZEEOF'
#!/usr/bin/env bash
set -euo pipefail

app_dir="${HOME}/.local/share/applications"
[[ -d "${app_dir}" ]] || exit 0

changed=0
shopt -s nullglob
for launcher in \
    "${app_dir}"/chrome-*.desktop \
    "${app_dir}"/chromium-*.desktop \
    "${app_dir}"/brave-*.desktop \
    "${app_dir}"/msedge-*.desktop \
    "${app_dir}"/com.google.Chrome.flextop.*.desktop \
    "${app_dir}"/org.chromium.Chromium.flextop.*.desktop \
    "${app_dir}"/com.brave.Browser.flextop.*.desktop \
    "${app_dir}"/com.microsoft.Edge.flextop.*.desktop; do
    grep -Eq -- '--app(-id)?=' "${launcher}" || continue
    grep -q '^Categories=' "${launcher}" && continue
    sed -i '/^\[Desktop Entry\]$/a Categories=X-KythWebApp;' "${launcher}"
    changed=1
done

if (( changed )) && command -v kbuildsycoca6 >/dev/null 2>&1; then
    kbuildsycoca6 --noincremental >/dev/null 2>&1 || true
fi
WEBAPPCATEGORIZEEOF
chmod +x /usr/bin/kyth-web-app-categorize

mkdir -p /etc/systemd/user/default.target.wants
cat >/etc/systemd/user/kyth-web-app-categorize.service <<'WEBAPPSERVICEEOF'
[Unit]
Description=Place browser-installed web apps in the Web Apps launcher folder

[Service]
Type=oneshot
ExecStart=/usr/bin/kyth-web-app-categorize
WEBAPPSERVICEEOF

cat >/etc/systemd/user/kyth-web-app-categorize.path <<'WEBAPPPATHEOF'
[Unit]
Description=Watch for browser-installed web app launchers

[Path]
PathChanged=%h/.local/share/applications
Unit=kyth-web-app-categorize.service

[Install]
WantedBy=default.target
WEBAPPPATHEOF
ln -sf /etc/systemd/user/kyth-web-app-categorize.path \
	/etc/systemd/user/default.target.wants/kyth-web-app-categorize.path

# Seed the same familiar folder layout into fresh homes. The autostart helper
# repairs these for existing users and for accounts created by unusual tools.
mkdir -p \
	/etc/skel/Desktop \
	/etc/skel/Documents \
	/etc/skel/Downloads \
	/etc/skel/Games \
	/etc/skel/Music \
	/etc/skel/Pictures \
	/etc/skel/Public \
	/etc/skel/Templates \
	/etc/skel/Videos

cat >/etc/skel/Games/.directory <<'GAMESDIREEOF'
[Desktop Entry]
Icon=applications-games
Name=Games
GAMESDIREEOF

cat >/etc/skel/.config/user-dirs.dirs <<'USERDIRSEOF'
XDG_DESKTOP_DIR="$HOME/Desktop"
XDG_DOWNLOAD_DIR="$HOME/Downloads"
XDG_TEMPLATES_DIR="$HOME/Templates"
XDG_PUBLICSHARE_DIR="$HOME/Public"
XDG_DOCUMENTS_DIR="$HOME/Documents"
XDG_MUSIC_DIR="$HOME/Music"
XDG_PICTURES_DIR="$HOME/Pictures"
XDG_VIDEOS_DIR="$HOME/Videos"
USERDIRSEOF

cat >/etc/skel/.config/plasma-org.kde.plasma.desktop-appletsrc <<'PLASMADESKTOPEOF'
[Containments][1]
wallpaperplugin=org.kde.image

[Containments][1][Wallpaper][org.kde.image][General]
Image=/usr/share/wallpapers/kyth/contents/images/1920x1080.svg
PLASMADESKTOPEOF

# ── MangoHud defaults ─────────────────────────────────────────────────────────
# Ship a sensible system-wide config so MangoHud shows useful info out of the box.
# Users can override in ~/.config/MangoHud/MangoHud.conf or per-app.
mkdir -p /etc/MangoHud
install -m 0644 /ctx/MangoHud.conf /etc/MangoHud/MangoHud.conf

# ── vkBasalt defaults ─────────────────────────────────────────────────────────
# vkBasalt is inactive unless ENABLE_VKBASALT=1 is set per-game.
# Ship a default config (CAS sharpening) so it works correctly when enabled.
# Users can override with ~/.config/vkBasalt/vkBasalt.conf
install -m 0644 /ctx/vkBasalt.conf /etc/vkBasalt.conf

# ── KythOS Helper app — /ctx file installs ──────────────────────────────────────
install -m 0755 /ctx/kyth-welcome/kyth-welcome /usr/bin/kyth-welcome
# /usr/bin/kyth-welcome is a thin shim; the application package lives here.
mkdir -p /usr/lib/kyth-welcome
cp -a /ctx/kyth-welcome/kyth_welcome /usr/lib/kyth-welcome/
rm -rf /usr/lib/kyth-welcome/kyth_welcome/__pycache__
find /usr/lib/kyth-welcome -type d -exec chmod 0755 {} +
find /usr/lib/kyth-welcome -type f -exec chmod 0644 {} +
install -m 0755 /ctx/kyth-welcome/kyth-welcome-launch /usr/bin/kyth-welcome-launch
install -m 0644 /ctx/kyth-welcome/kyth-welcome.desktop \
	/usr/share/applications/kyth-welcome.desktop
cat >/usr/share/applications/kyth-app-store.desktop <<'APPSTOREEOF'
[Desktop Entry]
Type=Application
Name=KythOS App Store
GenericName=App Store
Comment=Find and install trusted apps on KythOS
Exec=/usr/bin/kyth-welcome-launch --page "App Store"
Icon=plasmadiscover
Terminal=false
Categories=Settings;PackageManager;
Keywords=apps;store;software;flatpak;install;remove;
StartupNotify=true
StartupWMClass=kyth-welcome
APPSTOREEOF
install -m 0755 /ctx/kyth-partition-install.sh /usr/bin/kyth-partition-install

# Place System Hub on the desktop for all new users. The executable bit is
# required so KDE Plasma 6 treats it as trusted without prompting the user.
mkdir -p /etc/skel/Desktop
install -m 0755 /ctx/kyth-welcome/kyth-welcome.desktop \
	/etc/skel/Desktop/kyth-welcome.desktop

# Recycle Bin on the desktop keeps deletion recovery visible. Type=Link entries
# open in Dolphin and need no executable/trust bit. Kept in /usr/share/kyth so
# the user-polish pass can seed existing accounts too.
mkdir -p /usr/share/kyth
cat >/usr/share/kyth/kyth-recycle-bin.desktop <<'TRASHEOF'
[Desktop Entry]
Type=Link
URL=trash:/
Name=Recycle Bin
GenericName=Trash
Icon=user-trash
TRASHEOF
install -m 0644 /usr/share/kyth/kyth-recycle-bin.desktop \
	/etc/skel/Desktop/kyth-recycle-bin.desktop

# ── Storage Sense ─────────────────────────────────────────────────────────────
# Automatic housekeeping: empty Recycle Bin items older than 30 days, drop unused
# Flatpak runtimes, vacuum the user journal. Opt-in: the timer ships disabled and
# System Hub -> Health Report has the on/off switch.
cat >/usr/bin/kyth-storage-sense <<'STORAGESENSEEOF'
#!/usr/bin/env bash
# KythOS Storage Sense — enable/disable from System Hub → Health Report.
set -uo pipefail

days=30
info_dir="${HOME}/.local/share/Trash/info"
files_dir="${HOME}/.local/share/Trash/files"
now=$(date +%s)

# Trash entries record their deletion time in .trashinfo (XDG trash spec);
# only entries older than the cutoff are removed, never the whole bin.
if [[ -d "${info_dir}" ]]; then
    for info in "${info_dir}"/*.trashinfo; do
        [[ -e "${info}" ]] || continue
        deleted=$(sed -n 's/^DeletionDate=//p' "${info}" | head -1)
        [[ -n "${deleted}" ]] || continue
        ts=$(date -d "${deleted}" +%s 2>/dev/null) || continue
        if (( now - ts > days * 86400 )); then
            name=$(basename "${info}" .trashinfo)
            rm -rf -- "${files_dir:?}/${name}" "${info}" 2>/dev/null || true
        fi
    done
fi

flatpak uninstall --unused -y --noninteractive >/dev/null 2>&1 || true
journalctl --user --vacuum-time=30d >/dev/null 2>&1 || true
STORAGESENSEEOF
chmod +x /usr/bin/kyth-storage-sense

cat >/usr/lib/systemd/user/kyth-storage-sense.service <<'STORAGESENSESVCEOF'
[Unit]
Description=KythOS Storage Sense cleanup

[Service]
Type=oneshot
ExecStart=/usr/bin/kyth-storage-sense
STORAGESENSESVCEOF

cat >/usr/lib/systemd/user/kyth-storage-sense.timer <<'STORAGESENSETIMEREOF'
[Unit]
Description=Weekly KythOS Storage Sense cleanup

[Timer]
OnCalendar=weekly
Persistent=true
RandomizedDelaySec=1h

[Install]
WantedBy=timers.target
STORAGESENSETIMEREOF

install -m 0755 /ctx/kyth-welcome/kyth-update-notifier /usr/bin/kyth-update-notifier
install -m 0644 /ctx/kyth-welcome/kyth-update-notifier.desktop \
	/usr/share/applications/kyth-update-notifier.desktop
# Autostart the notifier for new user accounts
mkdir -p /etc/skel/.config/autostart
install -m 0644 /ctx/kyth-welcome/kyth-update-notifier.desktop \
	/etc/skel/.config/autostart/kyth-update-notifier.desktop

# User-session confidence checks. These show friendly notifications and are
# version/deployment-gated so they do not nag on every login.
mkdir -p /etc/xdg/autostart
cat >/etc/xdg/autostart/kyth-post-update-check.desktop <<'POSTUPDATEAUTOSTARTEOF'
[Desktop Entry]
Type=Application
Name=KythOS Post-Update Check
Exec=/usr/bin/kyth-post-update-check --no-notify
NoDisplay=true
X-KDE-autostart-after=panel
POSTUPDATEAUTOSTARTEOF

cat >/etc/xdg/autostart/kyth-firstboot-app-status.desktop <<'APPSTATUSAUTOSTARTEOF'
[Desktop Entry]
Type=Application
Name=KythOS App Setup Status
Exec=/usr/bin/kyth-firstboot-app-status
NoDisplay=true
X-KDE-autostart-after=panel
APPSTATUSAUTOSTARTEOF

# Steam Flatpak writes game shortcuts inside its sandbox. Refresh host menu
# exports quietly at login so installed games appear under Games in KDE.
mkdir -p /etc/xdg/autostart
cat >/etc/xdg/autostart/kyth-steam-game-export.desktop <<'STEAMEXPORTAUTOSTARTEOF'
[Desktop Entry]
Type=Application
Name=KythOS Steam Game Menu Export
Exec=/usr/bin/kyth-steam-game-export
NoDisplay=true
X-KDE-autostart-after=panel
STEAMEXPORTAUTOSTARTEOF

# Import-smoke the helper during the build so syntax errors, missing Python
# dependencies, and top-level failures fail the image without running slow
# desktop and hardware probes inside the build container.
python3 -c '
import importlib.machinery, importlib.util, pathlib
path = pathlib.Path("/usr/bin/kyth-welcome")
loader = importlib.machinery.SourceFileLoader("kyth_welcome_smoke", str(path))
spec = importlib.util.spec_from_loader(loader.name, loader)
module = importlib.util.module_from_spec(spec)
loader.exec_module(module)
'

install -m 0755 /ctx/game-performance /usr/bin/game-performance
install -m 0755 /ctx/kyth-gamescope /usr/bin/kyth-gamescope
install -m 0755 /ctx/kyth-performance-mode /usr/bin/kyth-performance-mode
install -m 0755 /ctx/kyth-scx /usr/bin/kyth-scx
install -m 0755 /ctx/kyth-nvme-tuning /usr/bin/kyth-nvme-tuning
install -m 0755 /ctx/zink-run /usr/bin/zink-run
install -m 0755 /ctx/low-latency-run /usr/bin/low-latency-run
install -m 0755 /ctx/kyth-kerver /usr/bin/kyth-kerver
install -m 0755 /ctx/kyth-device-info /usr/bin/kyth-device-info
install -m 0755 /ctx/kyth-smoke-check /usr/bin/kyth-smoke-check
install -m 0755 /ctx/kyth-post-update-check /usr/bin/kyth-post-update-check
install -m 0755 /ctx/kyth-firstboot-app-status /usr/bin/kyth-firstboot-app-status
install -m 0755 /ctx/kyth-controller-check /usr/bin/kyth-controller-check
install -m 0755 /ctx/kyth-resume-check /usr/bin/kyth-resume-check
install -m 0755 /ctx/kyth-nvidia-status /usr/bin/kyth-nvidia-status
install -m 0755 /ctx/kyth-creator-check /usr/bin/kyth-creator-check
install -m 0755 /ctx/kyth-davinci-install /usr/bin/kyth-davinci-install
install -m 0755 /ctx/kyth-widevine-install /usr/bin/kyth-widevine-install
install -m 0755 /ctx/kyth-duperemove /usr/bin/kyth-duperemove
install -m 0755 /ctx/kyth-distrobox-root-launch /usr/bin/kyth-distrobox-root-launch
install -m 0755 /ctx/kyth-local-bin-migrate /usr/bin/kyth-local-bin-migrate
install -m 0755 /ctx/kyth-nearby-share /usr/bin/kyth-nearby-share
install -m 0755 /ctx/kyth-setup-transfer /usr/bin/kyth-setup-transfer
install -m 0755 /ctx/kyth-dynamic-lock /usr/bin/kyth-dynamic-lock
install -m 0644 /ctx/kyth-duperemove.service /usr/lib/systemd/system/kyth-duperemove.service
install -m 0644 /ctx/kyth-duperemove.timer /usr/lib/systemd/system/kyth-duperemove.timer
install -m 0644 /ctx/kyth-local-bin-migrate.service /usr/lib/systemd/system/kyth-local-bin-migrate.service
install -m 0755 /ctx/kyth-topgrade-migrate /usr/bin/kyth-topgrade-migrate
install -m 0755 /ctx/kyth-vscode-wallet /usr/bin/kyth-vscode-wallet
mkdir -p /usr/lib/systemd/user /usr/lib/systemd/user/default.target.wants
install -m 0644 /ctx/kyth-dynamic-lock.service /usr/lib/systemd/user/kyth-dynamic-lock.service
cat >/usr/lib/systemd/user/kyth-browser-wallet-defaults.service <<'WALLETDEFAULTSEOF'
[Unit]
Description=Apply quiet VS Code and Brave wallet defaults
ConditionPathExists=!%h/.local/state/kyth/browser-wallet-defaults-v1

[Service]
Type=oneshot
ExecStart=/usr/bin/bash -c 'set -euo pipefail; /usr/bin/kyth-vscode-wallet; mkdir -p "${HOME}/.local/state/kyth"; touch "${HOME}/.local/state/kyth/browser-wallet-defaults-v1"'

[Install]
WantedBy=default.target
WALLETDEFAULTSEOF
ln -sf ../kyth-browser-wallet-defaults.service \
	/usr/lib/systemd/user/default.target.wants/kyth-browser-wallet-defaults.service
install -m 0644 /ctx/kyth-topgrade-migrate.service /usr/lib/systemd/system/kyth-topgrade-migrate.service
install -m 0755 /ctx/kyth-vpn-connect/kyth-vpn-connect /usr/bin/kyth-vpn-connect
install -m 0644 /ctx/kyth-vpn-connect/kyth-vpn-connect.desktop \
	/usr/share/applications/kyth-vpn-connect.desktop
install -m 0755 /ctx/kyth-vpnc-script /usr/libexec/kyth-vpnc-script
install -m 0755 /ctx/kyth-vpn-status/kyth-vpn-status /usr/bin/kyth-vpn-status
# ── Downloaded installer MIME interception ───────────────────────────────────
# When a Windows user double-clicks a .exe/.msi or downloaded .rpm in Dolphin,
# show a dialog that suggests the best KythOS path instead of failing silently
# or teaching the wrong mutable-system model.
# The handler is registered as the system-wide default for these installer MIME
# types; users can override per-app via Dolphin's "Open With" dialog.
install -m 0755 /ctx/kyth-exe-handler /usr/bin/kyth-exe-handler
install -m 0644 /ctx/kyth-exe-handler.desktop \
	/usr/share/applications/kyth-exe-handler.desktop

# Keep expert tools installed without crowding a new user's app launcher.
# System Hub still exposes the relevant guided actions, and every binary remains
# available from a terminal. /usr/local/share takes precedence over RPM entries.
mkdir -p /usr/local/share/applications
for _hidden_desktop in \
	com.gerbilsoft.rom-properties.rp-config.desktop \
	htop.desktop \
	jstest-gtk.desktop \
	mpv.desktop \
	nvim.desktop \
	nvtop.desktop \
	org.corectrl.CoreCtrl.desktop \
	org.kde.drkonqi.coredump.gui.desktop \
	org.kde.kdebugsettings.desktop \
	org.kde.kjournaldbrowser.desktop \
	remote-viewer.desktop; do
	cat >"/usr/local/share/applications/${_hidden_desktop}" <<'HIDDENDESKTOPEOF'
[Desktop Entry]
Type=Application
Name=Hidden expert tool
Hidden=true
HIDDENDESKTOPEOF
done
unset _hidden_desktop

# Register as system-wide default for common installer MIME types.
# /etc/xdg/mimeapps.list is the XDG-standard location for system defaults;
# it is read before per-user ~/.config/mimeapps.list so new users get it
# automatically, and existing users can still override per-app.
mkdir -p /etc/xdg
cat >>/etc/xdg/mimeapps.list <<'MIMEAPPSEOF'
[Default Applications]
application/pdf=org.kde.okular.desktop;okularApplication_pdf.desktop;
application/epub+zip=org.kde.okular.desktop;okularApplication_epub.desktop;
image/jpeg=org.kde.gwenview.desktop;gwenview.desktop;
image/png=org.kde.gwenview.desktop;gwenview.desktop;
image/gif=org.kde.gwenview.desktop;gwenview.desktop;
image/webp=org.kde.gwenview.desktop;gwenview.desktop;
video/mp4=org.videolan.VLC.desktop;mpv.desktop;org.kde.haruna.desktop;
video/x-matroska=org.videolan.VLC.desktop;mpv.desktop;org.kde.haruna.desktop;
video/x-msvideo=org.videolan.VLC.desktop;mpv.desktop;org.kde.haruna.desktop;
audio/mpeg=org.videolan.VLC.desktop;mpv.desktop;org.kde.elisa.desktop;
audio/flac=org.videolan.VLC.desktop;mpv.desktop;org.kde.elisa.desktop;
text/plain=org.kde.kwrite.desktop;org.kde.kate.desktop;
text/markdown=org.kde.kwrite.desktop;org.kde.kate.desktop;
application/zip=org.kde.ark.desktop;ark.desktop;
application/x-7z-compressed=org.kde.ark.desktop;ark.desktop;
application/x-rar=org.kde.ark.desktop;ark.desktop;
application/x-tar=org.kde.ark.desktop;ark.desktop;
application/x-ms-dos-executable=kyth-exe-handler.desktop
application/x-msdos-program=kyth-exe-handler.desktop
application/x-dosexec=kyth-exe-handler.desktop
application/x-msi=kyth-exe-handler.desktop
application/x-msdownload=kyth-exe-handler.desktop
application/vnd.microsoft.portable-executable=kyth-exe-handler.desktop
application/x-rpm=kyth-exe-handler.desktop
application/x-redhat-package-manager=kyth-exe-handler.desktop
x-scheme-handler/http=com.brave.Browser.desktop;chromium-browser.desktop
x-scheme-handler/https=com.brave.Browser.desktop;chromium-browser.desktop
x-scheme-handler/mailto=com.getmailspring.Mailspring.desktop
inode/directory=org.kde.dolphin.desktop
MIMEAPPSEOF

# Rebuild the MIME/desktop database so KDE picks up the new handler immediately.
update-desktop-database /usr/share/applications/ 2>/dev/null || true

# Add nearby sharing to Dolphin's file context menu. KDE Connect handles
# discovery and transfer; the helper prompts when multiple paired devices are
# reachable.
mkdir -p /usr/share/kio/servicemenus
install -m 0644 /ctx/kyth-nearby-share.desktop \
	/usr/share/kio/servicemenus/kyth-nearby-share.desktop

# Surface a plain "Open Terminal Here" action in Dolphin. This is a small
# everyday comfort affordance for support notes, development, and modding.
cat >/usr/share/kio/servicemenus/kyth-open-terminal-here.desktop <<'TERMHEREDESKTOPEOF'
[Desktop Entry]
Type=Service
MimeType=inode/directory;
Actions=kythOpenTerminalHere;
X-KDE-Priority=TopLevel

[Desktop Action kythOpenTerminalHere]
Name=Open Terminal Here
Icon=utilities-terminal
Exec=konsole --workdir %f
TERMHEREDESKTOPEOF

# ── Right-click "New Document" templates for Dolphin ─────────────────────────
# Any file placed in ~/Templates appears in Dolphin's right-click → Create New
# → Document menu. Seeding /etc/skel ensures every new user gets the templates
# on first login.
mkdir -p /etc/skel/Templates
printf '' >"/etc/skel/Templates/Plain Text.txt"
printf '# Title\n\n' >"/etc/skel/Templates/Markdown.md"
printf '#!/usr/bin/env bash\nset -euo pipefail\n\n' >"/etc/skel/Templates/Shell Script.sh"
printf '#!/usr/bin/env python3\n\n\ndef main():\n    pass\n\n\nif __name__ == "__main__":\n    main()\n' \
	>"/etc/skel/Templates/Python Script.py"
chmod +x /etc/skel/Templates/"Shell Script.sh"
chmod +x /etc/skel/Templates/"Python Script.py"

install -m 0755 /ctx/kyth-rclone-update /usr/bin/kyth-rclone-update
install -m 0755 /ctx/kyth-session-snapshot /usr/bin/kyth-session-snapshot
install -m 0755 /ctx/kyth-report-issue /usr/bin/kyth-report-issue
install -m 0755 /ctx/kyth-ge-proton-update /usr/bin/kyth-ge-proton-update
install -m 0755 /ctx/kyth-steam-game-export /usr/bin/kyth-steam-game-export
install -m 0644 /ctx/kyth-ge-proton-update.service /usr/lib/systemd/user/kyth-ge-proton-update.service
install -m 0644 /ctx/kyth-ge-proton-update.timer /usr/lib/systemd/user/kyth-ge-proton-update.timer
install -m 0644 /ctx/kyth-flathub-setup.service /usr/lib/systemd/system/kyth-flathub-setup.service
install -m 0644 /ctx/kyth-default-flatpaks.service /usr/lib/systemd/system/kyth-default-flatpaks.service
install -m 0440 /ctx/kyth-bootc-sudo /etc/sudoers.d/kyth-bootc
install -m 0440 /ctx/kyth-sched-sudo /etc/sudoers.d/kyth-sched
install -m 0755 /ctx/kyth-hw-setup /usr/bin/kyth-hw-setup
install -m 0644 /ctx/kyth-hw-setup.service /usr/lib/systemd/system/kyth-hw-setup.service

# ── KythOS performance daemons ────────────────────────────────────────────────
install -m 0755 /ctx/kyth-sched /usr/bin/kyth-sched
install -m 0644 /ctx/kyth-sched.service /usr/lib/systemd/user/kyth-sched.service

install -m 0755 /ctx/kyth-telem /usr/bin/kyth-telem
install -m 0644 /ctx/kyth-telem.service /usr/lib/systemd/user/kyth-telem.service

install -m 0755 /ctx/kyth-update-watcher /usr/bin/kyth-update-watcher
install -m 0644 /ctx/kyth-update-watcher.service /usr/lib/systemd/system/kyth-update-watcher.service
install -m 0644 /ctx/kyth-update-watcher.timer /usr/lib/systemd/system/kyth-update-watcher.timer

# Zero-Python update escape hatch — works even when KythOS Hub is broken.
install -m 0755 /ctx/kyth-apply-update /usr/bin/kyth-apply-update
install -m 0644 /ctx/kyth-apply-update.desktop /usr/share/applications/kyth-apply-update.desktop

mkdir -p /etc/kyth
install -m 0644 /ctx/kyth-sched-profiles.toml /etc/kyth/sched-profiles.toml
install -m 0644 /ctx/auto-update.toml /etc/kyth/auto-update.toml
install -m 0644 /ctx/kyth-asus-supergfxd.rules /usr/lib/udev/rules.d/98-kyth-asus-supergfxd.rules

# Autostart on first login — removes itself after running once (like kyth-set-resolution).
mkdir -p /etc/skel/.config/autostart
cat >/etc/skel/.config/autostart/kyth-welcome.desktop <<'WELCOMEEOF'
[Desktop Entry]
Type=Application
Name=KythOS Helper
Exec=/usr/bin/kyth-welcome-launch
X-KDE-autostart-after=panel
Hidden=false
NoDisplay=true
WELCOMEEOF

# ── Bootc kernel arguments ────────────────────────────────────────────────────
# bootc reads kargs.d entries and adds them to the BLS boot entry at install time.
mkdir -p /usr/lib/bootc/kargs.d
cat >/usr/lib/bootc/kargs.d/99-kyth.toml <<'KARGSEOF'
kargs = ["quiet", "rhgb", "splash", "rd.plymouth=1", "plymouth.enable=1", "plymouth.ignore-serial-consoles", "systemd.show_status=false", "rd.systemd.show_status=false", "loglevel=3", "rd.udev.log_level=3", "vt.global_cursor_default=0", "threadirqs"]
KARGSEOF

# The early Plymouth layer runs before the daily dnf upgrade. Run the branding
# guard again here, after every package transaction, so upgraded Plymouth theme
# packages cannot restore upstream BGRT/spinner artwork into the final image.
install -Dm0755 /ctx/scripts/plymouth-branding-guard.sh \
	/usr/libexec/kyth-plymouth-branding-guard
/usr/libexec/kyth-plymouth-branding-guard \
	/ctx/branding/transparent-watermark.svg

mkdir -p /etc/dracut.conf.d
if [[ -f /etc/dracut.conf.d/99-kyth.conf ]]; then
	grep -q 'add_dracutmodules=.*kyth-plymouth' /etc/dracut.conf.d/99-kyth.conf ||
		printf '\nadd_dracutmodules+=" kyth-plymouth "\n' >>/etc/dracut.conf.d/99-kyth.conf
else
	cat >/etc/dracut.conf.d/99-kyth.conf <<'DRACUTEOF'
add_dracutmodules+=" ostree drm plymouth kyth-plymouth "
DRACUTEOF
fi
grep -q 'force_add_dracutmodules=.*kyth-plymouth' /etc/dracut.conf.d/99-kyth.conf ||
	printf 'force_add_dracutmodules+=" kyth-plymouth "\n' >>/etc/dracut.conf.d/99-kyth.conf

# Existing installs may still have older KythOS boot entries with serial/TTY
# console arguments that make Plymouth fall back to visible boot text. This
# one-shot migration fixes the bootloader entries after the updated image boots;
# the freshly staged deployment gets the clean kargs above at install/update time.
cat >/usr/lib/systemd/system/kyth-boot-splash-kargs.service <<'SPLASHKARGSEOF'
[Unit]
Description=KythOS boot splash kernel argument migration
ConditionPathExists=!/var/lib/kyth/boot-splash-kargs-v2
After=local-fs.target

[Service]
Type=oneshot
ExecStart=/usr/bin/bash -c 'set -e; mkdir -p /var/lib/kyth; if command -v grubby >/dev/null 2>&1; then grubby --update-kernel=ALL --remove-args="console=tty0 console=ttyS0,115200"; grubby --update-kernel=ALL --args="quiet rhgb splash rd.plymouth=1 plymouth.enable=1 plymouth.ignore-serial-consoles systemd.show_status=false rd.systemd.show_status=false loglevel=3 rd.udev.log_level=3 vt.global_cursor_default=0"; fi; touch /var/lib/kyth/boot-splash-kargs-v2'

[Install]
WantedBy=multi-user.target
SPLASHKARGSEOF
systemctl enable kyth-boot-splash-kargs.service 2>/dev/null || true

# Existing installs and newly staged bootc deployments can have bootloader
# metadata generated while the image still identified as Fedora. Keep visual
# boot classes and theme icons repaired so stale BLS grub_class=fedora entries
# cannot draw Fedora artwork during the handoff to Plymouth.
mkdir -p /usr/libexec
cat >/usr/libexec/kyth-boot-branding-guard <<'BOOTBRANDINGEOF'
#!/usr/bin/env bash
set -euo pipefail

boot_was_ro=0
cleanup() {
    if [[ "${boot_was_ro}" -eq 1 ]]; then
        mount -o remount,ro /boot || true
    fi
}
trap cleanup EXIT

if findmnt -no OPTIONS /boot 2>/dev/null | tr ',' '\n' | grep -qx ro; then
    if mount -o remount,rw /boot 2>/dev/null; then
        boot_was_ro=1
    else
        echo "WARNING: /boot is read-only; bootloader branding repair will skip unwritable entries" >&2
    fi
fi

for bls_dir in /boot/loader/entries /boot/efi/loader/entries; do
    [[ -d "${bls_dir}" ]] || continue
    while IFS= read -r -d '' entry; do
        [[ -w "${entry}" ]] || continue
        sed -i \
            -e 's/^title[[:space:]]Fedora Linux/title KythOS/' \
            -e 's/^title[[:space:]]Fedora/title KythOS/' \
            -e 's/^grub_class[[:space:]].*/grub_class kythos/' \
            -e 's/^sort-key[[:space:]]fedora$/sort-key kythos/' \
            "${entry}"
        grep -q '^grub_class[[:space:]]' "${entry}" || printf 'grub_class kythos\n' >> "${entry}"
    done < <(find "${bls_dir}" -maxdepth 1 -type f -name '*.conf' -print0)
done

mkdir -p /etc/default
if [[ -f /etc/default/grub ]]; then
    if grep -q '^GRUB_DISTRIBUTOR=' /etc/default/grub; then
        sed -i 's/^GRUB_DISTRIBUTOR=.*/GRUB_DISTRIBUTOR="KythOS"/' /etc/default/grub
    else
        printf '\nGRUB_DISTRIBUTOR="KythOS"\n' >> /etc/default/grub
    fi
else
    printf 'GRUB_DISTRIBUTOR="KythOS"\n' > /etc/default/grub
fi

for grub_icon_dir in \
    /boot/grub2/themes/system/icons \
    /boot/grub2/themes/starfield/icons \
    /usr/share/grub/themes/system/icons \
    /usr/share/grub/themes/starfield/icons; do
    [[ -d "${grub_icon_dir}" ]] || continue
    [[ -w "${grub_icon_dir}" ]] || continue
    if [[ -r /usr/share/pixmaps/kythos.png ]]; then
        for icon in kyth kythos fedora gnu-linux linux; do
            install -m 0644 /usr/share/pixmaps/kythos.png "${grub_icon_dir}/${icon}.png"
        done
    fi
done

if command -v grub2-mkconfig >/dev/null 2>&1 && [[ -d /boot/grub2 ]]; then
    grub2-mkconfig -o /boot/grub2/grub.cfg >/dev/null 2>&1 || true
fi
BOOTBRANDINGEOF
chmod 0755 /usr/libexec/kyth-boot-branding-guard

cat >/usr/lib/systemd/system/kyth-boot-branding.service <<'BOOTBRANDINGSERVICEEOF'
[Unit]
Description=Refresh KythOS bootloader branding
After=local-fs.target

[Service]
Type=oneshot
ExecStart=/usr/libexec/kyth-boot-branding-guard

[Install]
WantedBy=multi-user.target
BOOTBRANDINGSERVICEEOF
systemctl enable kyth-boot-branding.service 2>/dev/null || true

cat >/usr/lib/systemd/system/kyth-boot-branding.path <<'BOOTBRANDINGPATHEOF'
[Unit]
Description=Watch bootloader entries for KythOS branding repairs

[Path]
PathModified=/boot/loader/entries
PathModified=/boot/efi/loader/entries
Unit=kyth-boot-branding.service

[Install]
WantedBy=multi-user.target
BOOTBRANDINGPATHEOF
systemctl enable kyth-boot-branding.path 2>/dev/null || true

# Existing deployments already have an initramfs in /boot. Keep it aligned with
# the current KythOS Plymouth module and repair any fallback-theme leaks.
cat >/usr/libexec/kyth-refresh-boot-splash-initramfs <<'SPLASHINITRDSCRIPTEOF'
#!/usr/bin/env bash
set -euo pipefail

state_dir=/var/lib/kyth
fingerprint_file="${state_dir}/boot-splash-initramfs.sha256"
migration_marker="${state_dir}/boot-splash-initramfs-v17"
mkdir -p "${state_dir}"

if command -v plymouth-set-default-theme >/dev/null 2>&1; then
    plymouth-set-default-theme kyth || true
fi

if [[ -x /usr/libexec/kyth-boot-branding-guard ]]; then
    /usr/libexec/kyth-boot-branding-guard || true
fi

# On deployed ostree/bootc systems /usr is normally immutable. Only refresh
# fallback assets when the filesystem is writable; the image build already
# installs the Kyth Plymouth theme and dracut module into /usr.
if [[ -w /usr/share/plymouth && -x /usr/libexec/kyth-plymouth-branding-guard ]]; then
    /usr/libexec/kyth-plymouth-branding-guard || true
fi

if [[ ! -d /etc/dracut.conf.d && -w /etc ]]; then
    mkdir -p /etc/dracut.conf.d
fi
if [[ -w /etc/dracut.conf.d ]]; then
    if [[ -f /etc/dracut.conf.d/99-kyth.conf ]]; then
        grep -q 'add_dracutmodules=.*kyth-plymouth' /etc/dracut.conf.d/99-kyth.conf || \
            printf '\nadd_dracutmodules+=" kyth-plymouth "\n' >> /etc/dracut.conf.d/99-kyth.conf
    else
        cat > /etc/dracut.conf.d/99-kyth.conf <<'DRACUTEOF'
add_dracutmodules+=" ostree drm plymouth kyth-plymouth "
DRACUTEOF
    fi
    grep -q 'force_add_dracutmodules=.*kyth-plymouth' /etc/dracut.conf.d/99-kyth.conf || \
        printf 'force_add_dracutmodules+=" kyth-plymouth "\n' >> /etc/dracut.conf.d/99-kyth.conf
fi

fingerprint_current() {
    local input
    local inputs=(
        /usr/lib/dracut/modules.d/99kyth-plymouth/module-setup.sh
        /usr/libexec/kyth-plymouth-branding-guard
        /etc/dracut.conf.d/99-kyth.conf
        /etc/plymouth/plymouthd.conf
        /usr/share/plymouth/plymouthd.defaults
        /usr/share/kyth/branding/transparent-watermark.png
        /usr/share/pixmaps/system-logo-white.png
        /usr/share/plymouth/themes/kyth/kyth.plymouth
        /usr/share/plymouth/themes/kyth/kyth.script
        /usr/share/plymouth/themes/kyth/kyth-logo.png
    )
    {
        for input in "${inputs[@]}"; do
            if [[ -r "${input}" ]]; then
                sha256sum "${input}"
            else
                printf 'MISSING  %s\n' "${input}"
            fi
        done
    } | sha256sum | awk '{print $1}'
}

collect_images() {
    images=()
    local image kernel existing seen
    shopt -s nullglob
    for image in /boot/ostree/*/initramfs-*.img /boot/initramfs-*.img; do
        kernel="${image##*/initramfs-}"
        kernel="${kernel%.img}"
        [[ -d "/usr/lib/modules/${kernel}" ]] || continue

        seen=0
        for existing in "${images[@]}"; do
            if [[ "${existing}" == "${image}" ]]; then
                seen=1
                break
            fi
        done
        [[ "${seen}" -eq 0 ]] && images+=("${image}")
    done
    shopt -u nullglob
}

image_needs_refresh() {
    local image=$1
    local defaults listing logo ok

    command -v lsinitrd >/dev/null 2>&1 || return 0
    defaults="$(mktemp /tmp/kyth-plymouth-defaults.XXXXXX)"
    listing="$(mktemp /tmp/kyth-plymouth-listing.XXXXXX)"
    logo="$(mktemp /tmp/kyth-plymouth-logo.XXXXXX)"
    ok=1

    lsinitrd -f /usr/share/plymouth/plymouthd.defaults "${image}" > "${defaults}" 2>/dev/null || ok=0
    lsinitrd -f /usr/share/pixmaps/system-logo-white.png "${image}" > "${logo}" 2>/dev/null || ok=0
    lsinitrd "${image}" > "${listing}" 2>/dev/null || ok=0
    grep -q 'usr/share/plymouth/themes/kyth/kyth.plymouth' "${listing}" || ok=0
    grep -q 'usr/share/plymouth/themes/kyth/kyth.script' "${listing}" || ok=0
    grep -q 'usr/share/plymouth/themes/kyth/kyth-logo.png' "${listing}" || ok=0
    grep -q 'usr/share/plymouth/themes/default.plymouth' "${listing}" || ok=0
    [[ -r /usr/share/kyth/branding/transparent-watermark.png ]] || ok=0
    cmp -s "${logo}" /usr/share/kyth/branding/transparent-watermark.png || ok=0
    grep -q '^Theme=kyth$' "${defaults}" || ok=0
    grep -q '^ShowDelay=0$' "${defaults}" || ok=0
    grep -q '^DeviceTimeout=8$' "${defaults}" || ok=0
    if grep -Ei 'usr/share/plymouth/themes/(bgrt-fedora|bgrt|spinner)(/|$)' "${listing}" >&2; then
        ok=0
    fi
    rm -f "${defaults}" "${listing}" "${logo}"

    [[ "${ok}" -eq 1 ]] && return 1
    return 0
}

verify_image() {
    local image=$1
    local defaults listing logo

    command -v lsinitrd >/dev/null 2>&1 || return 0
    defaults="$(mktemp /tmp/kyth-plymouth-defaults.XXXXXX)"
    listing="$(mktemp /tmp/kyth-plymouth-listing.XXXXXX)"
    logo="$(mktemp /tmp/kyth-plymouth-logo.XXXXXX)"

    lsinitrd -f /usr/share/plymouth/plymouthd.defaults "${image}" > "${defaults}" || {
        echo "ERROR: refreshed initramfs is missing Plymouth defaults: ${image}" >&2
        rm -f "${defaults}" "${listing}" "${logo}"
        return 1
    }
    lsinitrd -f /usr/share/pixmaps/system-logo-white.png "${image}" > "${logo}" || {
        echo "ERROR: refreshed initramfs is missing transparent Plymouth system logo: ${image}" >&2
        rm -f "${defaults}" "${listing}" "${logo}"
        return 1
    }
    lsinitrd "${image}" > "${listing}" || {
        echo "ERROR: unable to inspect refreshed initramfs: ${image}" >&2
        rm -f "${defaults}" "${listing}" "${logo}"
        return 1
    }
    grep -q 'usr/share/plymouth/themes/kyth/kyth.plymouth' "${listing}" || {
        echo "ERROR: refreshed initramfs does not contain KythOS Plymouth theme: ${image}" >&2
        rm -f "${defaults}" "${listing}" "${logo}"
        return 1
    }
    grep -q 'usr/share/plymouth/themes/kyth/kyth.script' "${listing}" || {
        echo "ERROR: refreshed initramfs does not contain KythOS Plymouth script: ${image}" >&2
        rm -f "${defaults}" "${listing}" "${logo}"
        return 1
    }
    grep -q 'usr/share/plymouth/themes/kyth/kyth-logo.png' "${listing}" || {
        echo "ERROR: refreshed initramfs does not contain KythOS Plymouth logo: ${image}" >&2
        rm -f "${defaults}" "${listing}" "${logo}"
        return 1
    }
    grep -q 'usr/share/plymouth/themes/default.plymouth' "${listing}" || {
        echo "ERROR: refreshed initramfs does not force KythOS as the default Plymouth theme: ${image}" >&2
        rm -f "${defaults}" "${listing}" "${logo}"
        return 1
    }
    cmp -s "${logo}" /usr/share/kyth/branding/transparent-watermark.png || {
        echo "ERROR: refreshed initramfs still contains distro Plymouth system logo: ${image}" >&2
        rm -f "${defaults}" "${listing}" "${logo}"
        return 1
    }
    grep -q '^Theme=kyth$' "${defaults}" || {
        echo "ERROR: refreshed initramfs Plymouth defaults do not force Theme=kyth: ${image}" >&2
        rm -f "${defaults}" "${listing}" "${logo}"
        return 1
    }
    grep -q '^ShowDelay=0$' "${defaults}" || {
        echo "ERROR: refreshed initramfs Plymouth defaults do not draw immediately: ${image}" >&2
        rm -f "${defaults}" "${listing}" "${logo}"
        return 1
    }
    grep -q '^DeviceTimeout=8$' "${defaults}" || {
        echo "ERROR: refreshed initramfs Plymouth defaults are missing DeviceTimeout=8: ${image}" >&2
        rm -f "${defaults}" "${listing}" "${logo}"
        return 1
    }
    if grep -Ei 'usr/share/plymouth/themes/(bgrt-fedora|bgrt|spinner)(/|$)' "${listing}" >&2; then
        echo "ERROR: Plymouth fallback theme leaked into refreshed initramfs: ${image}" >&2
        rm -f "${defaults}" "${listing}" "${logo}"
        return 1
    fi

    rm -f "${defaults}" "${listing}" "${logo}"
}

current_fingerprint="$(fingerprint_current)"
collect_images

needs_refresh=0
if [[ ! -e "${migration_marker}" ]]; then
    needs_refresh=1
fi
if [[ -r "${fingerprint_file}" && "$(cat "${fingerprint_file}")" != "${current_fingerprint}" ]]; then
    needs_refresh=1
fi
if [[ "${#images[@]}" -eq 0 ]]; then
    needs_refresh=1
fi
for image in "${images[@]}"; do
    if image_needs_refresh "${image}"; then
        needs_refresh=1
    fi
done

if [[ "${needs_refresh}" -eq 0 ]]; then
    printf '%s\n' "${current_fingerprint}" > "${fingerprint_file}"
    touch "${migration_marker}"
    exit 0
fi

include_root="$(mktemp -d /tmp/kyth-plymouth-initramfs.XXXXXX)"
boot_was_ro=0
cleanup() {
    rm -rf "${include_root}"
    if [[ "${boot_was_ro}" -eq 1 ]]; then
        mount -o remount,ro /boot || true
    fi
}
trap cleanup EXIT

if findmnt -no OPTIONS /boot 2>/dev/null | tr ',' '\n' | grep -qx ro; then
    if mount -o remount,rw /boot 2>/dev/null; then
        boot_was_ro=1
    else
        echo "WARNING: /boot is read-only and could not be remounted; skipping initramfs refresh" >&2
        exit 0
    fi
fi

mkdir -p \
    "${include_root}/etc/plymouth" \
    "${include_root}/usr/share/plymouth" \
    "${include_root}/usr/share/pixmaps" \
    "${include_root}/usr/share/plymouth/themes"
printf '[Daemon]\nTheme=kyth\nShowDelay=0\nDeviceTimeout=8\nUseFirmwareBackground=false\n' \
    > "${include_root}/etc/plymouth/plymouthd.conf"
install -m 0644 \
    "${include_root}/etc/plymouth/plymouthd.conf" \
    "${include_root}/usr/share/plymouth/plymouthd.defaults"
if [[ -r /usr/share/kyth/branding/transparent-watermark.png ]]; then
    install -m 0644 /usr/share/kyth/branding/transparent-watermark.png \
        "${include_root}/usr/share/pixmaps/system-logo-white.png"
else
    printf '%s' 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNgYAAAAAMAASsJTYQAAAAASUVORK5CYII=' \
        | base64 -d > "${include_root}/usr/share/pixmaps/system-logo-white.png"
fi
cp -a /usr/share/plymouth/themes/kyth "${include_root}/usr/share/plymouth/themes/kyth"
ln -sfn kyth/kyth.plymouth "${include_root}/usr/share/plymouth/themes/default.plymouth"
rm -rf \
    "${include_root}/usr/share/plymouth/themes/bgrt-fedora" \
    "${include_root}/usr/share/plymouth/themes/bgrt" \
    "${include_root}/usr/share/plymouth/themes/spinner"

if [[ -w /etc/plymouth ]]; then
    install -m 0644 "${include_root}/etc/plymouth/plymouthd.conf" /etc/plymouth/plymouthd.conf
fi
if [[ -w /usr/share/plymouth ]]; then
    install -m 0644 "${include_root}/usr/share/plymouth/plymouthd.defaults" /usr/share/plymouth/plymouthd.defaults
fi
if [[ -w /usr/share/pixmaps ]]; then
    install -m 0644 "${include_root}/usr/share/pixmaps/system-logo-white.png" /usr/share/pixmaps/system-logo-white.png
fi

rebuilt=0
for image in "${images[@]}"; do
    kernel="${image##*/initramfs-}"
    kernel="${kernel%.img}"

    TMPDIR=/var/tmp dracut \
        --tmpdir /var/tmp \
        --no-hostonly \
        --kver "${kernel}" \
        --reproducible \
        --force \
        --add "drm plymouth ostree kyth-plymouth" \
        --include "${include_root}/etc/plymouth" /etc/plymouth \
        --include "${include_root}/usr/share/plymouth" /usr/share/plymouth \
        --include "${include_root}/usr/share/pixmaps/system-logo-white.png" /usr/share/pixmaps/system-logo-white.png \
        "${image}" \
        "${kernel}"
    verify_image "${image}"
    rebuilt=1
done

if [[ "${rebuilt}" -eq 0 ]]; then
    TMPDIR=/var/tmp dracut \
        --tmpdir /var/tmp \
        --regenerate-all \
        --force \
        --add "drm plymouth kyth-plymouth" \
        --include "${include_root}/etc/plymouth" /etc/plymouth \
        --include "${include_root}/usr/share/plymouth" /usr/share/plymouth \
        --include "${include_root}/usr/share/pixmaps/system-logo-white.png" /usr/share/pixmaps/system-logo-white.png
    collect_images
    for image in "${images[@]}"; do
        verify_image "${image}"
    done
fi

printf '%s\n' "${current_fingerprint}" > "${fingerprint_file}"
touch "${migration_marker}"
SPLASHINITRDSCRIPTEOF
chmod 0755 /usr/libexec/kyth-refresh-boot-splash-initramfs

cat >/usr/lib/systemd/system/kyth-boot-splash-initramfs.service <<'SPLASHINITRDEOF'
[Unit]
Description=Refresh KythOS boot splash initramfs
After=local-fs.target

[Service]
Type=oneshot
ExecStart=/usr/libexec/kyth-refresh-boot-splash-initramfs

[Install]
WantedBy=multi-user.target
SPLASHINITRDEOF
systemctl enable kyth-boot-splash-initramfs.service 2>/dev/null || true

# First-boot notice: shown once via Plymouth message_callback, then sentinel
# gates it so subsequent boots skip the message.
cat >/usr/lib/systemd/system/kyth-firstboot-notice.service <<'FBOOTEOF'
[Unit]
Description=KythOS first-boot Plymouth notice
After=plymouth-start.service
Before=plymouth-quit.service
DefaultDependencies=no
ConditionPathExists=!/var/lib/kyth/first-boot-done

[Service]
Type=oneshot
ExecStart=/usr/bin/bash -c 'mkdir -p /var/lib/kyth && touch /var/lib/kyth/first-boot-done && plymouth message --text="After login, open the KythOS System Hub to finish installing your preferred software."'

[Install]
WantedBy=sysinit.target
FBOOTEOF
systemctl enable kyth-firstboot-notice.service 2>/dev/null || true

# ── Security Tools menu group ──────────────────────────────────────────────────
# Define a custom "Security Tools" group in the XDG application menu so that
# Kali tools exported via distrobox-export land there instead of "Lost and Found".
# "Security" alone is not a recognized XDG main category, so apps without a main
# category fall through to KDE's catch-all bucket.  X-KythSecurity is our custom
# main category; the .menu merge file teaches KDE what group it belongs to.
mkdir -p /usr/share/desktop-directories
cat >/usr/share/desktop-directories/kyth-security.directory <<'SECDIREF'
[Desktop Entry]
Version=1.0
Type=Directory
Name=Security Tools
Comment=Security and penetration testing tools
Icon=security-high
SECDIREF

install -m 0644 /ctx/kyth-web-apps.directory \
	/usr/share/desktop-directories/kyth-web-apps.directory

mkdir -p /etc/xdg/menus/applications-merged
cat >/etc/xdg/menus/applications-merged/kyth-security.menu <<'SECMENUEOF'
<!DOCTYPE Menu PUBLIC "-//freedesktop//DTD Menu 1.0//EN"
  "http://www.freedesktop.org/standards/menu-spec/menu-1.0.dtd">
<Menu>
  <Name>Applications</Name>
  <!-- Explicit layout so Security Tools sorts alphabetically with standard categories.
       Merge files are processed last, so this Layout overrides the default ordering.
       <Merge type="menus"/> at the end catches any non-standard categories. -->
  <Layout>
    <Merge type="files"/>
    <Menuname>AudioVideo</Menuname>
    <Menuname>Development</Menuname>
    <Menuname>Education</Menuname>
    <Menuname>Game</Menuname>
    <Menuname>Graphics</Menuname>
    <Menuname>Internet</Menuname>
    <Menuname>Network</Menuname>
    <Menuname>Office</Menuname>
    <Menuname>Science</Menuname>
    <Menuname>Security Tools</Menuname>
    <Menuname>Settings</Menuname>
    <Menuname>System</Menuname>
    <Menuname>Utility</Menuname>
    <Menuname>Web Apps</Menuname>
    <Merge type="menus"/>
  </Layout>
  <Menu>
    <Name>Security Tools</Name>
    <Directory>kyth-security.directory</Directory>
    <Include>
      <Category>X-KythSecurity</Category>
    </Include>
  </Menu>
</Menu>
SECMENUEOF

install -m 0644 /ctx/kyth-web-apps.menu \
	/etc/xdg/menus/applications-merged/kyth-web-apps.menu

# ── Game Tools menu group ─────────────────────────────────────────────────────
# Keep the Games root focused on playable titles. Flatpak launchers and gaming
# helpers often advertise Categories=Game, so KDE otherwise mixes them with
# exported Steam game shortcuts. Match desktop IDs explicitly so optional tools
# move into this submenu whenever the user installs them.
cat >/usr/share/desktop-directories/kyth-game-tools.directory <<'GAMETOOLSDIREF'
[Desktop Entry]
Version=1.0
Type=Directory
Name=Tools
Comment=Game launchers, compatibility helpers, and save tools
Icon=applications-utilities
GAMETOOLSDIREF

cat >/etc/xdg/menus/applications-merged/kyth-game-tools.menu <<'GAMETOOLSMENUEOF'
<!DOCTYPE Menu PUBLIC "-//freedesktop//DTD Menu 1.0//EN"
  "http://www.freedesktop.org/standards/menu-spec/menu-1.0.dtd">
<Menu>
  <Name>Applications</Name>
  <Menu>
    <Name>Games</Name>
    <Menu>
      <Name>Tools</Name>
      <Directory>kyth-game-tools.directory</Directory>
      <Include>
        <Filename>com.valvesoftware.Steam.desktop</Filename>
        <Filename>net.lutris.Lutris.desktop</Filename>
        <Filename>com.heroicgameslauncher.hgl.desktop</Filename>
        <Filename>com.usebottles.bottles.desktop</Filename>
        <Filename>com.github.Matoking.protontricks.desktop</Filename>
        <Filename>com.github.mtkennerly.ludusavi.desktop</Filename>
        <Filename>net.davidotek.pupgui2.desktop</Filename>
        <Filename>org.prismlauncher.PrismLauncher.desktop</Filename>
        <Filename>io.github.benjamimgois.goverlay.desktop</Filename>
        <Filename>io.github.radiolamp.mangojuice.desktop</Filename>
      </Include>
    </Menu>
    <Exclude>
      <Filename>com.valvesoftware.Steam.desktop</Filename>
      <Filename>net.lutris.Lutris.desktop</Filename>
      <Filename>com.heroicgameslauncher.hgl.desktop</Filename>
      <Filename>com.usebottles.bottles.desktop</Filename>
      <Filename>com.github.Matoking.protontricks.desktop</Filename>
      <Filename>com.github.mtkennerly.ludusavi.desktop</Filename>
      <Filename>net.davidotek.pupgui2.desktop</Filename>
      <Filename>org.prismlauncher.PrismLauncher.desktop</Filename>
      <Filename>io.github.benjamimgois.goverlay.desktop</Filename>
      <Filename>io.github.radiolamp.mangojuice.desktop</Filename>
    </Exclude>
  </Menu>
</Menu>
GAMETOOLSMENUEOF

# LibreOffice Flatpak launchers intentionally advertise multiple freedesktop
# categories. Keep the suite together under Office instead of repeating Draw in
# Graphics and Math throughout KDE's Education submenus.
cat >/etc/xdg/menus/applications-merged/kyth-libreoffice.menu <<'LIBREOFFICEMENUEOF'
<!DOCTYPE Menu PUBLIC "-//freedesktop//DTD Menu 1.0//EN"
  "http://www.freedesktop.org/standards/menu-spec/menu-1.0.dtd">
<Menu>
  <Name>Applications</Name>
  <Menu>
    <Name>Graphics</Name>
    <Exclude>
      <Filename>org.libreoffice.LibreOffice.draw.desktop</Filename>
    </Exclude>
  </Menu>
  <Menu>
    <Name>Education</Name>
    <Exclude>
      <Filename>org.libreoffice.LibreOffice.math.desktop</Filename>
    </Exclude>
    <Menu>
      <Name>Mathematics</Name>
      <Exclude>
        <Filename>org.libreoffice.LibreOffice.math.desktop</Filename>
      </Exclude>
    </Menu>
    <Menu>
      <Name>Science</Name>
      <Exclude>
        <Filename>org.libreoffice.LibreOffice.math.desktop</Filename>
      </Exclude>
    </Menu>
  </Menu>
</Menu>
LIBREOFFICEMENUEOF

# ── ujust recipes ─────────────────────────────────────────────────────────────
# Install KythOS-specific ujust recipes so users can run e.g. "ujust rebase kyth:stable".
mkdir -p /usr/share/ublue-os/just
cp /ctx/just/kyth.just /usr/share/ublue-os/just/75-kyth.just
# The upstream justfile only imports up to 60-custom.just; wire in our file.
printf '\nimport? "/usr/share/ublue-os/just/75-kyth.just"\n' >>/usr/share/ublue-os/justfile
systemctl enable kyth-local-bin-migrate.service 2>/dev/null || true
systemctl enable kyth-topgrade-migrate.service 2>/dev/null || true
systemctl enable kyth-duperemove.timer 2>/dev/null || true
systemctl --global enable kyth-ge-proton-update.timer 2>/dev/null || true
systemctl enable kyth-flathub-setup.service 2>/dev/null || true
systemctl enable kyth-default-flatpaks.service 2>/dev/null || true
systemctl enable kyth-hw-setup.service 2>/dev/null || true
systemctl enable kyth-update-watcher.timer 2>/dev/null || true
systemctl --global enable kyth-sched.service 2>/dev/null || true
systemctl --global enable kyth-telem.service 2>/dev/null || true

# ── Steam first-run notification ─────────────────────────────────────────────
# Wrap the Steam launcher so that on the very first launch, a passive popup
# appears telling the user setup may take a few minutes.  The flag file is
# written only after the notification attempt completes so a silent failure
# doesn't permanently suppress the message on the next launch attempt.
# To reset: rm ~/.local/share/kyth-steam-initialized
cat >/usr/bin/kyth-steam <<'STEAMEOF'
#!/bin/bash
FLAG="${HOME}/.local/share/kyth-steam-initialized"
if [[ ! -f "${FLAG}" ]]; then
    mkdir -p "$(dirname "${FLAG}")"
    (
        if command -v kdialog &>/dev/null; then
            kdialog --title "KythOS" --passivepopup \
                "Steam is setting up for the first time. This may take a few minutes — please be patient." \
                30
        elif command -v notify-send &>/dev/null; then
            notify-send --urgency=normal --expire-time=30000 \
                "Steam First Start" \
                "Steam is setting up for the first time. This may take a few minutes — please be patient."
        fi
        touch "${FLAG}"
    ) &
fi
exec /usr/bin/steam "$@"
STEAMEOF
chmod +x /usr/bin/kyth-steam

# Override the Steam .desktop Exec line to use the wrapper.
# sysconfig.sh (Layer 3) already wrote a patched copy to /usr/local/share/applications/
# to strip PrefersNonDefaultGPU/X-KDE-RunOnDiscreteGpu. XDG gives /usr/local priority,
# so that copy is what KDE and launchers actually see — patch both to ensure the
# kyth-steam wrapper takes effect regardless of which path wins.
for desktop in \
	/usr/share/applications/steam.desktop \
	/usr/local/share/applications/steam.desktop; do
	if [[ -f "${desktop}" ]]; then
		sed -i 's|^Exec=/usr/bin/steam|Exec=/usr/bin/kyth-steam|g' "${desktop}"
	fi
done

# ── GE-Proton runtime update path ─────────────────────────────────────────────
# The weekly timer installs new GE-Proton to /var/lib/kyth/ge-proton/ (/var is
# writable on an immutable system). Tell Steam to check this path in addition to
# the build-time install in /usr/share/steam/compatibilitytools.d/.
# The directory must exist at first boot — Lutris (and Steam) call os.stat() on
# every path in STEAM_EXTRA_COMPAT_TOOLS_PATHS and crash with FileNotFoundError
# if any are missing, even before the update service has run for the first time.
mkdir -p /var/lib/kyth/ge-proton
chmod 1777 /var/lib/kyth/ge-proton
mkdir -p /usr/lib/tmpfiles.d
echo 'd /var/lib/kyth/ge-proton 1777 root root - -' >/usr/lib/tmpfiles.d/kyth-ge-proton.conf
echo 'STEAM_EXTRA_COMPAT_TOOLS_PATHS=/var/lib/kyth/ge-proton' >/etc/environment.d/ge-proton.conf
