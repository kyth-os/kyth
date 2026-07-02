---
name: run-system-hub
description: Build, run, and drive KythOS System Hub (kyth-welcome), the PySide6 desktop settings app. Use when asked to start System Hub, navigate to one of its pages, take a screenshot of its UI, or verify a visual/page change without a real display.
---

System Hub is a PySide6 desktop app (`kyth_welcome` package). It needs
a real or offscreen Qt platform to run — there's no headless test
suite for the UI, so the way to verify a change is to launch it under
`QT_QPA_PLATFORM=offscreen` and drive it via
`.claude/skills/run-system-hub/driver.py`, which bypasses the normal
`main()` entry point to navigate directly to a page and grab a
screenshot.

All paths below are relative to `build_files/kyth-welcome/` (the unit
root — this is where the `kyth_welcome/` package lives).

## Prerequisites

No system packages needed beyond Python 3 — `PySide6-Essentials`
ships its own Qt offscreen platform plugin, so no `xvfb`/X server is
required. (`PySide6-Essentials` is enough; `qt.py`'s `QtWebEngineWidgets`
import is wrapped in try/except so the full `PySide6-Addons` package
isn't needed for screenshots.)

```bash
python3 -m venv /tmp/system-hub-venv
/tmp/system-hub-venv/bin/pip install --quiet PySide6-Essentials defusedxml Pillow
```

(`defusedxml` is a hard import in `page_software.py` — without it the app
fails at import time.)

(`Pillow` is only needed if you want to pixel-sample a screenshot,
e.g. to verify an exact theme color — not required just to render.)

## Build

No build step — it's a plain Python package, no compilation/bundling.

## Run (agent path)

```bash
cd build_files/kyth-welcome

# discover valid --page / shoot keys
/tmp/system-hub-venv/bin/python .claude/skills/run-system-hub/driver.py list-pages

# navigate to a page and save a screenshot
/tmp/system-hub-venv/bin/python .claude/skills/run-system-hub/driver.py shoot Welcome /tmp/home.png
/tmp/system-hub-venv/bin/python .claude/skills/run-system-hub/driver.py shoot Hardware /tmp/hardware.png
```

The Home page's key is `Welcome`, not `Home` — `list-pages` is the
source of truth, but as of this writing the full key list is:

```
App Store, Channels, Cloud Storage, Compatibility, Controllers,
Diagnostics, Feedback, Gaming, Hardware, Kernel, Move Files,
Network Shares, Performance, Plasma Wayland, Repair, Update, VPN,
Welcome, Work Setup
```

`shoot` polls the page's `_worker` (e.g. `HardwareProbeWorker` on the
Hardware page, which runs `lspci`/`lsusb`/`lsmod`/etc. on a background
`QThread`) and waits for it to finish before grabbing the screenshot,
so the PNG shows final results, not a "Running hardware probes..."
loading state. Static pages with no `_worker` return almost
immediately. Default timeout is 25s (`--timeout` to change it).

Then view the PNG with the Read tool (or any image viewer) to actually
look at it — don't just check that the file was written.

### Interact (click buttons, inspect state)

`run-script` executes a Python snippet against a live `MainWindow` with
`win`, `app`, `navigate(key)`, `pump(seconds)`, and `shoot(path)` in
scope. Example that selects the "Gaming Rig" vibe on the dashboard and
verifies the toggle took effect (ran and verified):

```bash
cat > /tmp/vibe.py <<'EOF'
from kyth_welcome.qt import QPushButton

navigate("Welcome")
pump(0.5)
page = getattr(win, "_stack").currentWidget()
gaming = [b for b in page.findChildren(QPushButton) if "Gaming Rig" in b.text()][0]
gaming.click()
pump(0.5)
assert gaming.isChecked()
shoot("/tmp/vibe-gaming.png")
EOF
/tmp/system-hub-venv/bin/python .claude/skills/run-system-hub/driver.py run-script /tmp/vibe.py
```

Don't click **Apply Vibe Settings** (or other buttons that run
`pkexec`/`systemctl`/`rpm-ostree` actions) when driving the app on a
real KythOS host — the pages shell out to the live system. Selecting
toggles and navigating is safe; applying is not.

## Test

The repo's unit tests cover `kyth_welcome` helpers and run with plain
system Python (no PySide6 needed), from the **repo root**:

```bash
python3 -m unittest discover -s tests
```

## Run (human path)

```bash
build_files/kyth-welcome/kyth-welcome          # real window, needs a display
build_files/kyth-welcome/kyth-welcome --page Hardware   # jump straight to a page
```

`kyth-welcome` (no `-launch` suffix) is the dev entry point — it adds
itself to `sys.path` so a source checkout takes precedence over
`/usr/lib/kyth-welcome` on an installed system. Useless headless;
needs a real or Xwayland display. Ctrl-C or close the window to stop.

---

## Gotchas

- **Don't call `kyth_welcome.app.main()` for screenshots.** It acquires
  a single-instance PID lock at `~/.cache/kyth/kyth-welcome.lock` and
  refuses to launch a second instance (silent `sys.exit(0)`). The
  driver imports `kyth_welcome.windows.MainWindow` directly and never
  touches that lock, so it can run alongside a real session.
- **Async probes need a poll loop, not a fixed sleep.** The Hardware
  page's `HardwareProbeWorker` runs in a background `QThread`; grabbing
  a screenshot after only 1-2 `app.processEvents()` calls captures the
  page mid-load (progress bar + "Running hardware probes...") and
  prints `QThread: Destroyed while thread '' is still running` on
  exit. The driver polls `getattr(page, "_worker", None).isRunning()`
  instead.
- **The Home page's nav key is `"Welcome"`,** not `"Home"` — it's the
  page title shown in the UI, but the internal key matches the
  original wizard/welcome-screen naming. Always check `list-pages` if
  unsure rather than guessing from the sidebar label.
- **No `xvfb` needed.** `PySide6-Essentials` bundles its own offscreen
  Qt platform plugin (`QT_QPA_PLATFORM=offscreen`); installing/running
  a virtual X server is unnecessary overhead for this app.
- **Button texts carry emoji prefixes** (`"🎮 Gaming Rig"`, not
  `"Gaming Rig"`), and the offscreen render may not draw the glyph even
  though it's in `.text()`. Match with `in`, never `==`. The dashboard's
  vibe buttons are plain `QPushButton`s but only exist on the Welcome
  page widget — search `getattr(win, "_stack").currentWidget()`, not
  the whole window, and note `MainWindow`'s attributes are private
  (`_stack`, `_navigate_to`; pages keep state like `_preset_status`).
- **Clicking a vibe reshapes the whole UI** (sidebar sections and task
  cards change per profile) — a screenshot after the click is the way
  to see the full effect, not just the button's checked state.

## Troubleshooting

- **`ModuleNotFoundError: No module named 'PySide6'`**: you're running
  with system `python3` instead of the venv's. Use
  `/tmp/system-hub-venv/bin/python`, not `python3`.
- **Screenshot shows "Running hardware probes..." with an active
  progress bar**: the script exited before the worker thread finished.
  Use `driver.py shoot` (it polls) rather than a one-shot
  `grab()`/`save()` script with only a couple of `processEvents()` calls.
