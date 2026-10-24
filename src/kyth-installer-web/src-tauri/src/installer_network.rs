use std::collections::BTreeMap;

use serde::{Deserialize, Serialize};

pub(crate) const NMCLI_PATH: &str = "/usr/bin/nmcli";
pub(crate) const KONSOLE_PATH: &str = "/usr/bin/konsole";
pub(crate) const SCAN_ARGS: &[&str] = &[
    "--terse",
    "--escape",
    "yes",
    "--fields",
    "IN-USE,SSID,SECURITY,SIGNAL,BSSID,DEVICE",
    "--wait",
    "20",
    "device",
    "wifi",
    "list",
    "--rescan",
    "no",
];

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub(crate) struct WifiNetwork {
    pub(crate) ssid: String,
    pub(crate) security: String,
    pub(crate) signal: u8,
    pub(crate) in_use: bool,
    pub(crate) bssid: String,
    pub(crate) device: String,
}

#[derive(Debug, Clone, Serialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub(crate) enum WifiScanStatus {
    Ready,
    Empty,
    NoAdapter,
    RadioDisabled,
    Unavailable,
}

#[derive(Debug, Clone, Serialize, PartialEq, Eq)]
pub(crate) struct WifiScanResult {
    pub(crate) status: WifiScanStatus,
    pub(crate) networks: Vec<WifiNetwork>,
    pub(crate) detail: String,
}

trait Executor {
    fn freshness_timeout(&self) -> std::time::Duration {
        std::time::Duration::from_secs(20)
    }
    fn run(
        &mut self,
        program: &str,
        args: &[&str],
        timeout: std::time::Duration,
    ) -> Result<String, String>;
    fn launch(&mut self, program: &str, args: &[String]) -> Result<(), String>;
}

const DEVICE_ARGS: &[&str] = &[
    "--terse",
    "--escape",
    "yes",
    "--fields",
    "DEVICE,TYPE,STATE",
    "device",
    "status",
];
const RADIO_ARGS: &[&str] = &["--terse", "--fields", "WIFI-HW,WIFI", "radio", "all"];
const QUERY_TIMEOUT: std::time::Duration = std::time::Duration::from_secs(5);
const RESCAN_TIMEOUT: std::time::Duration = std::time::Duration::from_secs(25);

fn nonblocking(pipe: &impl std::os::fd::AsRawFd) -> Result<(), String> {
    let fd = pipe.as_raw_fd();
    // SAFETY: fd belongs to a live owned child pipe; flags do not change ownership.
    let flags = unsafe { libc::fcntl(fd, libc::F_GETFL) };
    if flags < 0 || unsafe { libc::fcntl(fd, libc::F_SETFL, flags | libc::O_NONBLOCK) } < 0 {
        return Err(format!(
            "Could not configure command pipe: {}",
            std::io::Error::last_os_error()
        ));
    }
    Ok(())
}

fn drain_pipe(pipe: &mut impl std::io::Read, bytes: &mut Vec<u8>) -> Result<bool, String> {
    let mut chunk = [0; 8192];
    loop {
        match pipe.read(&mut chunk) {
            Ok(0) => return Ok(true),
            Ok(count) => {
                if bytes.len() + count > 1024 * 1024 {
                    return Err("Wi-Fi command output exceeded 1 MiB.".into());
                }
                bytes.extend_from_slice(&chunk[..count]);
            }
            Err(e) if e.kind() == std::io::ErrorKind::WouldBlock => return Ok(false),
            Err(e) if e.kind() == std::io::ErrorKind::Interrupted => continue,
            Err(e) => return Err(format!("Could not read Wi-Fi command output: {e}")),
        }
    }
}

pub(crate) fn scan_wifi() -> Result<WifiScanResult, String> {
    scan_with(&mut SystemExecutor)
}

pub(crate) fn connect_wifi(selected: &WifiNetwork) -> Result<(), String> {
    connect_with(&mut SystemExecutor, selected)
}

