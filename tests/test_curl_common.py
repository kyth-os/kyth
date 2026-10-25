"""Exercise the sourced production helper with real curl and synthetic secrets."""

import http.server
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
import threading
import unittest


ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "build_files/scripts/lib/curl-common.sh"
TOKEN = "synthetic-curl-common-fixture-only"


@unittest.skipUnless(shutil.which("bash") and shutil.which("curl"), "requires bash and curl")
class CurlCommonTests(unittest.TestCase):
    def exercise_helper(self, authenticated):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            secret = directory / "github_token"
            if authenticated:
                secret.write_text(TOKEN + "\n", encoding="utf-8")
            helper = directory / "curl-common.sh"
            # Adapt only the secret path; execute the actual production source.
            helper.write_text(
                HELPER.read_text(encoding="utf-8").replace(
                    "/run/secrets/github_token", str(secret)
                ),
                encoding="utf-8",
            )
            curl = shutil.which("curl")
            assert curl is not None
            wrapper = directory / "curl"
            wrapper.write_text(
                '#!/bin/bash\n'
                'printf "%s\\0" "$@" >>"$ARGV_LOG"\n'
                'printf "%s" "$$" >"$CURL_PID"\n'
                f'exec {shlex.quote(curl)} "$@"\n',
                encoding="utf-8",
            )
            wrapper.chmod(0o700)
            requests = []
            pid_file = directory / "curl.pid"

            class Handler(http.server.BaseHTTPRequestHandler):
                def do_GET(self):
                    pid = pid_file.read_text(encoding="utf-8")
                    argv = Path(f"/proc/{pid}/cmdline").read_bytes()
                    requests.append((self.headers.get("Authorization"), argv))
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(b"ok")

                def log_message(self, format, *args):
                    pass

            server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            environment = os.environ.copy()
            environment.update(
                PATH=str(directory) + os.pathsep + environment["PATH"],
                ARGV_LOG=str(directory / "argv"),
                CURL_PID=str(pid_file),
            )
            script = r'''
set -euo pipefail
# Legacy compatibility lets this regression reproduce the original array bug.
# The production function overrides this shim when the helper is sourced.
github_api_curl() { command curl "${CURL_AUTH_ARGS[@]}" "$@"; }
fd_count() { local fds=(/proc/$$/fd/*); printf '%s\n' "${#fds[@]}"; }
before=$(fd_count)
source "$1"
CURL_COMMON_ARGS+=(--max-time 5)
: "source-time substitutions have finished before any curl starts"
github_api_curl -fsS --noproxy '*' "${CURL_COMMON_ARGS[@]}" "$2/first"
: "a later request must still carry authentication"
github_api_curl -fsS --noproxy '*' "${CURL_COMMON_ARGS[@]}" "$2/second"
for ((i = 0; i < 20; i++)); do source "$1"; done
github_api_curl -fsS --noproxy '*' "${CURL_COMMON_ARGS[@]}" --max-time 5 "$2/resourced"
# A leaked fd per source is permanent and can never settle; a transient
# fd (a curl connection still tearing down) can. Poll briefly for the
# count to return to the baseline before declaring a leak — the old
# one-shot comparison flaked intermittently under load.
after=$(fd_count)
for ((i = 0; i < 20 && after != before; i++)); do
  sleep 0.1
  after=$(fd_count)
done
[[ "$before" == "$after" ]]
'''
            try:
                result = subprocess.run(
                    ["bash", "-c", script, "curl-common-test", str(helper),
                     f"http://127.0.0.1:{server.server_port}"],
                    env=environment, capture_output=True, timeout=20,
                )
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)
            self.assertNotIn(TOKEN.encode(), result.stdout + result.stderr)
            self.assertEqual(result.returncode, 0, result.stderr.decode())
            self.assertEqual(len(requests), 3)
            for header, argv in requests:
                self.assertTrue(
                    header == f"token {TOKEN}" if authenticated else header is None,
                    "unexpected Authorization on an actual request",
                )
                self.assertNotIn(TOKEN.encode(), argv)
            logged_argv = (directory / "argv").read_bytes()
            self.assertNotIn(TOKEN.encode(), logged_argv)
            if authenticated:
                self.assertIn(b"-K\0/dev/fd/", logged_argv)
            else:
                self.assertNotIn(b"-K\0", logged_argv)
            self.assertEqual(
                {path.name for path in directory.iterdir()},
                {"curl-common.sh", "curl", "argv", "curl.pid"}
                | ({"github_token"} if authenticated else set()),
            )

    def test_auth_survives_multiple_later_calls_and_repeated_sourcing(self):
        self.exercise_helper(authenticated=True)

    def test_missing_secret_uses_anonymous_requests(self):
        self.exercise_helper(authenticated=False)


if __name__ == "__main__":
    unittest.main()
