# Installer feature parity

This document defines the installer bar for KythOS. It compares behaviors,
not visual similarity, and it deliberately separates consumer-workstation
requirements from enterprise storage/provisioning features.

## Reference installers

- Ubuntu's current desktop installer is the maintained successor to Ubiquity.
  Its documented baseline includes guided alongside installation, BitLocker
  blocking, manual partitioning, LVM/ZFS encryption, keyboard, language, and
  accessibility setup: [Ubuntu installation guide](https://documentation.ubuntu.com/desktop/en/24.04/tutorial/install-ubuntu-desktop/)
  and [advanced disk setup](https://documentation.ubuntu.com/desktop/en/latest/reference/advanced-disk-setup-features/).
- Anaconda's baseline includes Kickstart automation, remote/headless install,
  configurable storage schemes, rescue mode, driver disks, and remote logging:
  [Kickstart](https://anaconda-installer.readthedocs.io/en/latest/user-guide/kickstart.html),
  [boot options](https://anaconda-installer.readthedocs.io/en/latest/user-guide/boot-options.html),
  and [rescue mode](https://anaconda-installer.readthedocs.io/en/latest/rescue.html).
- Calamares documents guided alongside, replace-partition, whole-disk and
  manual modes, with encryption exposed in guided and manual partitioning:
  [Calamares partitioning](https://calamares.io/docs/partitions/).
- YaST/AutoYaST is the enterprise ceiling: automatic, guided and expert
  partitioning plus encryption, LVM, software RAID, multipath and reusable
  unattended profiles: [AutoYaST storage configuration](https://doc.opensuse.org/documentation/leap/archive/15.3/autoyast/html/book-autoyast/cha-configuration-installation-options.html).

## Current comparison

| Capability | KythOS | Consumer baseline | Enterprise baseline | Gate |
|---|---|---|---|---|
| Whole-disk install | bootc/Btrfs, final target rescan | Yes | Yes | Met |
| Guided Windows coexistence | NTFS check/info/dry-run, BitLocker refusal, geometry verification, GPT backup/restore | Yes | Yes | Exceeds consumer safety baseline |
| Use unallocated space | Exact live-region rescan before commit | Yes | Yes | Met |
| Replace one partition | Final ownership, mount, mapping, size and ESP checks | Yes | Yes | Met |
| Expert partitioner | Transaction journal, overlap simulation, one-root rule, EFI flagging, swap and per-filesystem fstab options | Yes | Yes | Met for physical partitions |
| BIOS and UEFI | ESP validation, BIOS-GRUB creation where bootc requires it, NVRAM entry-loss warning | Yes | Yes | Met |
| Locale, keyboard, timezone | Installed locale, console keymap and timezone selection; installer strings remain English | Yes | Yes | Partial; translated UI is Open P1 |
| Accessibility | Keyboard-operable controls, labels/live regions, skip link, large text, high contrast and reduced motion | Yes | Varies | Met at web UI level; screen-reader hardware test required |
| Unattended install | Headless CLI plus mode-0600 JSON answer files; all guided storage fields supported | Limited | Kickstart/AutoYaST | Met for fixed KythOS images, not general package provisioning |
| Failure diagnostics | Live streamed log, copyable full log, redacted machine-readable failure summary, mount cleanup | Varies | Remote logging/rescue | Met locally |
| Offline install | Exact pinned Fedora OCI image bundled in the ISO; optional CachyOS image requires network | Common | Common | Met for the default image |
| Full-disk encryption | Not exposed | LUKS/ZFS available | LUKS/LVM policies | **Open P0** |
| LVM/MD RAID/multipath/iSCSI | Existing mappings are detected and protected, but creation is not supported | Optional | Supported | Open enterprise scope |
| OEM/custom package selection | Fixed image with first-boot System Hub | Varies | Supported | Image-based alternative, not direct parity |
| In-installer rescue environment | Live desktop and System Hub repair tools, no dedicated installer rescue mode | Varies | Supported | Open P1 |

## Release gates

KythOS may call the installer *consumer feature-comparative* only when all P0
items above are complete and tested on real UEFI hardware. It may call the
installer *enterprise feature-comparative* only after LVM/RAID/network-storage
creation and a remote/unattended validation matrix exist. Until then, claims
must name the narrower strength: safe immutable-desktop and Windows dual-boot
installation.

Every storage release must exercise at least these physical or VM-backed cases:

1. Clean Windows 11 GPT/UEFI with NTFS shrink and a trailing recovery partition.
2. Hibernated/Fast Startup NTFS refusal with no partition-table mutation.
3. BitLocker refusal, including a BitLocker volume that is not mounted.
4. Existing Windows Boot Manager preserved in the ESP and firmware NVRAM.
5. 512-byte and 4K logical-sector disks, NVMe, SATA and removable media.
6. Free-space, replace-partition, whole-disk and expert layouts under UEFI and BIOS.
7. Power loss or injected failure before NTFS shrink, after filesystem shrink,
   after partition-boundary movement, and during bootloader installation.
8. Keyboard-only and screen-reader completion at the minimum supported display size.
9. Non-English locale/keymap installation and first login.
10. Answer-file wipe, alongside and free-space installations with secrets absent
    from process arguments, logs and failure summaries.

## Unattended answer files

Headless installs accept a JSON response file so passwords do not need to be
placed in process arguments. The file must be owned appropriately for the
invoking account, must not be a symlink, and must have mode `0600`:

```json
{
  "disk": "/dev/nvme0n1",
  "install_mode": "wipe",
  "username": "ada",
  "password": "replace-me",
  "hostname": "kyth",
  "timezone": "UTC",
  "locale": "en_US.UTF-8",
  "keymap": "us",
  "confirm_backup": true,
  "confirm_erase": true,
  "confirm_current": true
}
```

Run `kyth-installer --headless --answer-file /root/kyth-install.json` after
setting the file mode with `chmod 600`. Explicit command-line values override
matching answer-file fields.
