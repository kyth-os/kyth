# `kyth-config-apply` contract

The historical aggregate launcher is not present in this checkout. The
native replacement starts with a validation/planning boundary:

```json
{"operation":"pipewire"}
```

Requests are JSON objects on stdin. `operation` is one of `desktop`,
`display`, `input`, `network`, `pipewire`, `rgb`, `tailscale`, or `role`.
`role` additionally requires `profile` to be `everyday`, `gaming`, `dev`, or
`creator`. Unknown fields are ignored for forward compatibility, but no
request can name an executable or filesystem path. The current binary emits a
deterministic plan and performs no side effects. Executors will be added per
operation only after parity and rollback tests exist.
