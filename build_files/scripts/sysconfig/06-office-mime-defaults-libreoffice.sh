#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

# ── Office MIME defaults → LibreOffice ───────────────────────────────────────
# Without explicit system defaults, KDE's file manager and browser downloads
# open .docx/.xlsx/.pptx files with "Open With…" dialogs or pick the wrong app.
# Map all Microsoft Office and ODF types to the corresponding LibreOffice
# Flatpak sub-app so the right component opens directly (Writer, not the
# LibreOffice Start Center for a .docx).
cat >/etc/xdg/mimeapps.list <<'MIMEAPPSEOF'
[Default Applications]
application/msword=org.libreoffice.LibreOffice.writer.desktop
application/vnd.openxmlformats-officedocument.wordprocessingml.document=org.libreoffice.LibreOffice.writer.desktop
application/vnd.ms-word.document.macroenabled.12=org.libreoffice.LibreOffice.writer.desktop
application/vnd.ms-excel=org.libreoffice.LibreOffice.calc.desktop
application/vnd.openxmlformats-officedocument.spreadsheetml.sheet=org.libreoffice.LibreOffice.calc.desktop
application/vnd.ms-excel.sheet.macroenabled.12=org.libreoffice.LibreOffice.calc.desktop
application/vnd.ms-powerpoint=org.libreoffice.LibreOffice.impress.desktop
application/vnd.openxmlformats-officedocument.presentationml.presentation=org.libreoffice.LibreOffice.impress.desktop
application/vnd.ms-powerpoint.presentation.macroenabled.12=org.libreoffice.LibreOffice.impress.desktop
application/vnd.oasis.opendocument.text=org.libreoffice.LibreOffice.writer.desktop
application/vnd.oasis.opendocument.spreadsheet=org.libreoffice.LibreOffice.calc.desktop
application/vnd.oasis.opendocument.presentation=org.libreoffice.LibreOffice.impress.desktop
application/vnd.oasis.opendocument.graphics=org.libreoffice.LibreOffice.draw.desktop
application/rtf=org.libreoffice.LibreOffice.writer.desktop
text/rtf=org.libreoffice.LibreOffice.writer.desktop
text/csv=org.libreoffice.LibreOffice.calc.desktop
MIMEAPPSEOF

