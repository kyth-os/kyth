//! Pure streaming-command state and cancellation model.
//!
//! No process is spawned here. The model owns output framing, recent-output
//! retention, timeout decisions, and cancellation state so a later executor
//! can be tested against deterministic behavior before it gains authority to
//! run installer commands.

use std::collections::VecDeque;
use std::fs::OpenOptions;
use std::io::{self, Read, Write};
use std::os::unix::fs::{OpenOptionsExt, PermissionsExt};
use std::path::PathBuf;
use std::process::{Child, Command, ExitStatus, Stdio};
use std::time::{Duration, Instant};

const RECENT_OUTPUT_LINES: usize = 30;
const FAILURE_OUTPUT_LINES: usize = 10;
const STREAM_READ_CHUNK: usize = 64 * 1024;
const STREAM_POLL_INTERVAL: Duration = Duration::from_millis(100);
const MAX_INSTALLER_LOG_BYTES: u64 = 1024 * 1024;
const DEFAULT_OPERATION_TIMEOUT: Duration = Duration::from_secs(4 * 60 * 60);

fn append_installer_log_at(path: &std::path::Path, line: &str) {
    let Ok(mut file) = OpenOptions::new()
        .create(true)
        .append(true)
        .mode(0o600)
        .custom_flags(libc::O_NOFOLLOW)
        .open(path)
    else {
        return;
    };
    if file
        .set_permissions(std::fs::Permissions::from_mode(0o600))
        .is_err()
    {
        return;
    }
    if line.len() as u64 >= MAX_INSTALLER_LOG_BYTES {
        if file.set_len(0).is_err() {
            return;
        }
        let suffix = &line.as_bytes()[line.len() - (MAX_INSTALLER_LOG_BYTES as usize - 1)..];
        let _ = file.write_all(suffix);
        let _ = file.write_all(b"\n");
        return;
    }
    let line_bytes = line.len().saturating_add(1) as u64;
    if file
        .metadata()
        .map(|metadata| metadata.len().saturating_add(line_bytes) > MAX_INSTALLER_LOG_BYTES)
        .unwrap_or(false)
    {
        if file.set_len(0).is_err() {
            return;
        }
    }
    let _ = file.write_all(line.as_bytes());
    let _ = file.write_all(b"\n");
}

fn append_installer_log(line: &str) {
    let path = std::env::var_os("KYTH_INSTALLER_LOG")
        .map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from("/run/kyth-installer/log"));
    append_installer_log_at(&path, line);
}

#[derive(Debug, PartialEq, Eq)]
pub(crate) enum StreamEvent {
    Log(String),
}

/// Own a long-running executor child until it exits, is cancelled, or times out.
///
/// The daemon currently consumes the same line-oriented log protocol as the
/// compatibility runner, so events are written to stdout one line at a time.
/// Keeping the child and its cleanup here makes cancellation and failure
/// classification independent of the caller that planned the operation.
pub(crate) fn run_command(
    command: &mut Command,
    cancel_requested: impl Fn() -> bool,
) -> Result<ExitStatus, String> {
    let mut child = command
        .stdout(Stdio::piped())
        // Keep diagnostics flowing to the daemon's journal. Leaving a piped
        // stderr unread can fill the pipe and deadlock a verbose disk tool.
        .stderr(Stdio::inherit())
        .spawn()
        .map_err(|error| format!("could not spawn streaming command: {error}"))?;
    let result = run_child(&mut child, cancel_requested, DEFAULT_OPERATION_TIMEOUT);
    if result.is_err() && child.try_wait().ok().flatten().is_none() {
        let _ = child.kill();
    }
    let _ = child.wait();
    result
}

pub(crate) fn run_command_timeout(
    command: &mut Command,
    cancel_requested: impl Fn() -> bool,
    timeout: Duration,
) -> Result<ExitStatus, String> {
    let mut child = command
        .stdout(Stdio::piped())
        .stderr(Stdio::inherit())
        .spawn()
        .map_err(|error| format!("could not spawn streaming command: {error}"))?;
    let result = run_child(&mut child, cancel_requested, timeout);
    if result.is_err() && child.try_wait().ok().flatten().is_none() {
        let _ = child.kill();
    }
    let _ = child.wait();
    result
}

/// Run a fixed helper operation while supplying a bounded JSON request on
/// stdin. The helper is spawned and reaped through the same cancellation and
/// output path as streaming commands.
pub(crate) fn run_command_with_input(
    command: &mut Command,
    input: &[u8],
    cancel_requested: impl Fn() -> bool,
) -> Result<ExitStatus, String> {
    let mut child = command
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::inherit())
        .spawn()
        .map_err(|error| format!("could not spawn helper operation: {error}"))?;
    if let Some(mut stdin) = child.stdin.take() {
        stdin
            .write_all(input)
            .map_err(|error| format!("could not provide helper operation input: {error}"))?;
    }
    let result = run_child(&mut child, cancel_requested, DEFAULT_OPERATION_TIMEOUT);
    if result.is_err() && child.try_wait().ok().flatten().is_none() {
        let _ = child.kill();
    }
    let _ = child.wait();
    result
}

