# Health-Aware Updates

KythOS treats an update as successful only after the booted image passes
required health checks. Downloading an image or reaching the bootloader is not
enough.

## Lifecycle

1. The update watcher resolves the remote image to an immutable digest.
2. It refuses a digest that is quarantined locally or belongs to a different
   explicitly configured rollout ring.
3. After `bootc upgrade` stages the deployment, KythOS records the pending
   digest in `/var/lib/kyth/boot-health.json`. A pull that times out
   (`bootc upgrade` up to 1800 s) is **retryable** — no pending digest or
   quarantine is written, and the next run retries the same digest.
   Only after three unhealthy boots (step 6) does a digest become
   quarantined; `retryable: bootc upgrade timed out` in
   `/var/lib/kyth/update-watcher-status.json` surfaces as "Retry available"
   in System Hub.
4. On the next boot, greenboot runs KythOS checks from
   `/etc/greenboot/check/required.d`.
5. A healthy boot records the exact digest as known-good. A failed boot records
   the boot ID and reason, then greenboot retries the boot.
6. After three unhealthy boots, greenboot rolls back to the previous bootc
   deployment and KythOS quarantines the failed digest. The automatic updater
   and guarded manual update paths will not download or stage that digest again.

The required checks deliberately cover immutable deployment invariants: KythOS
identity, bootc deployment metadata, the desktop and networking components, and
the running kernel's module tree. They do not fail because a user disabled a
service, disconnected a network cable, or changed mutable `/etc` policy. Such a
failure would survive an OS rollback and could otherwise create a reboot loop.

## Release Rings

`/etc/kyth/auto-update.toml` supports these policies:

- `follow-image` follows the channel selected in System Hub.
- `stable` accepts only the `latest` image family.
- `testing` accepts only the `testing` image family.
- `canary` is reserved for explicitly published pre-testing images.

Explicit ring policy fails closed if the machine is accidentally switched to a
different image family. Ring selection does not bypass signature, digest, or
qualification checks.

## Inspect and Recover

Show bootc and health state:

```bash
ujust status
ujust update-health
kyth-boot-health status --json
```

System Hub also displays the current boot-health state, failed-boot count, and
number of quarantined builds on the Updates page. Support snapshots include the
same non-secret information.

A quarantined digest stays blocked even when a mutable registry tag still
points to it. After confirming that the image was repaired or the failure was
environmental, an administrator can explicitly retry it:

```bash
ujust retry-quarantined-update sha256:FULL_DIGEST
```

Clearing quarantine does not immediately update or reboot the machine. It only
allows the normal update watcher to consider that digest again.

System Hub, `ujust kyth-upgrade`, the full updater, and the Hub-independent
fallback updater all use `kyth-safe-upgrade`. Direct `sudo bootc upgrade`
remains available as an expert escape hatch, but requires normal administrator
authentication and deliberately bypasses KythOS quarantine policy.

## Troubleshooting: Staged Upgrade Not Taking Effect

Symptom: `bootc upgrade` (or `bootc switch`) reports success and "Queued for
next boot" with the correct digest, but after reboot `bootc status` still
shows the old digest — and repeating `bootc upgrade` any number of times
doesn't change the outcome.

Root cause observed on the ASUS TUF FA617NS host (2026-08-20): staging always
succeeded (the new deployment tree was fully written under
`/ostree/deploy/default/deploy/`), but the step that promotes a staged
deployment into a real bootloader entry — `ExecStop=/usr/bin/ostree admin
finalize-staged` on `ostree-finalize-staged.service`, which runs at shutdown
— failed with:

```
error: Remounting /boot read-write: Invalid argument
```

`/boot` on this layout is a bind mount of itself onto the same btrfs subvol as
root (`subvolid=5,subvol=/`), mounted read-only during normal operation;
finalize needs to remount it read-write briefly to write the new
kernel/initramfs/loader entry. When that remount fails at shutdown, the
staged deployment appears to be silently dropped rather than retried — no
error is surfaced to the user, and the next boot just reuses the previous
default. This reproduced even after a single clean `bootc upgrade` followed
by a single clean `systemctl reboot` (not just after re-running upgrade
mid-flight), so don't assume a "ran it twice" race is always the explanation.

Diagnose with:

```bash
journalctl -b -1 -u ostree-finalize-staged.service
```

Look for the `Invalid argument` line right after `Stopping
ostree-finalize-staged.service`.

`kyth-safe-upgrade` now remounts `/boot` and runs `ostree admin finalize-staged`
in the same session as the pull, so a GUI or `ujust kyth-upgrade` reboot
applies the image on the first try. `ostree-finalize-staged.service` is also
wrapped (immediate ExecStart plus shutdown ExecStop) so a raw `bootc upgrade`
writes the bootloader entry before reboot.

If you are already stuck with "Queued for next boot" on an older image:

```bash
sudo mount -o remount,bind,rw /boot
sudo ostree admin finalize-staged         # should print "Bootloader updated; bootconfig swap: yes"
sudo ostree admin status                  # confirm it now shows "(pending)"
sudo systemctl reboot
```

Or, on an image that includes the helper: `sudo kyth-finalize-staged reboot`
or `ujust apply-staged`.

## State and Privacy

The state file contains image digests, timestamps, failure counts, rollout
ring, and the last health-check reason. It contains no hostname, account name,
network address, hardware serial number, or telemetry upload identifier. The
file is readable for diagnostics but writable only by privileged system
services.
