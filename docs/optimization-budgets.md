# Optimization Measurements

KythOS records optimization data instead of treating “leaner” as a subjective
goal. The checked source budgets cover installer JavaScript module size,
React/Tauri Hub source-file and inline-style counts, and the number of shared
probe collectors.
They are intentionally ceilings, not targets.

Run the static gate and print its report with:

```bash
just check-optimization
just optimization-report
```

On a representative installed KythOS system, add `--runtime` to measure the
shared probe pass. Release automation also supplies
the OCI manifest and RPM manifest, recording compressed image size, layer count,
and package count in `optimization.json` beside the other supply-chain inputs.

Budgets live in `build_files/config/optimization-budgets.json`. Raise one only
when an intentional capability justifies the added maintenance or runtime cost;
otherwise split, share, or remove code first.