struct SystemExecutor;
impl Executor for SystemExecutor {
    fn run(
        &mut self,
        program: &str,
        args: &[&str],
        timeout: std::time::Duration,
    ) -> Result<String, String> {
        use std::os::unix::process::CommandExt;
        use std::process::{Command, Stdio};
        use std::time::{Duration, Instant};
        let started = Instant::now();
        let mut child = Command::new(program)
            .args(args)
            .env("LC_ALL", "C")
            .stdin(Stdio::null())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .process_group(0)
            .spawn()
            .map_err(|e| format!("Could not start {program}: {e}"))?;
        let result = (|| {
            let mut stdout = child.stdout.take().ok_or("Missing command stdout")?;
            let mut stderr = child.stderr.take().ok_or("Missing command stderr")?;
            nonblocking(&stdout)?;
            nonblocking(&stderr)?;
            let (mut out, mut err) = (Vec::new(), Vec::new());
            let (mut out_eof, mut err_eof) = (false, false);
            loop {
                out_eof |= drain_pipe(&mut stdout, &mut out)?;
                err_eof |= drain_pipe(&mut stderr, &mut err)?;
                if let Some(status) = child
                    .try_wait()
                    .map_err(|e| format!("Could not poll {program}: {e}"))?
                {
                    if out_eof && err_eof {
                        if !status.success() {
                            return Err(format!(
                                "{program} failed ({status}): {}",
                                String::from_utf8_lossy(&err).trim()
                            ));
                        }
                        return String::from_utf8(out)
                            .map_err(|_| format!("{program} returned invalid text"));
                    }
                }
                if started.elapsed() >= timeout {
                    return Err(format!(
                        "{program} timed out after {} ms",
                        timeout.as_millis()
                    ));
                }
                std::thread::sleep(
                    Duration::from_millis(10).min(timeout.saturating_sub(started.elapsed())),
                );
            }
        })();
        if result.is_err() {
            // Every capture runs in its own group. Kill descendants too: an
            // inherited pipe must not turn output collection into an unbounded wait.
            // SAFETY: this group was created by process_group(0) for this child.
            unsafe {
                libc::kill(-(child.id() as i32), libc::SIGKILL);
            }
            let _ = child.kill();
            let cleanup = Instant::now();
            while matches!(child.try_wait(), Ok(None))
                && cleanup.elapsed() < Duration::from_millis(250)
            {
                std::thread::sleep(Duration::from_millis(5));
            }
        }
        result
    }
    fn launch(&mut self, program: &str, args: &[String]) -> Result<(), String> {
        std::process::Command::new(program)
            .args(args)
            .spawn()
            .map(|_| ())
            .map_err(|e| format!("Could not open the Wi-Fi connection terminal: {e}"))
    }
}

fn scan_state(status: WifiScanStatus, detail: impl Into<String>) -> WifiScanResult {
    WifiScanResult {
        status,
        networks: vec![],
        detail: detail.into(),
    }
}

