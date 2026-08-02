#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

source "../../lib/config-helpers.sh"

# ── Homebrew shell profile ────────────────────────────────────────────────────
write_config /etc/profile.d/brew.sh <<'BREWSHEOF'
# Add Homebrew to PATH and configure environment for sh/bash/zsh if it exists
for _brew_path in "/home/linuxbrew/.linuxbrew/bin/brew" "${HOME}/.linuxbrew/bin/brew"; do
    if [ -x "${_brew_path}" ]; then
        eval "$("${_brew_path}" shellenv)"
        break
    fi
done
BREWSHEOF

write_config /etc/fish/conf.d/brew.fish <<'BREWFISHEOF'
# Add Homebrew to PATH and configure environment for fish shell if it exists
for _brew_path in "/home/linuxbrew/.linuxbrew/bin/brew" "$HOME/.linuxbrew/bin/brew"
    if test -x $_brew_path
        eval ($_brew_path shellenv)
        break
    end
end
BREWFISHEOF
