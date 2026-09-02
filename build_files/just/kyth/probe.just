# System probe JSON — single source for Hub Diagnostics and CLI
# Usage: ujust probe-json | jq .
[group('KythOS')]
probe-json:
    #!/usr/bin/env bash
    set -euo pipefail
    # Native collector and cache writer; the command emits the section values
    # used by the Rust Hub and never imports the compatibility package.
    exec /usr/bin/kyth-probe --print-only
