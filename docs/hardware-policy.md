# Hardware Policy

KythOS describes supported hardware behavior in
`build_files/config/hardware-profiles.toml`. The file is installed read-only as
`/usr/share/kyth/hardware-profiles.toml`; runtime evaluation never downloads or
executes profile content.

At boot, `kyth-hw-setup.service` invokes `kyth-hardware-policy apply`. The
engine reads PCI, USB, DMI, CPU and bound-driver identifiers from sysfs, matches
them against the versioned policy, and writes:

- `/var/lib/kyth/hardware-policy.json`: applied policy and result;
- `/var/lib/kyth/hardware-support.json`: current evaluation for diagnostics;
- `/etc/modprobe.d/90-kyth-hardware-policy.conf`: matched module options only;
- `/etc/scx/scx_loader.conf`: the first available approved scheduler.

The policy digest, hardware inventory digest, and running kernel form the setup
identity. An unchanged system exits quickly. A policy update, kernel update, or
hardware change is evaluated again automatically, replacing the old permanent
`hw-setup-done` marker.

## Matching and safety

Each PCI or USB selector must match one physical device as a unit. This avoids
combining the vendor from one device with the class or driver from another.
Multiple selectors are an AND operation, which permits explicit hybrid-GPU
profiles. Values within a selector are alternatives.

Profiles declare capabilities and a recommended image variant. Profile data
cannot provide commands. Runtime actions are limited to validated modprobe
options plus built-in handlers for sched-ext selection and NVIDIA module
preparation. Identifiers and option values reject whitespace and shell syntax.

## Managed quirks

A quirk must contain:

- a stable identifier and device/driver-specific match;
- a concise technical reason;
- a provenance link;
- an ISO review date in `expires_on`;
- one or more allowlisted actions.

An expired quirk remains active on matching machines to avoid silently
regressing working hardware. Validation fails, forcing a maintainer to confirm
the workaround is still needed and renew its date, or delete it after testing
the upstream fix.

Broad AMD, Intel, NVIDIA, MediaTek Wi-Fi, Intel Wi-Fi and Bluetooth module
options previously embedded in every image now come from matched quirks. The
old global `pcie_aspm=performance` kernel argument is removed during migration
because it traded laptop power behavior for a blanket workaround.

## Operator commands

```bash
kyth-hardware-policy inventory
kyth-hardware-policy evaluate
kyth-hardware-policy status
sudo kyth-hardware-policy apply --force
ujust hardware-policy
```

`inventory` includes hardware identifiers used for matching. Review it before
sharing because the DMI product and board names can identify a device model.

## Adding or changing support

1. Add the narrowest possible profile or quirk to the TOML policy.
2. Add fixture-based matching tests, including a nearby device that must not
   match.
3. Regenerate `docs/hardware-support-matrix.md` with the matrix command.
4. Record real-hardware results using the daily-driver validation process.
5. Promote a profile from experimental to supported or qualified only when its
   stated qualification evidence exists.

Planned image variants remain visibly marked as planned until the build,
release, Secure Boot, update, rollback, and hardware qualification paths all
publish and validate that distinct artifact. The universal image remains the
only updater target in the meantime.
