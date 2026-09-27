//! Boot oneshot: ensure the bluetooth radio is unblocked and powered on.
//! Best-effort throughout; always exits 0.

use kyth_shared::system::bluetooth_enable;

fn main() {
    bluetooth_enable::enable();
}
