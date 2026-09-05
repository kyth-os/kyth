mod installer_daemon;
mod installer_plan;
mod installer_runtime;
mod installer_storage;

fn main() -> std::process::ExitCode {
    match installer_daemon::run(&std::env::args().skip(1).collect::<Vec<_>>()) {
        Ok(()) => std::process::ExitCode::SUCCESS,
        Err(error) => {
            eprintln!("{error}");
            std::process::ExitCode::from(1)
        }
    }
}
