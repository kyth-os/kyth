fn main() -> std::process::ExitCode {
    match kyth_shared::privileged::serve() {
        Ok(()) => std::process::ExitCode::SUCCESS,
        Err(error) => {
            eprintln!("{error}");
            std::process::ExitCode::from(1)
        }
    }
}
