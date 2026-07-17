# Show the current KythOS Secure Boot enrollment state.
#
# This is safe to run any time. It does not change firmware settings.
[group('KythOS')]
secureboot-status:
    #!/usr/bin/env bash
    set -euo pipefail

    CERT_PEM="/usr/share/kyth/secureboot/kyth-secureboot.cer"
    CERT_DER="/usr/share/kyth/secureboot/kyth-secureboot.der"
    FLAG="/var/lib/kyth/mok-enrolled"

    echo "━━━ KythOS Secure Boot Status ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo

    if [[ -f "${CERT_DER}" ]]; then
        echo "  Certificate: present at ${CERT_DER}"
    elif [[ -f "${CERT_PEM}" ]]; then
        echo "  Certificate: present as PEM at ${CERT_PEM}"
    else
        echo "  Certificate: missing — this image was built without Secure Boot support"
    fi

    if mokutil --sb-state 2>/dev/null; then
        :
    else
        echo "  Firmware state: unavailable — boot this system in UEFI mode to use MOK enrollment"
    fi

    if mokutil --list-enrolled 2>/dev/null | grep -q "KythOS Secure Boot"; then
        echo "  KythOS MOK: enrolled"
    else
        echo "  KythOS MOK: not enrolled"
    fi

    if mokutil --list-new 2>/dev/null | grep -q "KythOS Secure Boot"; then
        echo "  Pending enrollment: staged for next reboot"
    else
        echo "  Pending enrollment: none detected"
    fi

    if [[ -f "${FLAG}" ]]; then
        echo "  First-boot service marker: ${FLAG}"
    else
        echo "  First-boot service marker: not set"
    fi

# Manually enroll the KythOS Secure Boot key (MOK) into UEFI firmware.
#
# The default Fedora kernel path does not need this key. Run this before
# enabling Secure Boot for the advanced CachyOS kernel image, or after a
# firmware reset if the KythOS MOK was removed.
#
# After running, reboot and enter the password you chose at the MokManager screen.
[group('KythOS')]
enroll-secureboot:
    #!/usr/bin/env bash
    set -euo pipefail

    CERT_PEM="/usr/share/kyth/secureboot/kyth-secureboot.cer"
    CERT_DER="/usr/share/kyth/secureboot/kyth-secureboot.der"

    if [[ ! -f "${CERT_PEM}" && ! -f "${CERT_DER}" ]]; then
        echo "KythOS Secure Boot certificate not found." >&2
        echo "This image was built without Secure Boot support." >&2
        exit 1
    fi

    if [[ ! -f "${CERT_DER}" ]]; then
        CERT_DER="$(mktemp --tmpdir kyth-secureboot.XXXXXX.der)"
        openssl x509 -in "${CERT_PEM}" -outform DER -out "${CERT_DER}"
    fi

    echo "━━━ KythOS Secure Boot Enrollment ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo

    SB_STATE="$(mokutil --sb-state 2>/dev/null || true)"
    if echo "${SB_STATE}" | grep -q "SecureBoot enabled"; then
        echo "  Secure Boot is currently enabled."
    else
        echo "  Secure Boot is currently disabled or unavailable."
        echo "  That is OK — for existing installs, staging the key before enabling"
        echo "  Secure Boot is the safest path."
    fi
    echo

    if mokutil --list-enrolled 2>/dev/null | grep -q "KythOS Secure Boot"; then
        echo "  KythOS Secure Boot key is already enrolled. Nothing to do."
        exit 0
    fi

    if mokutil --list-new 2>/dev/null | grep -q "KythOS Secure Boot"; then
        echo "  KythOS Secure Boot key is already staged for enrollment."
        echo "  Reboot, complete the blue MokManager prompt, then enable Secure Boot"
        echo "  in firmware if it is not enabled already."
        exit 0
    fi

    echo "  Enrolling KythOS Secure Boot certificate."
    echo "  Choose a one-time confirmation password — you will enter it at the"
    echo "  MokManager screen on next reboot to complete enrollment."
    echo
    read -rsp "  Enrollment password: " MOK_PASS
    echo
    read -rsp "  Confirm password:    " MOK_PASS2
    echo
    if [[ "${MOK_PASS}" != "${MOK_PASS2}" ]]; then
        echo "  Passwords do not match." >&2
        exit 1
    fi

    echo "${MOK_PASS}" | sudo mokutil --import "${CERT_DER}" --stdin-passwd

    echo
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  MOK enrollment staged."
    echo "  Next steps:"
    echo "    1. Reboot."
    echo "    2. At the blue MokManager screen, choose Enroll MOK / Continue / Yes."
    echo "    3. Enter the password you just chose, then reboot."
    echo "    4. Enable Secure Boot in UEFI/BIOS if it is not enabled already."
    echo "    5. Boot KythOS and run: ujust secureboot-status"
