fn main() {
    slint_build::compile("ui/installer.slint").expect("failed to compile native installer UI");
    // tauri-build does not emit rerun-if-changed for tauri.conf.json itself;
    // without this, config-only changes never invalidate cargo's fingerprint.
    println!("cargo:rerun-if-changed=tauri.conf.json");
    // Autogenerate `allow-<command>` / `deny-<command>` ACL permissions for
    // the backend proxy commands below. Without an app ACL manifest, Tauri
    // v2 lets every invoke() through on a local origin via a fail-open
    // carve-out that v3 removes — and adding capabilities/ without these
    // permissions would reject ALL installer IPC. The capability file
    // references the `allow-*` names generated here; keep the two lists in
    // sync when commands are added or removed.
    tauri_build::try_build(tauri_build::Attributes::new().app_manifest(
        tauri_build::AppManifest::new().commands(&[
            "installer_connection",
            "installer_validate_plan",
            "installer_recovery_guidance",
            "installer_execution_plan",
            "installer_request",
            "installer_stream",
            "installer_stream_stop",
        ]),
    ))
    .expect("tauri build failed")
}
