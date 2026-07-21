#!/bin/bash
# secureboot.sh — sign custom-kernel vmlinuz files with the KythOS MOK key.
#
# Skipped gracefully when no MOK key is provided (local builds without
# a secret configured). CI passes --secret id=mok_key,env=MOK_KEY.

set -euo pipefail

MOK_KEY_FILE="/run/secrets/mok_key"
SECUREBOOT_SIGNING_REQUESTED="${SECUREBOOT_SIGNING_REQUESTED:-0}"

CERT="/ctx/secureboot/kyth-secureboot.cer"
KERNEL_FLAVOR="$(cat /usr/share/kyth/kernel-flavor 2>/dev/null || echo fedora)"

# ── Install runtime enrollment artifacts in every image ─────────────────────
# Fedora is trusted by Fedora shim without Kyth signing, but users may switch to
# a custom kernel image later and need the public cert available beforehand.
# openssl and sbsigntools are installed in the stable package layer so this
# daily layer does not need to refresh DNF metadata.
command -v openssl >/dev/null
install -Dm 0644 "${CERT}" /usr/share/kyth/secureboot/kyth-secureboot.cer
openssl x509 -in "${CERT}" -outform DER -out /tmp/kyth-secureboot.der
install -Dm 0644 /tmp/kyth-secureboot.der /usr/share/kyth/secureboot/kyth-secureboot.der
install -Dm 0755 /ctx/kyth-enroll-mok /usr/bin/kyth-enroll-mok
install -Dm 0644 /ctx/kyth-enroll-mok.service /usr/lib/systemd/system/kyth-enroll-mok.service

if [[ "${KERNEL_FLAVOR}" == "fedora" ]]; then
	echo "secureboot: Fedora kernel flavor uses Fedora-signed boot artifacts — Kyth MOK signing skipped"
	exit 0
fi

if [[ ! -f "${MOK_KEY_FILE}" ]]; then
	if [[ "${SECUREBOOT_SIGNING_REQUESTED}" == "1" ]]; then
		echo "secureboot: ERROR — SECUREBOOT_SIGNING_REQUESTED=1 but MOK_KEY secret is unavailable" >&2
		exit 1
	fi
	echo "secureboot: no MOK key provided — Secure Boot signing skipped"
	echo "secureboot: set MOK_KEY env var and pass --secret id=mok_key,env=MOK_KEY to enable"
	exit 0
fi

# ── Find the installed custom kernel ─────────────────────────────────────────
KVER=$(find /usr/lib/modules -mindepth 1 -maxdepth 1 -type d -printf '%f\n' 2>/dev/null | sort -V | tail -n 1)
if [[ -z "${KVER}" ]]; then
	echo "secureboot: ERROR — no kernel found in /usr/lib/modules/" >&2
	exit 1
fi

VMLINUZ="/usr/lib/modules/${KVER}/vmlinuz"
if [[ ! -f "${VMLINUZ}" ]]; then
	echo "secureboot: ERROR — vmlinuz not found at ${VMLINUZ}" >&2
	exit 1
fi

# ── Sign the custom kernel ───────────────────────────────────────────────────
command -v sbsign >/dev/null
echo "secureboot: signing ${VMLINUZ} (kernel ${KVER})"
# Check each openssl modulus read on its own exit status rather than piping
# straight into `openssl md5 | awk`: under pipefail, a trailing `|| echo
# UNREADABLE` only fires if the LAST command in the pipe fails, but md5/awk
# happily hash empty input and "succeed" even when the modulus read itself
# failed — masking the real cause with a misleading (if harmless) hash value.
if KEY_MODULUS=$(openssl rsa -in "${MOK_KEY_FILE}" -noout -modulus 2>/dev/null); then
	KEY_MD5=$(openssl md5 <<<"${KEY_MODULUS}" | awk '{print $2}')
else
	KEY_MD5="UNREADABLE"
fi
if CERT_MODULUS=$(openssl x509 -in "${CERT}" -noout -modulus 2>/dev/null); then
	CERT_MD5=$(openssl md5 <<<"${CERT_MODULUS}" | awk '{print $2}')
else
	CERT_MD5="UNREADABLE"
fi
echo "secureboot: key modulus md5=${KEY_MD5}"
echo "secureboot: cert modulus md5=${CERT_MD5}"
if [[ "${KEY_MD5}" != "${CERT_MD5}" ]]; then
	if [[ "${SECUREBOOT_SIGNING_REQUESTED}" == "1" ]]; then
		echo "secureboot: ERROR — MOK_KEY secret does not match kyth-secureboot.cer in the repo." >&2
		echo "secureboot: Update the MOK_KEY GitHub secret with the private key matching cert modulus ${CERT_MD5}." >&2
		exit 1
	fi
	echo "secureboot: WARNING — MOK_KEY secret does not match kyth-secureboot.cer in the repo; signing skipped." >&2
	echo "secureboot: Update the MOK_KEY GitHub secret with the private key matching cert modulus ${CERT_MD5} to re-enable signing." >&2
	exit 0
fi
sbsign --key "${MOK_KEY_FILE}" \
	--cert "${CERT}" \
	--output "${VMLINUZ}.signed" \
	"${VMLINUZ}"
mv "${VMLINUZ}.signed" "${VMLINUZ}"
sbverify --cert "${CERT}" "${VMLINUZ}"

echo "secureboot: vmlinuz signed successfully"

systemctl enable kyth-enroll-mok.service

echo "secureboot: Secure Boot support configured"
