# shellcheck shell=bash
# ── EXE compat checker (.exe hover) ──────────────────────────────────────
# The Rust binary is copied into /usr/bin by the Dockerfile builder stage.
# Do not reinstall the retired Python source fixture from /ctx over it.
if [[ ! -x /usr/bin/kyth-exe-compat ]]; then
	echo "kyth-exe-compat: native Rust binary missing from image builder" >&2
	exit 1
fi
# No desktop entry: double-clicks belong to kyth-exe-handler.desktop (the
# trust-once fast path + Hub dialog, registered in mimeapps.list by
# 25-installer-mime-interception.sh). A second NoDisplay entry covering a
# subset of the same MIME types only duplicates naming and hides its stdout
# verdict from the user. kyth-exe-compat stays a CLI verdict tool.
rm -f /usr/share/applications/kyth-exe-compat.desktop
