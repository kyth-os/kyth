#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

# Install baseline tooling in a single transaction to reduce solver and
# metadata overhead before the gaming repos are enabled.
dnf5 install -y --skip-unavailable \
	sddm \
	sddm-breeze \
	kwallet-pam \
	fprintd \
	fprintd-pam \
	pcsc-lite \
	opensc \
	krdc \
	bubblewrap \
	skopeo \
	plasma-workspace-x11 \
	xorg-x11-server-Xorg \
	xorg-x11-xinit \
	xorg-x11-drv-libinput \
	irqbalance \
	p7zip \
	p7zip-plugins \
	plocate \
	cabextract \
	ntfs-3g \
	ntfsprogs \
	libpst \
	rsync \
	fuse \
	fuse-libs \
	fuse3 \
	mtools \
	dosfstools \
	sbsigntools \
	util-linux-script \
	tmux \
	openssl \
	fwupd \
	hyperfine
