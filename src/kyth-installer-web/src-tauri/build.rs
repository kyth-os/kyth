fn main() {
    slint_build::compile("ui/installer.slint").expect("failed to compile native installer UI");
    // tauri-build does not emit rerun-if-changed for tauri.conf.json itself;
    // without this, config-only changes never invalidate cargo's fingerprint.
    println!("cargo:rerun-if-changed=tauri.conf.json");
    tauri_build::build()
}
