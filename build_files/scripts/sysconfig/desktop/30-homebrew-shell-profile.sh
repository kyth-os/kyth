#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

# ── Homebrew shell profile ────────────────────────────────────────────────────
mkdir -p /etc/profile.d /etc/fish/conf.d

cat >/etc/profile.d/brew.sh <<'BREWSHEOF'
# Add Homebrew to PATH and configure environment for sh/bash/zsh if it exists
for _brew_path in "/home/linuxbrew/.linuxbrew/bin/brew" "${HOME}/.linuxbrew/bin/brew"; do
    if [ -x "${_brew_path}" ]; then
        eval "$("${_brew_path}" shellenv)"
        break
    fi
done
BREWSHEOF

cat >/etc/fish/conf.d/brew.fish <<'BREWFISHEOF'
# Add Homebrew to PATH and configure environment for fish shell if it exists
for _brew_path in "/home/linuxbrew/.linuxbrew/bin/brew" "$HOME/.linuxbrew/bin/brew"
    if test -x $_brew_path
        eval ($_brew_path shellenv)
        break
    end
end
BREWFISHEOF
