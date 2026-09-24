//! Background oneshot (never Before=plasmalogin.service): exhaustive relabel
//! of the rest of /var/home. Runs at idle priority via its unit file so it
//! cannot starve a running session. Skips while the active file-context policy
//! fingerprint is unchanged; falls back to a deployment stamp if unreadable.

use kyth_shared::system::selinux_relabel;

const STAMP: &str = "selinux-relabel-home-full.stamp";

fn main() {
    let deployment = selinux_relabel::deployment_id();
    let policy_fingerprint = selinux_relabel::active_file_contexts_fingerprint();
    let stamp = selinux_relabel::full_relabel_stamp(policy_fingerprint.as_deref(), &deployment);
    let stamp_dir = selinux_relabel::stamp_dir();
    if selinux_relabel::already_done(&stamp_dir, STAMP, &stamp) {
        println!(
            "kyth-selinux-relabel-home-full: active SELinux policy already relabeled, skipping"
        );
        return;
    }
    println!("kyth-selinux-relabel-home-full: relabeling /var/home (full tree, background) for stamp {stamp}");
    let ok = kyth_shared::system::process::run_bounded(
        &[
            "/sbin/restorecon".to_string(),
            "-RF".to_string(),
            "-D".to_string(),
            "-T0".to_string(),
            "/var/home".to_string(),
        ],
        // The 24-hour process bound matches TimeoutStartSec on the idle
        // background unit. restorecon -T0 uses available CPU cores; -D stores
        // policy digests on completed directories so interrupted runs can
        // skip subtrees already relabeled under the same policy.
        std::time::Duration::from_secs(86400),
    )
    .map(|output| output.status.success())
    .unwrap_or(false);
    if ok {
        selinux_relabel::write_stamp(&stamp_dir, STAMP, &stamp);
    }
}