fn scan_with(executor: &mut impl Executor) -> Result<WifiScanResult, String> {
    use WifiScanStatus::*;
    let devices = match executor.run(NMCLI_PATH, DEVICE_ARGS, QUERY_TIMEOUT) {
        Ok(output) => output,
        Err(error) => return Ok(scan_state(Unavailable, error)),
    };
    let adapters: Vec<_> = devices
        .lines()
        .map(split_nmcli_fields)
        .filter(|f| f.len() == 3 && f[1] == "wifi")
        .collect();
    if adapters.is_empty() {
        return Ok(scan_state(NoAdapter, "No Wi-Fi adapter was found."));
    }
    let radio = match executor.run(NMCLI_PATH, RADIO_ARGS, QUERY_TIMEOUT) {
        Ok(output) => output,
        Err(error) => return Ok(scan_state(Unavailable, error)),
    };
    let radio = split_nmcli_fields(radio.trim());
    if radio.len() == 2 && radio.iter().any(|state| state == "disabled") {
        return Ok(scan_state(
            RadioDisabled,
            "Wi-Fi radio is disabled. Enable Wi-Fi and scan again.",
        ));
    }
    if radio != ["enabled", "enabled"] {
        return Ok(scan_state(
            Unavailable,
            "Could not determine Wi-Fi radio state.",
        ));
    }
    let usable: Vec<_> = adapters
        .iter()
        .filter(|f| {
            valid_device(&f[0])
                && (f[2] == "disconnected"
                    || f[2].starts_with("connected")
                    || f[2].starts_with("connecting"))
        })
        .map(|f| f[0].as_str())
        .collect();
    if usable.is_empty() || usable.len() > 8 {
        return Ok(scan_state(
            Unavailable,
            "Wi-Fi adapters are unavailable or unmanaged.",
        ));
    }
    for device in &usable {
        if let Err(error) = rescan_device(executor, device) {
            return Ok(scan_state(
                Unavailable,
                format!("Wi-Fi scan failed on {device}: {error}"),
            ));
        }
    }
    let output = match executor.run(NMCLI_PATH, SCAN_ARGS, QUERY_TIMEOUT) {
        Ok(output) => output,
        Err(error) => return Ok(scan_state(Unavailable, error)),
    };
    let networks: Vec<_> = parse_nmcli_wifi_list(&output)
        .into_iter()
        .filter(|n| usable.contains(&n.device.as_str()))
        .collect();
    Ok(WifiScanResult {
        status: if networks.is_empty() { Empty } else { Ready },
        detail: if networks.is_empty() {
            "Scan completed; NetworkManager reports no named Wi-Fi networks."
        } else {
            "Scan completed; showing NetworkManager's reported access points."
        }
        .into(),
        networks,
    })
}

const BUSCTL_PATH: &str = "/usr/bin/busctl";

fn last_scan(
    executor: &mut impl Executor,
    path: &str,
    timeout: std::time::Duration,
) -> Result<i64, String> {
    let output = executor.run(
        BUSCTL_PATH,
        &[
            "--system",
            "get-property",
            "org.freedesktop.NetworkManager",
            path,
            "org.freedesktop.NetworkManager.Device.Wireless",
            "LastScan",
        ],
        timeout,
    )?;
    let fields: Vec<_> = output.split_whitespace().collect();
    if fields.len() != 2 || fields[0] != "x" {
        return Err("Could not determine Wi-Fi scan completion (invalid LastScan).".into());
    }
    fields[1]
        .parse::<i64>()
        .ok()
        .filter(|v| *v >= -1)
        .ok_or_else(|| "Could not determine Wi-Fi scan completion (invalid LastScan).".into())
}

fn rescan_device(executor: &mut impl Executor, device: &str) -> Result<(), String> {
    use std::time::{Duration, Instant};
    let path = executor.run(
        NMCLI_PATH,
        &[
            "--get-values",
            "GENERAL.DBUS-PATH",
            "device",
            "show",
            device,
        ],
        QUERY_TIMEOUT,
    )?;
    let path = path.trim();
    let prefix = "/org/freedesktop/NetworkManager/Devices/";
    if !path.starts_with(prefix)
        || path.len() <= prefix.len()
        || path.len() > 256
        || !path[prefix.len()..]
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || b == b'_')
    {
        return Err("Could not determine Wi-Fi scan completion (invalid device path).".into());
    }
    let before = last_scan(executor, path, QUERY_TIMEOUT)?;
    // Unlike list --rescan yes, an explicit RequestScan exposes rejection.
    executor.run(
        NMCLI_PATH,
        &["--wait", "20", "device", "wifi", "rescan", "ifname", device],
        RESCAN_TIMEOUT,
    )?;
    // RequestScan success only means accepted. LastScan must advance before
    // reading the cache; no fixed sleep is treated as freshness evidence.
    let started = Instant::now();
    let deadline = executor.freshness_timeout();
    loop {
        let remaining = deadline.saturating_sub(started.elapsed());
        if remaining.is_zero() {
            return Err("Wi-Fi scan completion timed out; cached results were not used. Try scanning again.".into());
        }
        let after = last_scan(executor, path, QUERY_TIMEOUT.min(remaining))?;
        if after >= 0 && after > before {
            return Ok(());
        }
        std::thread::sleep(
            Duration::from_millis(100).min(deadline.saturating_sub(started.elapsed())),
        );
    }
}

