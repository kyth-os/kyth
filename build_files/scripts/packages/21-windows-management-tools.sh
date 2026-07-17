#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

# ── Windows environment management tools ─────────────────────────────────────
# Tools for users who manage Windows hosts, Azure, or Active Directory from
# KythOS. Reuses the already-vendored Microsoft signing key written to
# /etc/pki/rpm-gpg/RPM-GPG-KEY-microsoft by packages/19-vscode.sh.

# Azure CLI — same Microsoft key, different repo.
cat >/etc/yum.repos.d/azure-cli.repo <<'AZUREREPOEOF'
[azure-cli]
name=Azure CLI
baseurl=https://packages.microsoft.com/yumrepos/azure-cli
enabled=1
gpgcheck=1
gpgkey=file:///etc/pki/rpm-gpg/RPM-GPG-KEY-microsoft
AZUREREPOEOF

dnf5 install -y azure-cli
rpm -q azure-cli

# Disable update checks — same reason as VS Code: immutable image.
dnf5 config-manager setopt azure-cli.enabled=0

# RDP, Active Directory, Kerberos, and SMB tooling — all in standard Fedora repos.
# freerdp: best-in-class RDP client; powers Remmina's RDP backend.
# realmd/sssd/adcli: domain join, AD auth, and LDAP/Kerberos enrollment.
# krb5-workstation: kinit, klist, kdestroy — Kerberos ticket management.
# samba-client: smbclient + net ads + wbinfo for SMB share browsing and AD queries.
#   (cifs-utils for mounting is already installed in the baseline block above.)
dnf5 install -y --skip-unavailable \
	freerdp \
	realmd \
	sssd \
	sssd-ad \
	sssd-tools \
	adcli \
	krb5-workstation \
	samba-client \
	openldap-clients
