//! Fallback network settings opener for sessions without a connection.
//! Always exits 0; replaces into the settings app when one is available.

use kyth_shared::system::network_fallback;
use std::os::unix::process::CommandExt;

fn main() {
    if let Some(argv) = network_fallback::fallback_argv() {
        let _ = std::process::Command::new(&argv[0]).args(&argv[1..]).exec();
    }
}