fn connect_with(executor: &mut impl Executor, selected: &WifiNetwork) -> Result<(), String> {
    let args = connection_terminal_args(selected)?;
    let cached = executor.run(NMCLI_PATH, SCAN_ARGS, QUERY_TIMEOUT)?;
    if !parse_nmcli_wifi_list(&cached).iter().any(|n| {
        n.ssid == selected.ssid
            && n.security == selected.security
            && n.bssid.eq_ignore_ascii_case(&selected.bssid)
            && n.device == selected.device
    }) {
        return Err("The selected Wi-Fi access point disappeared or changed security. Scan again before connecting.".into());
    }
    executor.launch(KONSOLE_PATH, &args)
}

/// Parse the six requested terse fields without merging AP/device/security identity.
pub(crate) fn parse_nmcli_wifi_list(output: &str) -> Vec<WifiNetwork> {
    let mut by_identity = BTreeMap::new();

    for line in output.lines() {
        let fields = split_nmcli_fields(line);
        if fields.len() != 6 {
            continue;
        }
        let (in_use, ssid, security, signal) = (&fields[0], &fields[1], &fields[2], &fields[3]);
        if !valid_ssid(ssid) || !valid_bssid(&fields[4]) || !valid_device(&fields[5]) {
            continue;
        }
        let Ok(signal) = signal.parse::<u8>() else {
            continue;
        };
        if signal > 100 {
            continue;
        }

        let network = WifiNetwork {
            ssid: ssid.clone(),
            security: if security.is_empty() {
                "--".into()
            } else {
                security.clone()
            },
            signal,
            in_use: in_use == "*",
            bssid: fields[4].clone(),
            device: fields[5].clone(),
        };
        by_identity.insert(
            (
                network.ssid.clone(),
                network.security.clone(),
                network.bssid.clone(),
                network.device.clone(),
            ),
            network,
        );
    }

    let mut networks: Vec<_> = by_identity.into_values().collect();
    networks.sort_by(|left, right| {
        right
            .in_use
            .cmp(&left.in_use)
            .then_with(|| right.signal.cmp(&left.signal))
            .then_with(|| left.ssid.cmp(&right.ssid))
    });
    networks
}

fn split_nmcli_fields(line: &str) -> Vec<String> {
    let mut fields = Vec::new();
    let mut field = String::new();
    let mut chars = line.chars();

    while let Some(ch) = chars.next() {
        match ch {
            ':' => fields.push(std::mem::take(&mut field)),
            '\\' => match chars.next() {
                Some('\\') => field.push('\\'),
                Some(':') => field.push(':'),
                Some(other) => {
                    field.push('\\');
                    field.push(other);
                }
                None => field.push('\\'),
            },
            other => field.push(other),
        }
    }
    fields.push(field);
    fields
}

pub(crate) fn valid_ssid(ssid: &str) -> bool {
    !ssid.is_empty() && ssid.len() <= 32 && !ssid.chars().any(char::is_control)
}

fn valid_bssid(value: &str) -> bool {
    let octets: Vec<_> = value.split(':').collect();
    octets.len() == 6
        && octets
            .iter()
            .all(|part| part.len() == 2 && part.bytes().all(|b| b.is_ascii_hexdigit()))
        && u8::from_str_radix(octets[0], 16).is_ok_and(|b| b & 1 == 0)
        && octets.iter().any(|part| *part != "00")
}

fn valid_device(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 15
        && value.as_bytes()[0].is_ascii_alphanumeric()
        && value
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || matches!(b, b'_' | b'-' | b'.'))
}

