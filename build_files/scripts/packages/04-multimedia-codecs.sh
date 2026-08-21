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
#     A/V, AC3 (Dolby Digital). Prefer RPM Fusion over negativo17 multimedia.
#   gstreamer1-plugin-libav      — Fedora 44 package name (Provides:
#     gstreamer1-libav). FFmpeg-backed GStreamer plugin.
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
#
# Always --disablerepo=fedora-multimedia: ublue bases may still have negativo17
# metadata even after 03-rpmfusion hygiene, and that repo's split libav* layout
# makes gstreamer1-plugin-libav unsatisfiable (then --skip-unavailable used to
# hide the gap until the fail-closed rpm -q check).
dnf5 remove -y gstreamer1-plugins-bad || true

# Required codec stack — NO --skip-unavailable. A missing package must fail the
# image build rather than ship a desktop that cannot play common video.
dnf5 install -y --allowerasing \
	--disablerepo=fedora-multimedia \
	--exclude=gstreamer1-plugins-bad \
	ffmpeg \
	ffmpegthumbnailer \
	gstreamer1-plugins-good \
	gstreamer1-plugin-openh264 \
	gstreamer1-plugins-bad-freeworld \
	gstreamer1-plugins-ugly \
	gstreamer1-plugin-libav \
	gstreamer1-vaapi \
	mozilla-openh264

required_codec_rpms=(
	ffmpeg
	gstreamer1-plugins-good
	gstreamer1-plugins-bad-freeworld
	gstreamer1-plugin-libav
	gstreamer1-vaapi
)
missing_codec_rpms=()
for pkg in "${required_codec_rpms[@]}"; do
	if ! rpm -q "${pkg}" >/dev/null 2>&1; then
		missing_codec_rpms+=("${pkg}")
	fi
done
if ((${#missing_codec_rpms[@]})); then
	echo "ERROR: required codec packages missing after install: ${missing_codec_rpms[*]}" >&2
	echo "Enabled repos (for diagnosis):" >&2
	dnf5 repolist --enabled >&2 || true
	exit 1
fi

# Compatibility: older docs/scripts may still look for the virtual Provides name.
if ! rpm -q --whatprovides gstreamer1-libav >/dev/null 2>&1; then
	echo "ERROR: gstreamer1-plugin-libav did not Provide gstreamer1-libav" >&2
	exit 1
fi
