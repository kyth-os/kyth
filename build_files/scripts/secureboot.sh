#!/bin/bash
# secureboot.sh — sign custom-kernel vmlinuz files with the KythOS MOK key.
#
# Fail-closed for custom (CachyOS) kernels: an unsigned custom kernel does
# not boot on Secure Boot machines, so building one without a MOK key is an
# error unless the builder explicitly opts out for a test/nosb image via
# KYTH_ALLOW_UNSIGNED_KERNEL=1 (which stamps a nosb marker file so the
# resulting artifact is traceable — never ship it as a release).
# CI passes --secret id=mok_key,env=MOK_KEY.

set -euo pipefail

MOK_KEY_FILE="/run/secrets/mok_key"
SECUREBOOT_SIGNING_REQUESTED="${SECUREBOOT_SIGNING_REQUESTED:-0}"
# Explicit opt-out for local/test builds that cannot sign. When set, the
# image is stamped unsigned (see stamp_unsigned_marker) instead of failing.
KYTH_ALLOW_UNSIGNED_KERNEL="${KYTH_ALLOW_UNSIGNED_KERNEL:-0}"

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

# ── nosb marker: traceability for explicitly-unsigned test images ────────────
# Written whenever KYTH_ALLOW_UNSIGNED_KERNEL=1 lets an unsigned custom
# kernel through. Release tooling and support can check for this file to
# tell a nosb/test image apart from a properly signed one.
stamp_unsigned_marker() {
	local reason=$1
	mkdir -p /usr/share/kyth/secureboot
	cat >/usr/share/kyth/secureboot/unsigned-kernel <<EOF
status=unsigned
reason=${reason}
kernel_flavor=${KERNEL_FLAVOR}
note=Secure Boot is NOT supported on this image; enroll nothing, expect SB boot failure.
EOF
	echo "secureboot: WARNING — ${reason}; stamped /usr/share/kyth/secureboot/unsigned-kernel (nosb image, do not release)" >&2
}

fail_closed_unsigned() {
	local reason=$1
	if [[ "${KYTH_ALLOW_UNSIGNED_KERNEL}" == "1" ]]; then
		stamp_unsigned_marker "${reason}"
		exit 0
	fi
	echo "secureboot: ERROR — ${reason}" >&2
	echo "secureboot: provide the MOK key (--secret id=mok_key,env=MOK_KEY, see build.just)" >&2
	echo "secureboot: or set KYTH_ALLOW_UNSIGNED_KERNEL=1 for a local nosb/test image (never release it)" >&2
	exit 1
}

if [[ ! -f "${MOK_KEY_FILE}" ]]; then
	if [[ "${SECUREBOOT_SIGNING_REQUESTED}" == "1" ]]; then
		echo "secureboot: ERROR — SECUREBOOT_SIGNING_REQUESTED=1 but MOK_KEY secret is unavailable" >&2
		exit 1
	fi
	fail_closed_unsigned "no MOK key provided for ${KERNEL_FLAVOR} kernel — refusing to ship an unsigned image that cannot boot under Secure Boot"
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
	# A mismatched key would produce a signature nothing trusts — worse than
	# unsigned. Fail closed the same way as a missing key.
	fail_closed_unsigned "MOK_KEY secret does not match kyth-secureboot.cer in the repo (cert modulus ${CERT_MD5}); signing skipped"
fi
sbsign --key "${MOK_KEY_FILE}" \
	--cert "${CERT}" \
	--output "${VMLINUZ}.signed" \
	"${VMLINUZ}"
mv "${VMLINUZ}.signed" "${VMLINUZ}"
sbverify --cert "${CERT}" "${VMLINUZ}"
# A previous opt-out layer may have stamped nosb; a verified signature clears it.
rm -f /usr/share/kyth/secureboot/unsigned-kernel

echo "secureboot: vmlinuz signed successfully"

systemctl enable kyth-enroll-mok.service

echo "secureboot: Secure Boot support configured"