/// Arguments for a terminal-backed nmcli flow. No shell is involved and no
/// passphrase is placed in argv; nmcli prompts in Konsole when needed.
pub(crate) fn connection_terminal_args(selected: &WifiNetwork) -> Result<Vec<String>, String> {
    let ssid = &selected.ssid;
    if !valid_ssid(ssid)
        || !valid_bssid(&selected.bssid)
        || !valid_device(&selected.device)
        || selected.security.is_empty()
        || selected.security.len() > 128
        || selected.security.chars().any(char::is_control)
        || selected.signal > 100
    {
        return Err("The selected Wi-Fi network has an invalid SSID.".to_string());
    }

    Ok([
        "--hold",
        "-e",
        NMCLI_PATH,
        "--ask",
        "device",
        "wifi",
        "connect",
        ssid.as_str(),
        "bssid",
        &selected.bssid,
        "ifname",
        &selected.device,
    ]
    .into_iter()
    .map(str::to_string)
    .collect())
}

#[cfg(test)]
mod tests {
    use super::*;
    fn selection(ssid: &str) -> WifiNetwork {
        WifiNetwork {
            ssid: ssid.into(),
            security: "--".into(),
            signal: 80,
            in_use: false,
            bssid: "02:00:00:00:00:01".into(),
            device: "wlan0".into(),
        }
    }

    #[test]
    fn parses_escaped_fields_and_empty_results() {
        assert!(parse_nmcli_wifi_list("").is_empty());
        let rows = parse_nmcli_wifi_list(
            "*:Secure\\\\Lab\\:Guest:WPA2:63:02\\:00\\:00\\:00\\:00\\:02:wlan0\n",
        );
        assert_eq!(rows.len(), 1);
        assert_eq!(rows[0].ssid, "Secure\\Lab:Guest");
        assert_eq!(rows[0].bssid, "02:00:00:00:00:02");
    }

    #[test]
    fn scan_reads_cached_wifi_with_stable_fields() {
        assert!(SCAN_ARGS
            .windows(3)
            .any(|args| args == ["device", "wifi", "list"]));
        assert!(SCAN_ARGS.windows(2).any(|args| args == ["--rescan", "no"]));
        assert!(SCAN_ARGS.windows(2).any(|args| args == ["--wait", "20"]));
    }

    #[test]
    fn connect_uses_the_working_ask_flow_without_a_shell_or_password_argument() {
        let args = connection_terminal_args(&selection("Guest Wi-Fi")).unwrap();
        assert_eq!(
            args,
            [
                "--hold",
                "-e",
                NMCLI_PATH,
                "--ask",
                "device",
                "wifi",
                "connect",
                "Guest Wi-Fi",
                "bssid",
                "02:00:00:00:00:01",
                "ifname",
                "wlan0",
            ]
        );
        assert!(!args
            .iter()
            .any(|arg| arg == "password" || arg == "sh" || arg == "-c"));
    }

    #[test]
    fn connection_arguments_preserve_ssids_as_single_literal_arguments() {
        let ssid = "Guest; printf not-a-shell";
        let args = connection_terminal_args(&selection(ssid)).unwrap();
        assert_eq!(args[7], ssid);
    }

    #[test]
    fn invalid_ssids_are_rejected_before_launch() {
        assert!(connection_terminal_args(&selection("")).is_err());
        assert!(connection_terminal_args(&selection("bad\nssid")).is_err());
        assert!(connection_terminal_args(&selection(&"x".repeat(33))).is_err());
    }
}

#[cfg(test)]
mod regression_open {
    #[test]
    fn literal_double_dash_ssid_is_not_a_hidden_network_placeholder() {
        let rows = parse_nmcli_wifi_list(" :--::39:02\\:00\\:00\\:00\\:00\\:09:wlan0\n");
        assert_eq!(rows.len(), 1);
        assert_eq!(connection_terminal_args(&rows[0]).unwrap()[7], "--");
    }

