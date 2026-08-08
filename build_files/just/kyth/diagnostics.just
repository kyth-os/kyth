# Print a short KythOS system/kernel tuning summary.
[group('KythOS')]
kerver:
    #!/usr/bin/env bash
    set -euo pipefail
    /usr/bin/kyth-kerver

# Print a paste-friendly system support snapshot.
[group('KythOS')]
device-info:
    #!/usr/bin/env bash
    set -euo pipefail
    /usr/bin/kyth-device-info

# Run the daily-driver readiness smoke check.
[group('KythOS')]
smoke-check *args:
    #!/usr/bin/env bash
    set -euo pipefail
    /usr/bin/kyth-smoke-check {{ args }}

# Run the once-per-deployment post-update confidence check now.
[group('KythOS')]
post-update-check *args:
    #!/usr/bin/env bash
    set -euo pipefail
    /usr/bin/kyth-post-update-check --force {{ args }}

# Check common suspend/resume regressions: network, audio, Bluetooth, display, Vulkan.
[group('KythOS')]
resume-check:
    #!/usr/bin/env bash
    set -euo pipefail
    /usr/bin/kyth-resume-check

# Measure boot time and app-launch latency, tracked over time.
[group('KythOS')]
snappy-bench *args:
    #!/usr/bin/env bash
    set -euo pipefail
    /usr/bin/kyth-snappy-bench {{ args }}

# Perf gate 5% — CI fails if gaming-audit p95 regresses
[group('KythOS')]
perf-gate mode="status":
    #!/usr/bin/env bash
    set -euo pipefail
    /usr/bin/kyth-perf-gate "{{ mode }}"

# Telemetry privacy — offline collectors opt-out + purge
[group('KythOS')]
telemetry-opt mode="status":
    #!/usr/bin/env bash
    set -euo pipefail
    /usr/bin/kyth-telemetry-opt "{{ mode }}"
