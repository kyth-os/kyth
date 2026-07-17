# shellcheck shell=bash
# ── Security Tools menu group ──────────────────────────────────────────────────
# Define a custom "Security Tools" group in the XDG application menu so that
# Kali tools exported via distrobox-export land there instead of "Lost and Found".
# "Security" alone is not a recognized XDG main category, so apps without a main
# category fall through to KDE's catch-all bucket.  X-KythSecurity is our custom
# main category; the .menu merge file teaches KDE what group it belongs to.
mkdir -p /usr/share/desktop-directories
cat >/usr/share/desktop-directories/kyth-security.directory <<'SECDIREF'
[Desktop Entry]
Version=1.0
Type=Directory
Name=Security Tools
Comment=Security and penetration testing tools
Icon=security-high
SECDIREF

install -m 0644 /ctx/kyth-web-apps.directory \
	/usr/share/desktop-directories/kyth-web-apps.directory

mkdir -p /etc/xdg/menus/applications-merged
cat >/etc/xdg/menus/applications-merged/kyth-security.menu <<'SECMENUEOF'
<!DOCTYPE Menu PUBLIC "-//freedesktop//DTD Menu 1.0//EN"
  "http://www.freedesktop.org/standards/menu-spec/menu-1.0.dtd">
<Menu>
  <Name>Applications</Name>
  <!-- Explicit layout so Security Tools sorts alphabetically with standard categories.
       Merge files are processed last, so this Layout overrides the default ordering.
       <Merge type="menus"/> at the end catches any non-standard categories. -->
  <Layout>
    <Merge type="files"/>
    <Menuname>AudioVideo</Menuname>
    <Menuname>Development</Menuname>
    <Menuname>Education</Menuname>
    <Menuname>Game</Menuname>
    <Menuname>Graphics</Menuname>
    <Menuname>Internet</Menuname>
    <Menuname>Network</Menuname>
    <Menuname>Office</Menuname>
    <Menuname>Science</Menuname>
    <Menuname>Security Tools</Menuname>
    <Menuname>Settings</Menuname>
    <Menuname>System</Menuname>
    <Menuname>Utility</Menuname>
    <Menuname>Web Apps</Menuname>
    <Merge type="menus"/>
  </Layout>
  <Menu>
    <Name>Security Tools</Name>
    <Directory>kyth-security.directory</Directory>
    <Include>
      <Category>X-KythSecurity</Category>
    </Include>
  </Menu>
</Menu>
SECMENUEOF

install -m 0644 /ctx/kyth-web-apps.menu \
	/etc/xdg/menus/applications-merged/kyth-web-apps.menu