    #[test]
    fn shared_ssid_preserves_security_ap_device_and_connected_identity() {
        let rows = parse_nmcli_wifi_list(concat!(
            "*:Shared:WPA2:50:02\\:00\\:00\\:00\\:00\\:01:wlan0\n",
            " :Shared::95:02\\:00\\:00\\:00\\:00\\:02:wlan0\n",
            " :Shared:WPA3:90:02\\:00\\:00\\:00\\:00\\:03:wlan0\n",
            " :Shared:WPA2:60:02\\:00\\:00\\:00\\:00\\:01:wlan1\n",
        ));
        assert_eq!(rows.len(), 4);
        assert_eq!(
            (&rows[0].security, rows[0].signal, &rows[0].device),
            (&"WPA2".into(), 50, &"wlan0".into())
        );
        assert_eq!(rows.iter().filter(|r| r.in_use).count(), 1);
    }

    #[test]
    fn rejects_malformed_identity_and_signal_rows() {
        for (bssid, device) in [
            ("", "wlan0"),
            ("garbage", "wlan0"),
            ("00:00:00:00:00:00", "wlan0"),
            ("ff:ff:ff:ff:ff:ff", "wlan0"),
            ("03:00:00:00:00:01", "wlan0"),
            ("02:00:00:00:00:01", ""),
            ("02:00:00:00:00:01", "../wlan0"),
            ("02:00:00:00:00:01", "--help"),
            ("02:00:00:00:00:01", "wlan 0"),
        ] {
            let row = format!(" :Guest::80:{}:{}\n", bssid.replace(':', "\\:"), device);
            assert!(
                parse_nmcli_wifi_list(&row).is_empty(),
                "accepted {bssid} {device}"
            );
        }
        for signal in ["--", "101", "-1"] {
            assert!(parse_nmcli_wifi_list(&format!(
                " :Guest::{signal}:02\\:00\\:00\\:00\\:00\\:01:wlan0\n"
            ))
            .is_empty());
        }
    }

    use super::*;
    #[test]
    fn actual_empty_security_open_row_survives() {
        let rows = parse_nmcli_wifi_list(" :Open\\:Guest::80:02\\:00\\:00\\:00\\:00\\:01:wlan0\n");
        assert_eq!(rows.len(), 1, "real open network must not disappear");
        assert_eq!(rows[0].security, "--");
    }
}

#[cfg(test)]
mod scan_tests {
    struct FreshnessFake {
        scans: usize,
        advance: bool,
        listed: bool,
    }
    impl Executor for FreshnessFake {
        fn freshness_timeout(&self) -> Duration {
            Duration::from_millis(30)
        }
        fn run(&mut self, program: &str, args: &[&str], _: Duration) -> Result<String, String> {
            if program == "/usr/bin/busctl" {
                self.scans += 1;
                return Ok(format!(
                    "x {}\n",
                    if self.advance && self.scans >= 2 {
                        11
                    } else {
                        10
                    }
                ));
            }
            if args.contains(&"GENERAL.DBUS-PATH") {
                return Ok("/org/freedesktop/NetworkManager/Devices/1\n".into());
            }
            if args.contains(&"status") {
                return Ok(DEVICES.into());
            }
            if args.contains(&"all") {
                return Ok("enabled:enabled\n".into());
            }
            if args.contains(&"rescan") {
                return Ok("".into());
            }
            if args.contains(&"list") {
                self.listed = true;
                return Ok(OPEN.into());
            }
            panic!("unexpected command {program} {args:?}")
        }
        fn launch(&mut self, _: &str, _: &[String]) -> Result<(), String> {
            panic!("not connecting")
        }
    }
    #[test]
    fn accepted_scan_without_lastscan_advance_is_unavailable_not_fresh_empty() {
        let mut exec = FreshnessFake {
            scans: 0,
            advance: false,
            listed: false,
        };
        let result = scan_with(&mut exec).unwrap();
        assert_eq!(result.status, WifiScanStatus::Unavailable);
        assert!(result.detail.contains("completion"));
        assert!(!exec.listed, "unchanged cache must not be shown as fresh");
    }
    #[test]
    fn list_is_read_only_after_lastscan_actually_advances() {
        let mut exec = FreshnessFake {
            scans: 0,
            advance: true,
            listed: false,
        };
        let result = scan_with(&mut exec).unwrap();
        assert_eq!(result.status, WifiScanStatus::Ready);
        assert!(exec.scans >= 2 && exec.listed);
    }

