#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

# ── Multimedia baseline ───────────────────────────────────────────────────────
# Install a full system codec stack so common local playback, browser media,
# and creator workflows work without extra setup.  RPM Fusion provides the
# patent-encumbered pieces Fedora does not ship by default.
#
# Package rationale:
#   gstreamer1-plugins-good      — Fedora "good" tier: OGG/Vorbis, FLAC, WAV,
#     AIFF, MP4/isomp4, MKV/Matroska, WebM, AVI, VP8, QuickTime. Not pulled in
#     transitively — without it KDE Elisa, Gwenview, and any GStreamer-based app
#     cannot open these common formats.
#   gstreamer1-plugins-bad-freeworld — RPM Fusion nonfree: H.264 encode (x264),
#     HEVC encode (x265), and other patent-encumbered encoders/decoders.
#   gstreamer1-plugins-ugly      — RPM Fusion free: MP3 decode (mad), MPEG-1/2
#     A/V, AC3 (Dolby Digital).
#   gstreamer1-libav             — ffmpeg-backed GStreamer plugin; handles
#     virtually every container/codec ffmpeg supports.
#   gstreamer1-vaapi             — GStreamer VA-API plugin (vaapidecode element).
#     The VA-API driver backends (iHD, radeonsi_drv_video.so) are already
#     installed; without this plugin GStreamer apps do software decode even on
#     capable hardware.
#   NOTE: pipewire-codec-aptx (RPM Fusion nonfree) was removed. PipeWire 1.6.5
#     on Fedora 44 ships pipewire-libs-extra which bundles aptX/aptX-HD and LDAC
#     natively — the RPM Fusion package conflicts with the same file path.
#
# gstreamer1-plugins-bad-freeworld conflicts with Fedora's stock
# gstreamer1-plugins-bad; remove the stock build first, then install the RPM
# Fusion replacement with --allowerasing.
dnf5 remove -y gstreamer1-plugins-bad || true
dnf5 install -y --allowerasing --skip-unavailable --exclude=gstreamer1-plugins-bad \
	ffmpeg \
	ffmpegthumbnailer \
	gstreamer1-plugins-good \
	gstreamer1-plugin-openh264 \
	gstreamer1-plugins-bad-freeworld \
	gstreamer1-plugins-ugly \
	gstreamer1-libav \
	gstreamer1-vaapi \
	mozilla-openh264
