# shellcheck shell=bash
# Shared list of stock Plymouth themes that can carry Fedora branding (either
# distro artwork inside the theme, or — for bgrt — the firmware BGRT image
# from the inherited boot path) and so must be neutralized or removed.
# Sourced by repair-current-plymouth-initramfs.sh, which runs from a full
# repo checkout. plymouth-branding-guard.sh keeps its own copy of this list
# instead: it's installed standalone (/usr/libexec/kyth-plymouth-branding-guard,
# also inst_multiple'd into the initramfs) with no sibling lib/ directory, and
# two of its own copies live inside a quoted dracut heredoc where variables
# must stay literal for the initramfs — none of those can source this file.
# Keep all copies in sync by hand.
#
# shellcheck disable=SC2034  # consumed by the scripts that source this file

KYTH_STOCK_PLYMOUTH_THEMES=(bgrt-fedora bgrt spinner)
