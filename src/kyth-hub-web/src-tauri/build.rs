fn main() {
    // tauri-build emits rerun-if-changed for frontend_dist, icons, and
    // capabilities — but NOT for tauri.conf.json itself. Without this,
    // config-only changes (e.g. enableGTKAppId) never invalidate cargo's
    // fingerprint, and the image ships a stale kyth-hub-shell binary.
    println!("cargo:rerun-if-changed=tauri.conf.json");
    tauri_build::build()
}
