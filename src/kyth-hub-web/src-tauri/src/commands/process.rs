use std::process::Output;

/// Common error type for helper-process launches from Tauri commands.
#[derive(Debug)]
pub(crate) enum CommandError {
    Spawn(std::io::Error),
    Output(std::io::Error),
    Timeout(std::io::Error),
}

impl std::fmt::Display for CommandError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Spawn(error) => write!(f, "could not start command: {error}"),
            Self::Output(error) => write!(f, "could not read command output: {error}"),
            Self::Timeout(error) => write!(f, "command timed out: {error}"),
        }
    }
}

/// Run a fixed helper command and keep process launching/error conversion in
/// one place. Callers decide whether non-zero exit status is a failure,
/// because some probes intentionally use exit status as data.
pub(crate) fn output(program: &str, args: &[&str]) -> Result<Output, CommandError> {
    let argv = std::iter::once(program.to_string())
        .chain(args.iter().map(|arg| (*arg).to_string()))
        .collect::<Vec<_>>();
    // Single-sourced with every other Hub recipe action so a tier change
    // cannot leave this helper behind on its own magic number.
    let bound = kyth_shared::system::jobs::timeout_for(
        kyth_shared::system::jobs::JobTimeoutClass::HubAction,
    );
    kyth_shared::system::process::run_bounded(&argv, bound).map_err(classify_error)
}

/// Map a runner failure onto the caller's error vocabulary. A timeout is
/// neither a spawn failure nor an output failure — labeling it "could not
/// read command output" sent diagnosis in the wrong direction.
fn classify_error(error: std::io::Error) -> CommandError {
    match error.kind() {
        std::io::ErrorKind::NotFound => CommandError::Spawn(error),
        std::io::ErrorKind::TimedOut => CommandError::Timeout(error),
        _ => CommandError::Output(error),
    }
}

/// Prevent helper output from becoming an unbounded UI error message.
pub(crate) fn bounded_text(bytes: &[u8]) -> String {
    let text = kyth_shared::system::process::strip_ansi(&String::from_utf8_lossy(bytes));
    kyth_shared::system::process::redact_sensitive_text(text.trim())
        .chars()
        .take(400)
        .collect()
}

#[cfg(test)]
mod tests {
    use super::{bounded_text, classify_error, output, CommandError};

    #[test]
    fn timeout_is_classified_as_timeout_not_output() {
        let error = std::io::Error::from(std::io::ErrorKind::TimedOut);
        let classified = classify_error(error);
        assert!(matches!(classified, CommandError::Timeout(_)));
        assert!(classified.to_string().starts_with("command timed out"));
        let missing = classify_error(std::io::Error::from(std::io::ErrorKind::NotFound));
        assert!(matches!(missing, CommandError::Spawn(_)));
        let other = classify_error(std::io::Error::from(std::io::ErrorKind::PermissionDenied));
        assert!(matches!(other, CommandError::Output(_)));
    }

    #[test]
    fn bounded_text_trims_and_caps_helper_output() {
        let text = format!("  {}  ", "x".repeat(500));
        let bounded = bounded_text(text.as_bytes());
        assert_eq!(bounded.len(), 400);
        assert!(!bounded.starts_with(' '));
    }

    #[test]
    fn missing_helper_is_a_typed_spawn_error() {
        let error =
            output("/definitely/missing/kyth-helper", &[]).expect_err("missing helper should fail");
        assert!(matches!(error, CommandError::Spawn(_)));
    }
}
