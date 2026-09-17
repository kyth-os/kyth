//! Boot oneshot (Before=plasmalogin.service): fast relabel of the /var/home
//! paths login actually stats. Bounded by account count, never by home
//! size. Skips via a per-deployment stamp. Always exits 0.

use kyth_shared::system::selinux_relabel;

const STAMP: &str = "selinux-relabel-home.stamp";

fn main() {
    let deployment = selinux_relabel::deployment_id();
    let stamp_dir = selinux_relabel::stamp_dir();
    if selinux_relabel::already_done(&stamp_dir, STAMP, &deployment) {
        println!("kyth-selinux-relabel-home: already relabeled login-critical paths for this deployment, skipping");
        return;
    }
    println!("kyth-selinux-relabel-home: relabeling login-critical /var/home paths for deployment {deployment}");
    if !selinux_relabel::restorecon_forced(&["/var/home".to_string()]) {
        eprintln!("kyth-selinux-relabel-home: warning: restorecon failed for /var/home");
    }
    if let Ok(homes) = std::fs::read_dir("/var/home") {
        for home in homes.flatten() {
            let path = home.path();
            if !path.is_dir() {
                continue;
            }
            let paths = selinux_relabel::login_paths(&path);
            if !selinux_relabel::restorecon_forced(&paths) {
                eprintln!(
                    "kyth-selinux-relabel-home: warning: restorecon failed for {}",
                    path.display()
                );
            }
        }
    }
    selinux_relabel::write_stamp(&stamp_dir, STAMP, &deployment);
}
