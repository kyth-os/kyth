"""Single validation contract for installer — Python + JS shared.

Backend `validation.py` and frontend `webui/app.js` must use identical
hostname/username/keymap/locale regexes. This module is the source of
truth; `validation_rules.json` is generated from it for the web UI build.
"""

from __future__ import annotations

import re

USERNAME_PATTERN = re.compile(r"[a-z_][a-z0-9_-]{0,30}")
HOSTNAME_PATTERN = re.compile(r"[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?")
LOCALE_PATTERN = re.compile(r"[A-Za-z0-9_.@-]{1,64}")
KEYMAP_PATTERN = re.compile(r"[A-Za-z0-9_.+@/-]{1,64}")

# Plain strings for JSON/JS generation (without re.compile wrapper)
USERNAME_REGEX = r"[a-z_][a-z0-9_-]{0,30}"
HOSTNAME_REGEX = r"[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?"
LOCALE_REGEX = r"[A-Za-z0-9_.@-]{1,64}"
KEYMAP_REGEX = r"[A-Za-z0-9_.+@/-]{1,64}"