fn run_child(
    child: &mut Child,
    cancel_requested: impl Fn() -> bool,
    timeout: Duration,
) -> Result<ExitStatus, String> {
    let started = Instant::now();
    let mut model = StreamingCommandModel::new(0, 0);
    let mut output = child
        .stdout
        .take()
        .ok_or_else(|| "streaming command stdout was not captured".to_string())?;
    let fd = std::os::unix::io::AsRawFd::as_raw_fd(&output);
    let flags = unsafe { libc::fcntl(fd, libc::F_GETFL) };
    if flags < 0 || unsafe { libc::fcntl(fd, libc::F_SETFL, flags | libc::O_NONBLOCK) } < 0 {
        return Err(format!(
            "could not configure streaming command output: {}",
            io::Error::last_os_error()
        ));
    }
    let mut buffer = [0u8; STREAM_READ_CHUNK];
    let mut output_closed = false;
    loop {
        if cancel_requested() {
            let _ = child.kill();
            return Err(
                "Installation cancelled by user. Disk changes may have already started."
                    .to_string(),
            );
        }
        if started.elapsed() >= timeout {
            let _ = child.kill();
            return Err(format!(
                "Command timed out after {} seconds",
                timeout.as_secs()
            ));
        }
        if !output_closed {
            match output.read(&mut buffer) {
                Ok(0) => output_closed = true,
                Ok(size) => {
                    for event in model.feed(&buffer[..size], started.elapsed().as_secs()) {
                        let StreamEvent::Log(line) = event;
                        append_installer_log(&line);
                        println!("{line}");
                    }
                }
                Err(error) if error.kind() == io::ErrorKind::WouldBlock => {}
                Err(error) if error.kind() == io::ErrorKind::Interrupted => continue,
                Err(error) => {
                    return Err(format!("could not read streaming command output: {error}"))
                }
            }
        }
        if let Some(status) = child
            .try_wait()
            .map_err(|error| format!("could not poll streaming command: {error}"))?
        {
            for event in model.finish_output() {
                let StreamEvent::Log(line) = event;
                append_installer_log(&line);
                println!("{line}");
            }
            return model
                .finish_status(status.code().unwrap_or(1))
                .map(|_| status);
        }
        std::thread::sleep(STREAM_POLL_INTERVAL);
    }
}

#[derive(Debug)]
pub(crate) struct StreamingCommandModel {
    pending: String,
    pending_utf8: Vec<u8>,
    last_line: Option<String>,
    recent_output: VecDeque<String>,
    started_at: u64,
    last_activity: u64,
    last_rx_activity: u64,
    last_rx: u64,
    total_bytes: u64,
    cancelled: bool,
}

impl StreamingCommandModel {
    pub(crate) fn new(now: u64, rx_bytes: u64) -> Self {
        Self {
            pending: String::new(),
            pending_utf8: Vec::new(),
            last_line: None,
            recent_output: VecDeque::with_capacity(RECENT_OUTPUT_LINES),
            started_at: now,
            last_activity: now,
            last_rx_activity: now,
            last_rx: rx_bytes,
            total_bytes: 0,
            cancelled: false,
        }
    }

    pub(crate) fn feed(&mut self, bytes: &[u8], now: u64) -> Vec<StreamEvent> {
        self.last_activity = now;
        self.decode(bytes, false);
        self.take_lines(false)
    }

    pub(crate) fn finish_output(&mut self) -> Vec<StreamEvent> {
        self.decode(&[], true);
        self.take_lines(true)
    }

    fn decode(&mut self, bytes: &[u8], final_chunk: bool) {
        self.pending_utf8.extend_from_slice(bytes);
        let mut offset = 0;
        loop {
            match std::str::from_utf8(&self.pending_utf8[offset..]) {
                Ok(text) => {
                    self.pending.push_str(text);
                    self.pending_utf8.clear();
                    break;
                }
                Err(error) => {
                    let valid_end = offset + error.valid_up_to();
                    self.pending.push_str(
                        std::str::from_utf8(&self.pending_utf8[offset..valid_end])
                            .expect("UTF-8 valid prefix must decode"),
                    );
                    let invalid_start = valid_end;
                    let Some(error_len) = error.error_len() else {
                        if final_chunk {
                            self.pending.push_str(&String::from_utf8_lossy(
                                &self.pending_utf8[invalid_start..],
                            ));
                            self.pending_utf8.clear();
                        } else {
                            self.pending_utf8 = self.pending_utf8[invalid_start..].to_vec();
                        }
                        break;
                    };
                    self.pending.push('\u{FFFD}');
                    offset = invalid_start + error_len;
                    if offset == self.pending_utf8.len() {
                        self.pending_utf8.clear();
                        break;
                    }
                }
            }
        }
    }

