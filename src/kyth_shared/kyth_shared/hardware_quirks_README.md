# Hardware quirks — future split per managed quirk
#
# Roadmap: each quirk in `hardware-profiles.toml` with `expires_on` should have
# a dedicated file here (`quirks/amd_vaapi.py`, `quirks/intel_wifi.py`, etc.)
# carrying its `match` + `provenance` + `actions`. This directory is the
# staging area for that split — see `hardware_policy.py:263` `_validate_quirk_entry`
# and `hardware-policy.md#managed-quirks`.
#
# Current step (Slice 3): directory created, single `amd_vaapi` example moved
# in next commit. No behavior change — `hardware_policy.py` still reads
# `hardware-profiles.toml` as before, but new quirks should be added here first
# and then referenced from TOML via `provenance`.