    #[test]
    fn process_runner_captures_output_and_reports_stderr_failure() {
        let mut exec = SystemExecutor;
        assert_eq!(
            exec.run(
                "/usr/bin/printf",
                &["actual-output"],
                Duration::from_secs(1)
            )
            .unwrap(),
            "actual-output"
        );
        let error = exec
            .run(
                "/usr/bin/python3",
                &[
                    "-c",
                    "import sys; print('real failure', file=sys.stderr); sys.exit(3)",
                ],
                Duration::from_secs(1),
            )
            .unwrap_err();
        assert!(error.contains("real failure"));
    }
    #[test]
    fn process_runner_times_out_real_sleep_and_inherited_pipes() {
        for (program, args) in [
            ("/usr/bin/sleep", vec!["2"]),
            (
                "/usr/bin/python3",
                vec![
                    "-c",
                    "import os,time; pid=os.fork(); time.sleep(2) if pid == 0 else None",
                ],
            ),
        ] {
            let started = std::time::Instant::now();
            let error = SystemExecutor
                .run(program, &args, Duration::from_millis(80))
                .unwrap_err();
            assert!(error.contains("timed out"), "{error}");
            assert!(started.elapsed() < Duration::from_millis(600));
        }
    }

    use super::*;
    use std::collections::VecDeque;
    use std::time::Duration;

    #[derive(Default)]
    struct Fake {
        replies: VecDeque<Result<String, String>>,
        calls: Vec<Vec<String>>,
        launches: Vec<Vec<String>>,
        last_scans: usize,
    }
    impl Fake {
        fn new(replies: &[Result<&str, &str>]) -> Self {
            Self {
                replies: replies
                    .iter()
                    .map(|r| r.map(str::to_string).map_err(str::to_string))
                    .collect(),
                ..Self::default()
            }
        }
    }
    impl Executor for Fake {
        fn run(
            &mut self,
            program: &str,
            args: &[&str],
            timeout: Duration,
        ) -> Result<String, String> {
            assert!(program == NMCLI_PATH || program == BUSCTL_PATH);
            assert!(timeout > Duration::ZERO && timeout <= Duration::from_secs(25));
            self.calls
                .push(args.iter().map(|s| s.to_string()).collect());
            if args.contains(&"GENERAL.DBUS-PATH") {
                return Ok("/org/freedesktop/NetworkManager/Devices/1\n".into());
            }
            if program == BUSCTL_PATH {
                self.last_scans += 1;
                return Ok(format!("x {}\n", self.last_scans));
            }
            self.replies.pop_front().expect("unexpected subprocess")
        }
        fn launch(&mut self, program: &str, args: &[String]) -> Result<(), String> {
            assert_eq!(program, KONSOLE_PATH);
            self.launches.push(args.to_vec());
            Ok(())
        }
    }
    #[test]
    fn connection_is_pinned_to_selected_ap_and_device_after_cache_recheck() {
        let selected = parse_nmcli_wifi_list(OPEN).remove(0);
        let mut fake = Fake::new(&[Ok(OPEN)]);
        connect_with(&mut fake, &selected).unwrap();
        assert_eq!(fake.calls.len(), 1);
        assert!(fake.calls[0].windows(2).any(|a| a == ["--rescan", "no"]));
        assert_eq!(
            fake.launches,
            vec![vec![
                "--hold",
                "-e",
                NMCLI_PATH,
                "--ask",
                "device",
                "wifi",
                "connect",
                "Open:Guest",
                "bssid",
                "02:00:00:00:00:01",
                "ifname",
                "wlan0"
            ]]
        );
    }
    #[test]
    fn stale_or_security_changed_selection_never_launches_a_terminal() {
        for cached in [
            "".to_string(),
            OPEN.replace("::80:", ":WPA2:80:"),
            OPEN.replace("wlan0", "wlan1"),
            OPEN.replace("00\\:01", "00\\:02"),
        ] {
            let selected = parse_nmcli_wifi_list(OPEN).remove(0);
            let mut fake = Fake::new(&[Ok(&cached)]);
            assert!(connect_with(&mut fake, &selected).is_err());
            assert!(fake.launches.is_empty());
        }
    }
    #[test]
    fn invalid_selection_is_rejected_before_any_subprocess() {
        let selected = parse_nmcli_wifi_list(OPEN).remove(0);
        for (bssid, device) in [
            ("bad", "wlan0"),
            ("02:00:00:00:00:01", "../wlan0"),
            ("02:00:00:00:00:01", "--help"),
        ] {
            let mut changed = selected.clone();
            changed.bssid = bssid.into();
            changed.device = device.into();
            let mut fake = Fake::default();
            assert!(connect_with(&mut fake, &changed).is_err());
            assert!(fake.calls.is_empty() && fake.launches.is_empty());
        }
    }
    const DEVICES: &str = "eth0:ethernet:connected\nwlan0:wifi:disconnected\n";
    const OPEN: &str = " :Open\\:Guest::80:02\\:00\\:00\\:00\\:00\\:01:wlan0\n";