    fn take_lines(&mut self, final_chunk: bool) -> Vec<StreamEvent> {
        let mut events = Vec::new();
        loop {
            let Some(index) = self.pending.find(['\n', '\r']) else {
                break;
            };
            let line = self.pending[..index].to_string();
            self.pending.drain(..=index);
            self.emit_line(line, &mut events);
        }
        if final_chunk && !self.pending.is_empty() {
            let line = std::mem::take(&mut self.pending);
            self.emit_line(line, &mut events);
        }
        events
    }

    fn emit_line(&mut self, line: String, events: &mut Vec<StreamEvent>) {
        let line = line.trim().to_string();
        if line.is_empty() || self.last_line.as_deref() == Some(line.as_str()) {
            return;
        }
        self.last_line = Some(line.clone());
        if self.recent_output.len() == RECENT_OUTPUT_LINES {
            self.recent_output.pop_front();
        }
        self.recent_output.push_back(line.clone());
        events.push(StreamEvent::Log(line));
    }

    pub(crate) fn request_cancel(&mut self) {
        self.cancelled = true;
    }

    pub(crate) fn cancellation_requested(&self) -> bool {
        self.cancelled
    }

    pub(crate) fn observe_network(&mut self, now: u64, rx_bytes: u64, total_bytes: u64) {
        self.total_bytes = total_bytes;
        if rx_bytes > self.last_rx {
            self.last_rx = rx_bytes;
            self.last_rx_activity = now;
        }
    }

    pub(crate) fn timeout_error(
        &mut self,
        now: u64,
        io_timeout: u64,
        net_timeout: u64,
        absolute_timeout: Option<u64>,
    ) -> Option<String> {
        if let Some(limit) = absolute_timeout {
            if now.saturating_sub(self.started_at) > limit {
                return Some(format!(
                    "Command exceeded absolute timeout of {limit} seconds"
                ));
            }
        }
        if now.saturating_sub(self.last_activity) > io_timeout {
            return Some(format!(
                "Command timed out after {io_timeout} seconds with no output"
            ));
        }
        if self.total_bytes > 0 && now.saturating_sub(self.last_rx_activity) > net_timeout {
            return Some(format!(
                "Command timed out after {net_timeout} seconds with no network progress"
            ));
        }
        None
    }

