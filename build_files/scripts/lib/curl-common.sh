# shellcheck shell=bash
# Shared curl retry/auth setup for scripts that fetch GitHub release assets.
# Source this, then append a locally-sized --max-time (varies by download size).
# shellcheck disable=SC2034  # consumed by the scripts that source this file

CURL_COMMON_ARGS=(--fail --retry 5 --retry-delay 2 --retry-all-errors --connect-timeout 15)

# Authenticated GitHub API calls — avoids the 60 req/hr unauthenticated rate limit
# on shared GitHub Actions runner IP ranges. Token is injected via BuildKit secret
# and never written to any image layer. Falls back gracefully to unauthenticated
# calls when building locally without the secret.
#
# Create the config pipe for each invocation: source-time substitutions close
# before curl runs, and retaining a pipe would only authenticate the first call.
# The token goes through curl -K, never through argv or a generated config file.
github_api_curl() {
	if [[ -f /run/secrets/github_token ]]; then
		command curl -K <(printf 'header = "Authorization: token %s"\n' "$(</run/secrets/github_token)") "$@"
	else
		command curl "$@"
	fi
}
