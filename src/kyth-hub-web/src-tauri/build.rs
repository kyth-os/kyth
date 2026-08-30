fn main() {
    slint_build::compile("ui/hub.slint").expect("failed to compile native Hub UI");
    tauri_build::build()
}
