# shellcheck shell=bash
# ── Game Tools menu group ─────────────────────────────────────────────────────
# Keep the Games root focused on playable titles. Flatpak launchers and gaming
# helpers often advertise Categories=Game, so KDE otherwise mixes them with
# exported Steam game shortcuts. Match desktop IDs explicitly so optional tools
# move into this submenu whenever the user installs them.
write_config /usr/share/desktop-directories/kyth-game-tools.directory <<'GAMETOOLSDIREF'
[Desktop Entry]
Version=1.0
Type=Directory
Name=Tools
Comment=Game launchers, compatibility helpers, and save tools
Icon=applications-utilities
GAMETOOLSDIREF

write_config /etc/xdg/menus/applications-merged/kyth-game-tools.menu <<'GAMETOOLSMENUEOF'
<!DOCTYPE Menu PUBLIC "-//freedesktop//DTD Menu 1.0//EN"
  "http://www.freedesktop.org/standards/menu-spec/menu-1.0.dtd">
<Menu>
  <Name>Applications</Name>
  <Menu>
    <Name>Games</Name>
    <Menu>
      <Name>Tools</Name>
      <Directory>kyth-game-tools.directory</Directory>
      <Include>
        <Filename>com.valvesoftware.Steam.desktop</Filename>
        <Filename>net.lutris.Lutris.desktop</Filename>
        <Filename>com.heroicgameslauncher.hgl.desktop</Filename>
        <Filename>com.usebottles.bottles.desktop</Filename>
        <Filename>com.github.Matoking.protontricks.desktop</Filename>
        <Filename>com.github.mtkennerly.ludusavi.desktop</Filename>
        <Filename>net.davidotek.pupgui2.desktop</Filename>
        <Filename>com.vysp3r.ProtonPlus.desktop</Filename>
        <Filename>org.prismlauncher.PrismLauncher.desktop</Filename>
        <Filename>io.github.benjamimgois.goverlay.desktop</Filename>
        <Filename>io.github.radiolamp.mangojuice.desktop</Filename>
      </Include>
    </Menu>
    <Exclude>
      <Filename>com.valvesoftware.Steam.desktop</Filename>
      <Filename>net.lutris.Lutris.desktop</Filename>
      <Filename>com.heroicgameslauncher.hgl.desktop</Filename>
      <Filename>com.usebottles.bottles.desktop</Filename>
      <Filename>com.github.Matoking.protontricks.desktop</Filename>
      <Filename>com.github.mtkennerly.ludusavi.desktop</Filename>
      <Filename>net.davidotek.pupgui2.desktop</Filename>
      <Filename>com.vysp3r.ProtonPlus.desktop</Filename>
      <Filename>org.prismlauncher.PrismLauncher.desktop</Filename>
      <Filename>io.github.benjamimgois.goverlay.desktop</Filename>
      <Filename>io.github.radiolamp.mangojuice.desktop</Filename>
    </Exclude>
  </Menu>
</Menu>
GAMETOOLSMENUEOF

# LibreOffice Flatpak launchers intentionally advertise multiple freedesktop
# categories. Keep the suite together under Office instead of repeating Draw in
# Graphics and Math throughout KDE's Education submenus.
write_config /etc/xdg/menus/applications-merged/kyth-libreoffice.menu <<'LIBREOFFICEMENUEOF'
<!DOCTYPE Menu PUBLIC "-//freedesktop//DTD Menu 1.0//EN"
  "http://www.freedesktop.org/standards/menu-spec/menu-1.0.dtd">
<Menu>
  <Name>Applications</Name>
  <Menu>
    <Name>Graphics</Name>
    <Exclude>
      <Filename>org.libreoffice.LibreOffice.draw.desktop</Filename>
    </Exclude>
  </Menu>
  <Menu>
    <Name>Education</Name>
    <Exclude>
      <Filename>org.libreoffice.LibreOffice.math.desktop</Filename>
    </Exclude>
    <Menu>
      <Name>Mathematics</Name>
      <Exclude>
        <Filename>org.libreoffice.LibreOffice.math.desktop</Filename>
      </Exclude>
    </Menu>
    <Menu>
      <Name>Science</Name>
      <Exclude>
        <Filename>org.libreoffice.LibreOffice.math.desktop</Filename>
      </Exclude>
    </Menu>
  </Menu>
</Menu>
LIBREOFFICEMENUEOF