    pub(crate) fn finish_status(&self, exit_code: i32) -> Result<(), String> {
        if self.cancelled {
            return Err(
                "Installation cancelled by user. Disk changes may have already started."
                    .to_string(),
            );
        }
        if exit_code == 0 {
            return Ok(());
        }
        let start = self
            .recent_output
            .len()
            .saturating_sub(FAILURE_OUTPUT_LINES);
        let detail = self
            .recent_output
            .iter()
            .skip(start)
            .cloned()
            .collect::<Vec<_>>()
            .join("\n");
        let detail = if detail.is_empty() {
            "No command output was captured."
        } else {
            &detail
        };
        Err(format!("Command failed (exit {exit_code}):\n\n{detail}"))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::Value;

    #[test]
    fn timeout_still_applies_after_child_closes_stdout() {
        let mut command = Command::new("/bin/sh");
        command.args(["-c", "exec 1>&-; exec sleep 2"]);
        let started = Instant::now();
        let error =
            run_command_timeout(&mut command, || false, Duration::from_millis(150)).unwrap_err();
        assert!(error.contains("timed out"));
        assert!(started.elapsed() < Duration::from_secs(1));
    }

    #[test]
    fn installer_log_is_private_bounded_and_does_not_follow_symlinks() {
        let directory = tempfile::tempdir().expect("temporary log directory");
        let path = directory.path().join("installer.log");
        append_installer_log_at(&path, "first line");
        assert_eq!(std::fs::read_to_string(&path).unwrap(), "first line\n");
        assert_eq!(
            std::fs::metadata(&path).unwrap().permissions().mode() & 0o777,
            0o600
        );
        append_installer_log_at(&path, &"x".repeat(MAX_INSTALLER_LOG_BYTES as usize));
        assert_eq!(
            std::fs::metadata(&path).unwrap().len(),
            MAX_INSTALLER_LOG_BYTES
        );

        let target = directory.path().join("target");
        std::fs::write(&target, "preserve").unwrap();
        let link = directory.path().join("link");
        std::os::unix::fs::symlink(&target, &link).unwrap();
        append_installer_log_at(&link, "do not follow");
        assert_eq!(std::fs::read_to_string(&target).unwrap(), "preserve");
    }

    #[test]
    fn frames_lines_handles_crlf_and_suppresses_duplicates() {
        let mut model = StreamingCommandModel::new(10, 0);
        assert_eq!(
            model.feed(b"first\r\nfirst\nsecond", 11),
            vec![StreamEvent::Log("first".to_string())]
        );
        assert_eq!(
            model.finish_output(),
            vec![StreamEvent::Log("second".to_string())]
        );
    }

    fn decode_hex(value: &str) -> Vec<u8> {
        (0..value.len())
            .step_by(2)
            .map(|index| u8::from_str_radix(&value[index..index + 2], 16).expect("valid hex"))
            .collect()
    }

    fn event_lines(events: Vec<StreamEvent>) -> Vec<String> {
        events
            .into_iter()
            .map(|event| match event {
                StreamEvent::Log(line) => line,
            })
            .collect()
    }

    #[test]
    fn shared_stream_fixture_matches_framing_and_failure_tail_contract() {
        let cases: Vec<Value> = serde_json::from_str(include_str!("../testdata/stream_cases.json"))
            .expect("stream parity fixture must be valid JSON");
        for case in cases {
            let name = case["name"].as_str().expect("fixture case needs a name");
            let mut model = StreamingCommandModel::new(0, 0);
            let mut feed_events = Vec::new();
            for chunk in case["chunks_hex"].as_array().expect("chunks are an array") {
                feed_events
                    .extend(model.feed(&decode_hex(chunk.as_str().expect("chunk is hex")), 1));
            }
            assert_eq!(
                event_lines(feed_events),
                serde_json::from_value::<Vec<String>>(case["expected_feed"].clone()).unwrap(),
                "{name}: feed events"
            );
            assert_eq!(
                event_lines(model.finish_output()),
                serde_json::from_value::<Vec<String>>(case["expected_finish"].clone()).unwrap(),
                "{name}: final events"
            );
            if let Some(expected) = case.get("expected_error_contains") {
                let error = model
                    .finish_status(case["exit_code"].as_i64().unwrap() as i32)
                    .expect_err("fixture failure must return an error");
                for needle in expected.as_array().unwrap() {
                    assert!(error.contains(needle.as_str().unwrap()), "{name}: {error}");
                }
                for needle in case["expected_error_excludes"].as_array().unwrap() {
                    assert!(!error.contains(needle.as_str().unwrap()), "{name}: {error}");
                }
            } else {
                assert!(
                    model
                        .finish_status(case["exit_code"].as_i64().unwrap() as i32)
                        .is_ok(),
                    "{name}"
                );
            }
        }
    }

    #[test]
    fn preserves_split_utf8_and_replaces_invalid_bytes_at_eof() {
        let mut model = StreamingCommandModel::new(0, 0);
        assert_eq!(
            model.feed("café\n".as_bytes(), 1),
            vec![StreamEvent::Log("café".to_string())]
        );

        let mut model = StreamingCommandModel::new(0, 0);
        assert_eq!(model.feed(b"caf\xc3", 1), Vec::<StreamEvent>::new());
        assert_eq!(
            model.feed(b"\xa9\n", 2),
            vec![StreamEvent::Log("café".to_string())]
        );
        assert_eq!(model.feed(b"bad\xff", 3), Vec::<StreamEvent>::new());
        assert_eq!(
            model.finish_output(),
            vec![StreamEvent::Log("bad�".to_string())]
        );
    }

    #[test]
    fn keeps_recent_output_bounded_and_reports_only_the_tail() {
        let mut model = StreamingCommandModel::new(0, 0);
        for index in 0..35 {
            let line = format!("line-{index}\n");
            model.feed(line.as_bytes(), index);
        }
        let error = model.finish_status(1).expect_err("nonzero exit must fail");
        assert!(!error.contains("line-24"));
        assert!(error.contains("line-25"));
        assert!(error.contains("line-34"));
    }

    #[test]
    fn cancellation_is_cooperative_and_wins_over_exit_status() {
        let mut model = StreamingCommandModel::new(0, 0);
        model.request_cancel();
        assert!(model.cancellation_requested());
        assert!(model.finish_status(0).is_err());
    }

    #[test]
    fn separates_io_network_and_absolute_timeout_clocks() {
        let mut model = StreamingCommandModel::new(100, 10);
        assert_eq!(model.timeout_error(105, 5, 5, Some(50)), None);
        model.observe_network(105, 20, 100);
        assert!(model
            .timeout_error(111, 20, 5, Some(50))
            .unwrap()
            .contains("network"));
        assert!(model
            .timeout_error(151, 100, 100, Some(50))
            .unwrap()
            .contains("absolute"));
        model.feed(b"progress\n", 200);
        assert!(model
            .timeout_error(221, 20, 100, Some(200))
            .unwrap()
            .contains("output"));
    }
}
