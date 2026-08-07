# System probe JSON — single source for Hub Diagnostics and CLI
# Usage: ujust probe-json | jq .
[group('KythOS')]
probe-json:
    #!/usr/bin/env bash
    set -euo pipefail
    # Single source of truth: kyth_shared/system/probe.py collect_probe_results()
    # Both Hub DiagnosticsPage and `ujust smoke-check` consume the same JSON shape.
    # Hub: diagnostics.py:_system_hub_probe reads probe_cached; CLI: this recipe.
    python3 << 'PY'
    import json, sys
    try:
        from kyth_shared.system.probe import collect_probe_results
        results = collect_probe_results()
        out = {k: {'status': r.status.value, 'data': r.data, 'error': r.error} for k, r in results.items()}
        print(json.dumps(out, indent=2))
    except Exception as e:
        print(json.dumps({'error': str(e)}), file=sys.stderr)
        sys.exit(1)
    PY
