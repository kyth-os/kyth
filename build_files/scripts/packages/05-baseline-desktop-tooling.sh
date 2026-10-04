#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

# Install baseline tooling in a single transaction to reduce solver and
# metadata overhead before the gaming repos are enabled.
# pam-kwallet is required (not --skip-unavailable): script 26 wires its PAM
# module into the login stack, and a silently-missing package would break
# wallet unlock while the build looks green.
dnf5 install -y \
	plasma-login-manager \
	pam-kwallet
dnf5 install -y --skip-unavailable \
	kcm-plasmalogin \
	fprintd \
	fprintd-pam \
	pcsc-lite \
	opensc \
	krdc \
	bubblewrap \
	irqbalance \
	plocate \
	ntfs-3g \
	os-prober \
	rsync \
	fuse \
	fuse-libs \
	fuse3 \
	mtools \
	dosfstools \
	sbsigntools \
	util-linux-script \
	openssl \
	fwupd

# Small CPU-only runtime for the optional, user-downloaded Guardian model.
# Keep image construction portable if the package is temporarily unavailable.
dnf5 install -y --skip-unavailable llama-cpp
