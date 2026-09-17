//! Desktop URI handler for `nxm://` Nexus Mods links. Usage errors exit 1;
//! handled-or-informed links exit 0.

use kyth_shared::system::nxm_handler;

fn main() {
    let url = std::env::args().nth(1);
    std::process::exit(nxm_handler::handle(
        url.as_deref(),
        &nxm_handler::home_dir(),
    ));
}
