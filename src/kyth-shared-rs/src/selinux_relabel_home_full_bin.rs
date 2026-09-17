//! Background oneshot (never Before=plasmalogin.service): exhaustive relabel
//! of the rest of /var/home. Runs at idle priority via its unit file so it
//! cannot starve a running session. Skips via a per-deployment stamp.

use kyth_shared::system::selinux_relabel;

const STAMP: &str = "selinux-relabel-home-full.stamp";

fn main() {
    let deployment = selinux_relabel::deployment_id();
    let stamp_dir = selinux_relabel::stamp_dir();
    if selinux_relabel::already_done(&stamp_dir, STAMP, &deployment) {
        println!("kyth-selinux-relabel-home-full: already relabeled full tree for this deployment, skipping");
        return;
    }
    println!("kyth-selinux-relabel-home-full: relabeling /var/home (full tree, background) for deployment {deployment}");
    let ok = kyth_shared::system::process::run_bounded(
        &[
            "/sbin/restorecon".to_string(),
            "-RF".to_string(),
            "-T0".to_string(),
            "/var/home".to_string(),
        ],
        // No wall-clock bound on purpose: the unit carries the idle
        // priority and TimeoutStartSec, and restorecon -T0 already runs
        // single-threaded at the kernel's pace. A Hub-style timeout here
        // would abort multi-hour first-boot relabels of huge game trees.
        std::time::Duration::from_secs(86400),
    )
    .map(|output| output.status.success())
    .unwrap_or(false);
    if ok {
        selinux_relabel::write_stamp(&stamp_dir, STAMP, &deployment);
    }
}
