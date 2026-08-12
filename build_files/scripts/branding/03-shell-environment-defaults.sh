# shellcheck shell=bash
# ── Default shell environment for all new users ───────────────────────────────
# /etc/skel/.zshrc seeds a polished zsh experience out-of-box. Every tool
# integration is conditional so the file works identically whether the optional
# packages were installed or not.
# Also seeds /etc/skel/.bashrc with the same modern tool aliases for bash users.
write_config /etc/skel/.zshrc <<'ZSHRCEOF'
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
# Wrapper at /usr/bin/zoxide delegates to distrobox; guard execution not just
# existence so a missing binary inside the container doesn't spam crun errors
if command -v zoxide >/dev/null 2>&1; then
  if zoxide init zsh >/dev/null 2>&1; then eval "$(zoxide init zsh)"; fi
fi

# Starship prompt — must come last to override any prompt set above
if command -v starship >/dev/null 2>&1; then
  if starship init zsh >/dev/null 2>&1; then eval "$(starship init zsh)"; fi
fi

# zsh-syntax-highlighting — must be sourced after all other init (Zle hook)
[[ -f /usr/share/zsh-syntax-highlighting/zsh-syntax-highlighting.zsh ]] &&
    source /usr/share/zsh-syntax-highlighting/zsh-syntax-highlighting.zsh
ZSHRCEOF

# Also seed a .bashrc that picks up the same modern tool aliases so bash
# users benefit without switching shells.
write_config /etc/skel/.bashrc <<'BASHRCEOF'
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

# zoxide — wrapper-aware guard so missing container binary doesn't spam
if command -v zoxide >/dev/null 2>&1; then
  if zoxide init bash >/dev/null 2>&1; then eval "$(zoxide init bash)"; fi
fi

# Starship prompt — wrapper-aware guard
if command -v starship >/dev/null 2>&1; then
  if starship init bash >/dev/null 2>&1; then eval "$(starship init bash)"; fi
fi
BASHRCEOF

# System-wide git-delta pager config — makes `git diff`, `git log`, and
# `git show` output beautiful syntax-highlighted diffs with line numbers.
# delta is the pager; any user can override in their own ~/.gitconfig.
write_config /etc/gitconfig <<'GITCONFIGEOF'
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
