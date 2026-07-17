#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

# ── WirePlumber audio policy ───────────────────────────────────────────────────
# Two concerns addressed here:
#   1. Bluetooth codec quality: pipewire-libs-extra ships LDAC and aptX, but
#      WirePlumber defaults to SBC when codec order is unspecified.  Listing
#      LDAC first forces codec negotiation to prefer it (990 kbps HQ mode)
#      before falling back to aptX HD → aptX → AAC → SBC XQ → SBC.
#   2. Device priority: USB audio and Bluetooth get higher session priority than
#      built-in speakers, so plugging in a headset makes it the active output
#      without a manual switch in the volume mixer.
mkdir -p /etc/wireplumber/wireplumber.conf.d
cat >/etc/wireplumber/wireplumber.conf.d/99-kyth-audio.conf <<'WPEOF'
# Automatically switch to headset Bluetooth profile (A2DP → HFP) when a call
# application opens a mic/output pair.  Without this, Bluetooth headsets stay
# in A2DP (stereo playback) and mic input fails silently in Discord/Teams.
wireplumber.settings = {
  bluetooth.autoswitch-to-headset-profile = true
}

# Bluetooth codec negotiation order — LDAC first, SBC last.
# Applies to every Bluetooth audio card that WirePlumber discovers.
monitor.bluez.rules = [
  {
    matches = [{ device.name = "~bluez_card.*" }]
    actions = {
      update-props = {
        bluez5.codecs           = [ ldac aptx_hd aptx aac sbc_xq sbc ]
        bluez5.a2dp.ldac.quality = hq
        bluez5.auto-connect     = [ a2dp_sink hfp_ag hsp_ag ]
      }
    }
  }
]

# Device session priority: Bluetooth (200) > USB audio (150) > built-in (100).
# When WirePlumber has no saved default for a session, the highest-priority
# available device wins — so plugging in a USB headset or Bluetooth headphones
# makes them the active output without opening the volume mixer.
monitor.alsa.rules = [
  {
    matches = [{ device.name = "~alsa_card.usb*" }]
    actions = { update-props = { priority.session = 150 } }
  }
  {
    matches = [{ device.name = "~alsa_card.pci*" }]
    actions = { update-props = { priority.session = 100 } }
  }
]

monitor.bluez.rules = [
  {
    matches = [{ node.name = "~bluez_output.*" }]
    actions = { update-props = { priority.session = 200 } }
  }
]
WPEOF

# obs-vkcapture is available, but do not inject it into every desktop process by
# default. Global capture hooks are convenient for streamers, but they can become
# another compatibility variable for games and GPU apps. `ujust install-obs`
# enables OBS_VKCAPTURE for the OBS Flatpak specifically.
mkdir -p /etc/environment.d
cat >/etc/environment.d/obs-vkcapture.conf <<'OBSVKCAPTUREEOF'
# OBS_VKCAPTURE intentionally left unset globally.
OBSVKCAPTUREEOF
