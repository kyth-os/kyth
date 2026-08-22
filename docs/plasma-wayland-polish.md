# Plasma and UI Polish Direction

This note tracks the KythOS desktop polish lane: keep the current interface
coherent first, then use Plasma and Wayland customizations to make the desktop
feel distinct, comfortable, and easy for new users to trust.

## Current Baseline

- KythOS branding is present across boot splash, os-release, SDDM background,
  Kickoff icon, wallpaper, app menu defaults, and System Hub.
- New users get KythDark, Papirus-Dark, Inter, Cascadia Code, KythOS wallpaper,
  right-side window controls, double-click open, Meta+E, Meta+Shift+S, Meta+V
  clipboard history, teal-accent Plasma focus states, and a quieter Discover
  notifier.
- Fresh users get the KythOS default layout preset: a bottom taskbar, KythOS
  launcher, pinned System Hub/App Store/Steam/Brave/Dolphin/Konsole apps,
  system tray, clock, show-desktop target, and KythOS wallpaper. The
  `kyth-comfort-v4` preset uses slightly larger panel targets, single-row task
  grouping, a curated tray, visible date, and no seconds noise.
- The curated tray keeps network, audio, Bluetooth, battery, notifications,
  clipboard, removable devices, printers, and KDE Connect discoverable.
- Screenshots have a visible home in `~/Screenshots`, are present in Dolphin
  Places, and Spectacle is pointed there during user polish.
- Login and lock screen defaults use the KythOS wallpaper and Kyth mark, keeping
  boot -> login -> desktop -> lock visually continuous without forking Breeze.
- Existing users receive versioned comfort migrations through
  `kyth-user-polish`.
- System Hub offers Everyday and Gaming role presets that adjust hub prominence,
  launcher favorites, and taskbar pins without uninstalling anything.
- Plasma Browser Integration's native connector is installed so browsers can
  tie into media keys, download progress, and desktop controls once the browser
  extension is enabled.
- Search understands familiar task names, while the visible Hub language keeps
  the primary desktop identity on KythOS. Explicit Windows wording belongs in
  migration flows, compatibility notes, and search aliases where it helps users
  find the right tool.

## Session defaults (Plasma Wayland)

- **Bare metal**, VMs, live media, and `nomodeset` all start SDDM and Plasma
  on Wayland (`plasma.desktop`). The greeter compositor is
  `kyth-sddm-compositor`. Plasma X11 is not a session.
- **Software compose:** when there is no DRM render node, on live media, or
  with `nomodeset`, KWin uses QPainter + llvmpipe. `kyth.hwgl=1` forces
  hardware GL.
- **XWayland** stays for Steam, Proton, Wine, and Electron. The NVIDIA
  userspace package (`xorg-x11-drv-nvidia*`) stays; classic Xorg and
  `plasma-workspace-x11` do not.
- **Fail-open:** if the helper cannot write `11-kyth-session.conf`, static
  `/etc/sddm.conf.d/10-kyth.conf` still provides the Wayland default so login
  is never blocked. SDDM's X11 session directory is an empty KythOS path so
  leftover X11 session files cannot appear in the greeter.
- System KWin defaults set `[Wayland] VrrPolicy=1` (Automatic) under
  `/etc/xdg/kwinrc`. Image packages explicitly include `xdg-desktop-portal`,
  `xdg-desktop-portal-kde`, and `qt6-qtwayland`.

## Consistency Rules

- Keep desktop defaults and the System Hub polish button on the same helper path.
  `kyth-user-polish --force` is the explicit "put the KythOS look back" action.
- Keep shell layout changes behind `kyth-apply-desktop-layout`; use `--initial`
  only for fresh accounts and `--force` only for explicit restore actions.
- Use `/etc/skel` for new-account defaults and versioned user polish for
  migration or repair.
- Avoid automatic visual overrides after every update unless the user has no
  existing theme state. Respect customization by default; make re-apply explicit.
- Prefer one shared visual vocabulary: KythDark shell, Kyth teal accent,
  KythOS wallpaper and icons, compact dark surfaces, high-contrast status
  colors, and comfortable interaction patterns.
- Treat System Hub as the control surface for tuning rather than scattering
  advanced toggles across undocumented scripts.
- Make KythOS feel modern by default: calm notifications, readable file paths,
  predictable double-click behavior, useful clipboard history, scannable
  Alt+Tab, a predictable screenshots folder, problem-aware Hub search, and
  role-aware pins. Avoid making the product pitch depend on another operating
  system except in migration guidance.

## Gaps To Polish Next

- Several System Hub pages still use inline `setStyleSheet(...)` colors and
  typography. Move repeated badges, section heads, keycaps, warnings, and
  status pills into shared QSS object names.
- The current Kyth plasma theme only overrides the panel background. Expand it
  carefully with a small number of distinctive, maintainable assets: panel
  separators, tray spacing, launcher affordances, task focus states, and lock
  screen details instead of forking Breeze wholesale.
- Desktop Modes cover gaming, creator, developer, laptop, ultrawide, balanced,
  and Windows comfort. Dedicated console and docked presets are still outstanding.
- Remaining Wayland readiness gates: NVIDIA/hybrid sleep-wake on live hardware,
  screen-share capture under Flatpak, and fractional-scale app quirks. Use
  `kyth-doctor` desktop-stack lines and Guardian portal/PipeWire recipes for
  recovery — not Hub-only probes.

## Plasma/Wayland Customization Path

1. Make the current shell feel finished: consistent panel, wallpaper, icons,
   window controls, Dolphin defaults, clipboard, shortcuts, app menu grouping,
   and desktop repair.
2. Iterate on the KythOS comfort layout preset: panel sizing, tray spacing,
   task manager behavior, multi-monitor behavior, launcher clarity, and restore
   diagnostics.
3. Expand opt-in role presets in System Hub:
   Console Mode and Docked Mode (creator/developer/laptop already land via
   Desktop Modes).
4. Harden Wayland readiness (OS-level):
   portal packages on the image, PipeWire capture, VRR/NightColor via
   `kyth-apply-vrr`, fractional scale via `kyth-apply-scaling`, display HDR via
   `kyth-apply-display-hdr`, Guardian portal dual-unit Plasma 6 names, and
   `desktop_stack` diagnostics for doctor/smoke. Prove software-compose greeter
   startup on nomodeset live hardware and NVIDIA/hybrid sleep-wake.

The north star: a new user should recognize the workflow, then notice that
KythOS is calmer, more recoverable, and less noisy.
