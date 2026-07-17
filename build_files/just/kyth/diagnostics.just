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
