//! Boot oneshot: migrate a stale SDDM /etc overlay to PLM. Idempotent; a
//! no-op once converged. Always exits 0 — a boot helper must never fail
//! the boot because the display stack was already correct.

use kyth_shared::system::display_manager_migrate;

fn main() {
    display_manager_migrate::migrate(
        &display_manager_migrate::etc_root(),
        &display_manager_migrate::lib_root(),
        &display_manager_migrate::systemctl_output,
    );
}
