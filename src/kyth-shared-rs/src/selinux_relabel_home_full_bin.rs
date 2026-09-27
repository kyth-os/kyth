//! Background oneshot (never Before=plasmalogin.service): exhaustive relabel
//! of the rest of /var/home. Runs at idle priority via its unit file so it
//! cannot starve a running session. Skips while the active file-context policy
//! fingerprint is unchanged; falls back to a deployment stamp if unreadable.
//!
//! Rootless overlay storage is excluded from `restorecon -D` and has leftover
//! `security.sehash` xattrs stripped: those digests make overlayfs directory
//! copy-up return EPERM in a user namespace, which breaks dnf/apt in distrobox.

use std::path::Path;
use std::time::Duration;

use kyth_shared::system::selinux_relabel;

const STAMP: &str = "selinux-relabel-home-full.stamp";
const HOME_ROOT: &str = "/var/home";

fn main() {
    let deployment = selinux_relabel::deployment_id();
    let policy_fingerprint = selinux_relabel::active_file_contexts_fingerprint();
    let stamp = selinux_relabel::full_relabel_stamp(policy_fingerprint.as_deref(), &deployment);
    let stamp_dir = selinux_relabel::stamp_dir();
    let home_root = Path::new(HOME_ROOT);

    // Always strip overlay sehash, even when the restorecon walk is skipped.
    // A previous un-excluded -D pass leaves boxes unable to upgrade until
    // this runs once on an already-stamped host.
    for overlay in selinux_relabel::overlay_exclude_paths(home_root) {
        let _ = kyth_shared::system::process::run_bounded(
            &selinux_relabel::overlay_sehash_cleanup_argv(&overlay),
            Duration::from_secs(3600),
        );
    }

    if selinux_relabel::already_done(&stamp_dir, STAMP, &stamp) {
        println!(
            "kyth-selinux-relabel-home-full: active SELinux policy already relabeled, skipping"
        );
        return;
    }
    println!("kyth-selinux-relabel-home-full: relabeling /var/home (full tree, background) for stamp {stamp}");
    let ok = kyth_shared::system::process::run_bounded(
        &selinux_relabel::full_restorecon_argv(home_root),
        // The 24-hour process bound matches TimeoutStartSec on the idle
        // background unit. restorecon -T0 uses available CPU cores; -D stores
        // policy digests on completed directories so interrupted runs can
        // skip subtrees already relabeled under the same policy. Overlay
        // layer dirs are passed with -e so -D cannot plant security.sehash
        // on rootless container storage.
        Duration::from_secs(86400),
    )
    .map(|output| output.status.success())
    .unwrap_or(false);
    if ok {
        selinux_relabel::write_stamp(&stamp_dir, STAMP, &stamp);
    }
}
