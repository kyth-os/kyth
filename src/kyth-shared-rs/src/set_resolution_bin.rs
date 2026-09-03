//! Bounded display-mode bootstrap for Plasma sessions.

use regex::Regex;
use std::{env, path::PathBuf, thread, time::Duration};

fn valid_token(value: &str) -> bool {
    !value.is_empty()
        && value
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || b"._-".contains(&byte))
}

fn valid_mode(value: &str) -> bool {
    !value.is_empty()
        && value
            .bytes()
            .all(|byte| byte.is_ascii_digit() || b"x@._-".contains(&byte))
}

fn first_modes(output: &str) -> Vec<(String, String)> {
    let output_re = Regex::new(r"^Output:\s+\d+\s+(\S+)").unwrap();
    let modes_re = Regex::new(r"(\d+):(\d+x\d+@[\d.]+)").unwrap();
    let mut current = None;
    let mut found = Vec::new();
    for line in output.lines().map(str::trim) {
        if let Some(capture) = output_re.captures(line) {
            current = capture.get(1).map(|value| value.as_str().to_string());
            continue;
        }
        if line.starts_with("Modes:") {
            if let Some(name) = current.take() {
                if let Some(capture) = modes_re.captures(line) {
                    let mode = capture.get(2).unwrap().as_str().to_string();
                    if valid_token(&name) && valid_mode(&mode) {
                        found.push((name, mode));
                    }
                }
            }
        }
    }
    found
}

fn main() {
    let args: Vec<String> = env::args().skip(1).collect();
    let autostart = args
        .windows(2)
        .find(|pair| pair[0] == "--autostart")
        .map(|pair| PathBuf::from(&pair[1]))
        .unwrap_or_else(|| {
            PathBuf::from(
                env::var_os("HOME")
                    .map(PathBuf::from)
                    .unwrap_or_else(|| PathBuf::from("/root"))
                    .join(".config/autostart/kyth-set-resolution.desktop"),
            )
        });
    let mut report = String::new();
    for _ in 0..8 {
        let argv = vec!["kscreen-doctor".into(), "-o".into()];
        if let Ok(result) = kyth_shared::system::process::run_bounded(&argv, Duration::from_secs(5))
        {
            let text = String::from_utf8_lossy(&result.stdout);
            if result.status.success() && !text.trim().is_empty() {
                report = text.into_owned();
                break;
            }
        }
        thread::sleep(Duration::from_millis(250));
    }
    for (output, mode) in first_modes(&report) {
        let argv = vec![
            "kscreen-doctor".into(),
            format!("output.{output}.enable"),
            format!("output.{output}.mode.{mode}"),
        ];
        let _ = kyth_shared::system::process::run_bounded(&argv, Duration::from_secs(5));
    }
    let _ = std::fs::remove_file(autostart);
}

#[cfg(test)]
mod tests {
    use super::first_modes;

    #[test]
    fn selects_first_mode_for_each_output() {
        let rows = first_modes("Output: 1 HDMI-A-1\nModes: 0:1920x1080@60 1:1280x720@60\nOutput: 2 DP-1\nModes: 0:2560x1440@144\n");
        assert_eq!(
            rows,
            [
                ("HDMI-A-1".into(), "1920x1080@60".into()),
                ("DP-1".into(), "2560x1440@144".into())
            ]
        );
    }

    #[test]
    fn rejects_injection_shaped_output_names() {
        assert!(first_modes("Output: 1 bad;touch\nModes: 0:1920x1080@60\n").is_empty());
    }
}
