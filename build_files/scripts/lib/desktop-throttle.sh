# shellcheck shell=bash
#
# Deprioritize a heavy local job (linters, the full test suite, coverage)
# so it can't starve kwin_wayland/Plasma of CPU, IO, or memory on a live
# desktop and force a session crash. CPUWeight/IOWeight only bite under
# actual contention — idle, the job still runs at full speed. MemoryHigh/
# MemoryMax cap this job's own cgroup so a spike (the ~180-file test
# suite's Hub-smoke construction/teardown is already flagged as OOM-prone
# — see test_kyth_welcome_hub_smoke.py's own "skip under coverage" guard)
# gets reclaimed or OOM-killed inside its own scope instead of taking down
# sibling cgroups like the desktop session's.
#
# Was three near-identical copies of this (validate.sh, run-quality.sh,
# .githooks/pre-push) that had already drifted: two carried a stale
# `[[ -z "${INVOCATION_ID:-}" ]]` condition that skipped the whole throttle
# whenever the invoking shell had any systemd unit in its ancestry (a
# terminal, an IDE, an agent's own sandboxed shell — not specifically
# "already inside this scope"), silently reproducing the exact crash the
# throttle exists to prevent; none of the three capped memory. One shared
# function so the next fix can't apply to only one of three copies again.
#
# Usage: source this near the very top of a script, before anything else
# runs, then call kyth_deprioritize_on_desktop "$@" — it re-execs "$0 $@"
# inside the scope and exits with its result, or returns normally if
# systemd-run isn't available (CI runners, or a user manager that failed
# to start) so the caller just continues at normal priority.
kyth_deprioritize_on_desktop() {
	if [[ -n "${KYTH_VALIDATION_SCOPE:-}" ]] || ! command -v systemd-run >/dev/null 2>&1; then
		return 0
	fi
	export KYTH_VALIDATION_SCOPE=1
	if systemd-run --user --scope --collect --quiet \
		-p CPUWeight=20 -p IOWeight=10 -p MemoryHigh=50% -p MemoryMax=70% \
		-- "$0" "$@" 2>/dev/null; then
		exit $?
	fi
	# systemd-run --user failed (no user manager, e.g. some CI runners) — continue at normal priority
}
