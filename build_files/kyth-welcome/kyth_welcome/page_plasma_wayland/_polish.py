# __KYTH_GENERATED_IMPORTS__
from ..services.process import run_command


class _PolishMixin:
    @staticmethod
    def _plasma_polish_command() -> list[str]:
        script = r"""
set -euo pipefail
if [ -x /usr/bin/kyth-user-polish ]; then
  /usr/bin/kyth-user-polish --force
  exit 0
fi
command -v kwriteconfig6 >/dev/null
mkdir -p "${HOME}/Screenshots"

kwriteconfig6 --file kdeglobals --group General --key ColorScheme KythDark
kwriteconfig6 --file kdeglobals --group General --key font 'Inter,10,-1,5,400,0,0,0,0,0,Regular'
kwriteconfig6 --file kdeglobals --group General --key fixed 'Cascadia Code,10,-1,5,400,0,0,0,0,0,Regular'
kwriteconfig6 --file kdeglobals --group General --key smallestReadableFont 'Inter,8,-1,5,400,0,0,0,0,0,Regular'
kwriteconfig6 --file kdeglobals --group General --key toolBarFont 'Inter,9,-1,5,400,0,0,0,0,0,Regular'
kwriteconfig6 --file kdeglobals --group General --key menuFont 'Inter,10,-1,5,400,0,0,0,0,0,Regular'
kwriteconfig6 --file kdeglobals --group Icons --key Theme Papirus-Dark
kwriteconfig6 --file kdeglobals --group KDE --key LookAndFeelPackage org.kde.breezedark.desktop
kwriteconfig6 --file kdeglobals --group KDE --key SingleClick --type bool false
kwriteconfig6 --file plasmarc --group Theme --key name kyth-dark
kwriteconfig6 --file kickoffrc --group Favorites --key FavoriteURLs 'applications:kyth-welcome.desktop,applications:kyth-app-store.desktop,applications:com.valvesoftware.Steam.desktop,applications:com.brave.Browser.desktop,applications:chromium-browser.desktop,applications:org.kde.konsole.desktop'
kwriteconfig6 --file kickoffrc --group General --key highlightNewlyInstalledApps --type bool false

kwriteconfig6 --file klipperrc --group General --key KeepClipboardContents --type bool true
kwriteconfig6 --file klipperrc --group General --key MaxClipItems 25
kwriteconfig6 --file kglobalshortcutsrc --group org.kde.klipper.desktop --key show_clipboard_history 'Meta+V,Ctrl+Alt+V,Show Clipboard History'
kwriteconfig6 --file kglobalshortcutsrc --group services --group org.kde.dolphin.desktop --key _launch 'Meta+E'
kwriteconfig6 --file kglobalshortcutsrc --group org.kde.spectacle.desktop --key RectangularRegionScreenShot 'Meta+Shift+S,Meta+Shift+S,Capture Rectangular Region'
kwriteconfig6 --file spectaclerc --group General --key defaultSaveLocation "file://${HOME}/Screenshots"
kwriteconfig6 --file spectaclerc --group General --key lastSaveAsLocation "file://${HOME}/Screenshots"
kwriteconfig6 --file spectaclerc --group General --key useReleaseToCapture --type bool true
kwriteconfig6 --file spectaclerc --group ImageSave --key translatedScreenshotsFolder "${HOME}/Screenshots"

kwriteconfig6 --file kwinrc --group TabBox --key LayoutName thumbnail_grid
kwriteconfig6 --file kwinrc --group TabBox --key ShowDesktop --type bool false
kwriteconfig6 --file kwinrc --group TabBoxAlternative --key LayoutName thumbnail_grid
kwriteconfig6 --file kwinrc --group org.kde.kdecoration2 --key ButtonsOnLeft ''
kwriteconfig6 --file kwinrc --group org.kde.kdecoration2 --key ButtonsOnRight IAX
kwriteconfig6 --file kwinrc --group org.kde.kdecoration2 --key library org.kde.breeze
kwriteconfig6 --file kwinrc --group org.kde.kdecoration2 --key theme Breeze
kwriteconfig6 --file kwinrc --group Plugins --key desktopchangeosdEnabled --type bool false
kwriteconfig6 --file kwinrc --group Compositing --key LatencyPolicy extreme
kwriteconfig6 --file kwinrc --group Compositing --key AllowTearing --type bool false

kwriteconfig6 --file plasma-discoverrc --group UpdatesNotifier --key UseNotifications --type bool false
kwriteconfig6 --file dolphinrc --group General --key RememberOpenedTabs --type bool true
kwriteconfig6 --file dolphinrc --group General --key ShowFullPath --type bool true
kwriteconfig6 --file dolphinrc --group General --key UseTabForSplitViewSwitch --type bool true
kwriteconfig6 --file dolphinrc --group General --key ShowSpaceInfo --type bool true
kwriteconfig6 --file dolphinrc --group DetailsMode --key PreviewSize 32
kwriteconfig6 --file kscreenlockerrc --group Daemon --key Autolock --type bool true
kwriteconfig6 --file kscreenlockerrc --group Daemon --key LockGracePeriod 5
kwriteconfig6 --file kscreenlockerrc --group Daemon --key LockOnResume --type bool true
kwriteconfig6 --file kscreenlockerrc --group Daemon --key Timeout 15
kwriteconfig6 --file kscreenlockerrc --group Greeter --group Wallpaper --group org.kde.image --group General --key Image /usr/share/wallpapers/kyth/contents/images/1920x1080.svg

if [ -r /usr/share/wallpapers/kyth/contents/images/1920x1080.svg ]; then
  kwriteconfig6 --file plasma-org.kde.plasma.desktop-appletsrc \
    --group Containments --group 1 --group Wallpaper --group org.kde.image --group General \
    --key Image /usr/share/wallpapers/kyth/contents/images/1920x1080.svg
fi

qdbus_cmd=""
for candidate in qdbus6 qdbus-qt6 qdbus; do
  if command -v "${candidate}" >/dev/null 2>&1; then
    qdbus_cmd="${candidate}"
    break
  fi
done
if [ -n "${qdbus_cmd}" ]; then
  "${qdbus_cmd}" org.kde.KWin /KWin reconfigure >/dev/null 2>&1 || true
fi
"""
        return ["bash", "-lc", script]

    def _apply_plasma_polish(self):
        cmd = self._plasma_polish_command()
        self._polish_result.set_running("Restoring the KythOS default layout...", self._command_details(cmd))
        result = run_command(cmd, timeout=20)
        if result is None:
            self._polish_result.set_result("err", "Could not apply KythOS polish: command failed to start", self._command_details(cmd))
            return
        if result.returncode == 0:
            self._polish_result.set_result(
                "ok",
                "KythOS default layout restored. Some panel, shell theme, or wallpaper changes may appear after restarting Plasma Shell or signing in again.",
                self._command_details(cmd, result),
            )
            self.refresh()
        else:
            detail = result.stderr.strip() or result.stdout.strip() or "unknown error"
            self._polish_result.set_result("err", f"Could not apply KythOS polish: {detail}", self._command_details(cmd, result))
