# Runtime migration report

The source of truth for runtime ownership is the generated
[`runtime-migration-report.json`](../build_files/config/runtime-migration-report.json),
produced from the generated
[`runtime-migration-inventory.json`](../build_files/config/runtime-migration-inventory.json).

The report distinguishes source implementation from installed runtime
authority. In particular, a Python file can be one of three different things:

- an active compatibility/runtime package;
- a source counterpart whose installed entry point is already native Rust; or
- source-only compatibility material that is not installed in the supported
  image.

Regenerate and validate both files with:

```text
python3 build_files/scripts/check-runtime-migration-inventory.py --generate
```

The normal repository validation command runs the checker without `--generate`
and fails if the checked-in inventory or report is stale. It also checks the
React/Tauri frontend boundaries for direct Python/process APIs, unscoped shell,
filesystem, or process plugins, and generic command bridges.

P0 interpretation:

- `python-installer` and `rust-transport-python-backend` are the remaining
  installer authority and are the highest-priority migration target.
- `python-shared-package` is an installed compatibility surface that should be
  reduced by active entry point, not by deleting every parser or fixture at
  once.
- `source-only` entries are not runtime migration tasks.
- Rust binaries, Rust services, and Rust dispatchers are counted separately
  from their retained Python source counterparts.
