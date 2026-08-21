#!/usr/bin/env bash
set -euo pipefail

ROOT="$(mktemp -d)"
trap 'rm -rf "${ROOT}"' EXIT

CERT="${ROOT}/kyth-secureboot.der"
FLAG="${ROOT}/mok-enrolled"
LOG="${ROOT}/mokutil.log"
MOKUTIL="${ROOT}/mokutil"

touch "${CERT}"

cat >"${MOKUTIL}" <<'MOKEOF'
#!/usr/bin/env bash
set -euo pipefail

case "$1" in
    --sb-state)
        if [[ "${MOCK_SB_ENABLED:-0}" == "1" ]]; then
            echo "SecureBoot enabled"
        else
            echo "SecureBoot disabled"
        fi
        ;;
    --list-enrolled)
        if [[ "${MOCK_ENROLLED:-0}" == "1" ]]; then
            echo "CN=KythOS Secure Boot"
        fi
        ;;
    --list-new)
        if [[ "${MOCK_PENDING:-0}" == "1" ]]; then
            echo "CN=KythOS Secure Boot"
        fi
        ;;
    --import)
        cat >/dev/null
        if [[ "${MOCK_IMPORT_FAIL:-0}" == "1" ]]; then
            echo "import failed" >&2
            exit 1
        fi
        echo "import $2" >> "${MOCK_LOG}"
        ;;
    *)
        echo "unexpected mokutil args: $*" >&2
        exit 2
        ;;
esac
MOKEOF
chmod +x "${MOKUTIL}"

run_enroller() {
	MOCK_LOG="${LOG}" \
		MOCK_SB_ENABLED="${1}" \
		MOCK_ENROLLED="${2}" \
		MOCK_IMPORT_FAIL="${MOCK_IMPORT_FAIL:-0}" \
		KYTH_MOK_CERT_DER="${CERT}" \
		KYTH_MOK_FLAG="${FLAG}" \
		KYTH_MOKUTIL="${MOKUTIL}" \
		"$(dirname "${BASH_SOURCE[0]}")/../kyth-enroll-mok" >"${ROOT}/out" 2>"${ROOT}/err"
}

run_enroller 0 0
if [[ -f "${FLAG}" ]]; then
	echo "disabled Secure Boot path should not create enrollment marker" >&2
	exit 1
fi
if [[ -s "${LOG}" ]]; then
	echo "disabled Secure Boot path should not import automatically" >&2
	exit 1
fi

run_enroller 1 0
if [[ ! -f "${FLAG}" ]]; then
	echo "enabled Secure Boot path should create enrollment marker after staging" >&2
	exit 1
fi
if ! grep -q "import ${CERT}" "${LOG}"; then
	echo "enabled Secure Boot path should stage mokutil import" >&2
	exit 1
fi

rm -f "${FLAG}" "${LOG}"
run_enroller 1 1
if [[ ! -f "${FLAG}" ]]; then
	echo "already-enrolled path should create enrollment marker" >&2
	exit 1
fi
if [[ -s "${LOG}" ]]; then
	echo "already-enrolled path should not import again" >&2
	exit 1
fi

rm -f "${FLAG}" "${LOG}"
enroll_status=0
MOCK_IMPORT_FAIL=1 run_enroller 1 0 || enroll_status=$?
if [[ "${enroll_status}" -eq 0 ]]; then
	echo "failed mokutil import should exit non-zero" >&2
	exit 1
fi
if [[ -f "${FLAG}" ]]; then
	echo "failed mokutil import should not create enrollment marker" >&2
	exit 1
fi

echo "secureboot enrollment tests passed"
