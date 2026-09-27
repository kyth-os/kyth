fn main() {
    slint_build::compile("ui/installer.slint").expect("failed to compile native installer UI");
    tauri_build::build()
}