    #[test]
    fn ready_scan_explicitly_rescans_then_reads_cached_six_fields() {
        let mut fake = Fake::new(&[Ok(DEVICES), Ok("enabled:enabled\n"), Ok(""), Ok(OPEN)]);
        let result = scan_with(&mut fake).unwrap();
        assert_eq!(result.status, WifiScanStatus::Ready);
        assert_eq!(result.networks[0].security, "--");
        assert!(fake
            .calls
            .iter()
            .any(|args| args == &["--wait", "20", "device", "wifi", "rescan", "ifname", "wlan0"]));
        assert!(fake
            .calls
            .last()
            .unwrap()
            .windows(2)
            .any(|a| a == ["--rescan", "no"]));
        assert!(fake
            .calls
            .last()
            .unwrap()
            .iter()
            .any(|a| a == "IN-USE,SSID,SECURITY,SIGNAL,BSSID,DEVICE"));
    }
    #[test]
    fn no_adapter_radio_disabled_and_unavailable_are_explicit() {
        for (replies, expected) in [
            (
                vec![Ok("eth0:ethernet:connected\n")],
                WifiScanStatus::NoAdapter,
            ),
            (
                vec![Ok(DEVICES), Ok("enabled:disabled\n")],
                WifiScanStatus::RadioDisabled,
            ),
            (
                vec![Ok("wlan0:wifi:unavailable\n"), Ok("enabled:enabled\n")],
                WifiScanStatus::Unavailable,
            ),
            (
                vec![Err("NetworkManager unavailable")],
                WifiScanStatus::Unavailable,
            ),
        ] {
            let mut fake = Fake::new(&replies);
            let result = scan_with(&mut fake).unwrap();
            assert_eq!(result.status, expected);
            assert!(result.networks.is_empty());
            assert!(!result.detail.is_empty());
            assert!(fake.replies.is_empty());
        }
    }
    #[test]
    fn empty_success_has_an_explicit_empty_status() {
        let mut fake = Fake::new(&[Ok(DEVICES), Ok("enabled:enabled\n"), Ok(""), Ok("")]);
        assert_eq!(scan_with(&mut fake).unwrap().status, WifiScanStatus::Empty);
    }
    #[test]
    fn scan_failure_and_timeout_never_return_cached_success() {
        for error in ["Scanning not allowed", "Wi-Fi rescan timed out"] {
            let mut fake = Fake::new(&[Ok(DEVICES), Ok("enabled:enabled\n"), Err(error), Ok(OPEN)]);
            let result = scan_with(&mut fake).unwrap();
            assert_eq!(result.status, WifiScanStatus::Unavailable);
            assert!(result.networks.is_empty());
            assert!(result.detail.contains(error));
            assert!(
                !fake.calls.iter().any(|args| args.contains(&"list".into())),
                "must not read cached APs after rejected rescan"
            );
        }
    }
}
