//! Boot oneshot: merge vendor account databases and ensure peripheral and
//! greeter accounts exist before udev parses rules. Always exits 0.

use kyth_shared::system::system_accounts;
use std::path::Path;

fn main() {
    system_accounts::fix(Path::new("/"), Path::new("/usr/lib"));
}
