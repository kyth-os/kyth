//! Native replacement for the Python `kyth-apply-explorer` launcher.
//!
//! Loads `explorer.toml` (see `system::explorer_preset::load_explorer`) and
//! applies it via `system::explorer_preset::apply_explorer`, which tries the
//! installed Plasma 6/5 `kwriteconfig` candidates and reports successful
//! click and preview updates.

use kyth_shared::system::explorer_preset::{apply_explorer, explorer_path, load_explorer};

fn main() {
    let config = load_explorer(explorer_path(None::<&std::path::Path>));
    let applied = apply_explorer(&config);
    println!("kyth-apply-explorer: {}", applied.len());
}
