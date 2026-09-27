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
#   gstreamer1-plugins-bad-free  — Fedora "bad" free set. On Fedora 44 /
#     GStreamer 1.28 this ships libgstva.so (modern VA-API plugin) and
#     Provides: gstreamer1-vaapi so the obsolete standalone gstreamer1-vaapi
#     1.26 RPM is not needed (and must not be required via rpm -q by NEVRA).
#   gstreamer1-plugins-bad-freeworld — RPM Fusion nonfree: H.264 encode (x264),
#     HEVC encode (x265), and other patent-encumbered encoders/decoders.
#   gstreamer1-plugins-ugly      — RPM Fusion free: MP3 decode (mad), MPEG-1/2
#     A/V, AC3 (Dolby Digital). Prefer RPM Fusion over negativo17 multimedia.
#   gstreamer1-plugin-libav      — Fedora 44 package name (Provides:
#     gstreamer1-libav). FFmpeg-backed GStreamer plugin.
#   NOTE: pipewire-codec-aptx (RPM Fusion nonfree) was removed. PipeWire 1.6.5
#     on Fedora 44 ships pipewire-libs-extra which bundles aptX/aptX-HD and LDAC
#     natively — the RPM Fusion package conflicts with the same file path.
#
# gstreamer1-plugins-bad-freeworld conflicts with Fedora's stock
# gstreamer1-plugins-bad; remove the stock build first, then install the RPM
# Fusion replacement with --allowerasing. Keep gstreamer1-plugins-bad-free
# (distinct package) — that is where VA-API lives on F44+.
#
# Always prefer RPM Fusion over negativo17 multimedia. 03-rpmfusion removes
# leftover *multimedia* / *negativo* repo files so gstreamer1-plugin-libav can
# resolve against a consistent ffmpeg/libav stack (the old --skip-unavailable
# path used to hide an unsatisfiable solve).
dnf5 remove -y gstreamer1-plugins-bad || true

# Required codec stack — NO --skip-unavailable. A missing package must fail the
# image build rather than ship a desktop that cannot play common video.
# fedora-multimedia is removed in 03-rpmfusion; do not --disablerepo it here
# (dnf5 exits 2 when that repo id no longer exists).
#
# Do not install the obsolete gstreamer1-vaapi NEVRA: dnf5 treats the request as
# already satisfied by gstreamer1-plugins-bad-free's Provides, then rpm -q
# gstreamer1-vaapi fails the fail-closed check even though libgstva.so is present.
dnf5 install -y --allowerasing \
	--exclude=gstreamer1-plugins-bad \
	ffmpeg \
	ffmpegthumbnailer \
	gstreamer1-plugins-good \
	gstreamer1-plugins-bad-free \
	gstreamer1-plugin-openh264 \
	gstreamer1-plugins-bad-freeworld \
	gstreamer1-plugins-ugly \
	gstreamer1-plugin-libav \
	mozilla-openh264

required_codec_rpms=(
	ffmpeg
	gstreamer1-plugins-good
	gstreamer1-plugins-bad-free
	gstreamer1-plugins-bad-freeworld
	gstreamer1-plugin-libav
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

# VA-API capability: Prefer the Provide (satisfied by bad-free on F44+) over the
# obsolete standalone RPM name. Also require the modern plugin .so on disk.
if ! rpm -q --whatprovides gstreamer1-vaapi >/dev/null 2>&1; then
	echo "ERROR: nothing Provides gstreamer1-vaapi (expected gstreamer1-plugins-bad-free)" >&2
	exit 1
fi
if [[ ! -e /usr/lib64/gstreamer-1.0/libgstva.so && ! -e /usr/lib/gstreamer-1.0/libgstva.so ]]; then
	echo "ERROR: libgstva.so missing after codec install (VA-API GStreamer plugin)" >&2
	exit 1
fi

# Compatibility: older docs/scripts may still look for the virtual Provides name.
if ! rpm -q --whatprovides gstreamer1-libav >/dev/null 2>&1; then
	echo "ERROR: gstreamer1-plugin-libav did not Provide gstreamer1-libav" >&2
	exit 1
fi
