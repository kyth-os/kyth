# shellcheck shell=bash
# ── Fish shell default config ──────────────────────────────────────────────────
# Fish has out-of-box syntax highlighting and autosuggestions — no plugins needed.
# New users who choose fish (chsh -s /usr/bin/fish) get a polished experience.
write_config /etc/skel/.config/fish/config.fish <<'FISHCONFIGEOF'
# KythOS fish config — edit freely, it's yours.

# Starship cross-shell prompt — wrapper-aware: don't spam crun if container lacks it
if command -q starship
    if starship init fish 2>/dev/null | source; end; or true
end

# Smarter cd (zoxide) — tracks frecency, `z dir` jumps to most-used match
if command -q zoxide
    if zoxide init fish 2>/dev/null | source; end; or true
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
