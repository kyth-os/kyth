# shellcheck shell=bash
# Shared curl retry/auth setup for scripts that fetch GitHub release assets.
# Source this, then append a locally-sized --max-time (varies by download size).
# shellcheck disable=SC2034  # consumed by the scripts that source this file

CURL_COMMON_ARGS=(--retry 5 --retry-delay 2 --retry-all-errors --connect-timeout 15)

# Authenticated GitHub API calls — avoids the 60 req/hr unauthenticated rate limit
# on shared GitHub Actions runner IP ranges. Token is injected via BuildKit secret
# and never written to any image layer. Falls back gracefully to unauthenticated
# calls when building locally without the secret.
CURL_AUTH_ARGS=()
if [[ -f /run/secrets/github_token ]]; then
	CURL_AUTH_ARGS=(-H "Authorization: token $(cat /run/secrets/github_token)")
fi
