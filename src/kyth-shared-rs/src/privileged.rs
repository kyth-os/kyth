//! Root-owned, fixed-operation boundary for Hub mutations.
//!
//! The wire protocol is one JSON request per line and one JSON response per
//! line. Requests are validated into fixed executable/argument shapes before
//! anything is spawned; there is deliberately no command or argv field.

use std::fs::{self, OpenOptions};
use std::io::{self, BufRead, BufReader, Read, Write};
use std::os::fd::AsRawFd;
use std::os::unix::fs::{FileTypeExt, PermissionsExt};
use std::os::unix::net::{UnixListener, UnixStream};
use std::process::{Command, Stdio};
use std::sync::OnceLock;
use std::thread;
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

use regex::Regex;
use serde_json::{json, Map, Value};

const SOCKET: &str = "/run/kyth/privileged.sock";
/// Largest single request line the root daemon will read: without a cap
/// one line can OOM it. Legitimate requests are small JSON objects.
const MAX_REQUEST_LINE_BYTES: u64 = 128 * 1024;
/// Cap on concurrent client threads: the accept loop spawns one thread
/// per connection, so an uncapped wheel member could exhaust threads.
const MAX_CLIENTS: usize = 32;
const AUDIT_LOG: &str = "/var/log/kyth/privileged.log";
const MAX_SHARE_PAYLOAD: usize = 64 * 1024;
const OPERATION_TIMEOUT: Duration = Duration::from_secs(900);

#[derive(Debug)]
struct ExecSpec {
    argv: Vec<String>,
    stdin: Option<Vec<u8>>,
}

fn text<'a>(request: &'a Value, field: &str) -> &'a str {
    request.get(field).and_then(Value::as_str).unwrap_or("")
}

fn share_text<'a>(
    payload: &'a Map<String, Value>,
    field: &str,
    allow_empty: bool,
    maximum: usize,
) -> Result<&'a str, String> {
    let value = payload
        .get(field)
        .and_then(Value::as_str)
        .ok_or_else(|| format!("{field} must be text"))?;
    if (!allow_empty && value.is_empty())
        || value.chars().count() > maximum
        || value
            .chars()
            .any(|character| character.is_control() || character == '\u{7f}')
    {
        return Err(format!("invalid {field}"));
    }
    Ok(value)
}

fn normalize_mount_point(value: &str) -> String {
    let mut parts = Vec::new();
    for part in value.split('/') {
        match part {
            "" | "." => {}
            ".." => {
                parts.pop();
            }
            part => parts.push(part),
        }
    }
    if parts.is_empty() {
        "/".to_string()
    } else {
        format!("/{}", parts.join("/"))
    }
}

static MOUNT_PATH_RE: OnceLock<Regex> = OnceLock::new();
static SHARE_NAME_RE: OnceLock<Regex> = OnceLock::new();
static SHARE_HOST_RE: OnceLock<Regex> = OnceLock::new();
static FLATPAK_ID_RE: OnceLock<Regex> = OnceLock::new();

fn mount_path_re() -> &'static Regex {
    MOUNT_PATH_RE.get_or_init(|| Regex::new(r"^[A-Za-z0-9._/ -]+$").expect("mount path regex"))
}

fn share_name_re() -> &'static Regex {
    SHARE_NAME_RE.get_or_init(|| Regex::new(r"^[A-Za-z0-9_-]{1,64}$").expect("share name regex"))
}

fn share_host_re() -> &'static Regex {
    SHARE_HOST_RE.get_or_init(|| Regex::new(r"^[A-Za-z0-9._:-]{1,253}$").expect("share host regex"))
}

fn flatpak_id_re() -> &'static Regex {
    FLATPAK_ID_RE.get_or_init(|| {
        Regex::new(r"^[A-Za-z0-9]+(?:[.-][A-Za-z0-9_]+)+$").expect("Flatpak id regex")
    })
}

fn share_mount_point(payload: &Map<String, Value>) -> Result<String, String> {
    let value = share_text(payload, "mount_point", false, 4096)?;
    let mount_point = normalize_mount_point(value);
    if !mount_path_re().is_match(&mount_point)
        || mount_point.contains("//")
        || !["/mnt/", "/media/", "/run/media/", "/home/"]
            .iter()
            .any(|prefix| mount_point.starts_with(prefix))
    {
        return Err("invalid mount_point".to_string());
    }
    Ok(mount_point)
}

fn network_share_stdin(
    request: &Value,
    operation: &str,
    uid: u32,
    gid: u32,
) -> Result<Vec<u8>, String> {
    let payload = request
        .get("payload")
        .and_then(Value::as_object)
        .ok_or_else(|| "network share payload must be an object".to_string())?;
    if serde_json::to_vec(payload)
        .map_err(|_| "network share payload is invalid".to_string())?
        .len()
        > MAX_SHARE_PAYLOAD
    {
        return Err("network share payload is too large".to_string());
    }
    let name = share_text(payload, "name", false, 64)?;
    if !share_name_re().is_match(name) {
        return Err("invalid share name".to_string());
    }
    let mount_point = share_mount_point(payload)?;
    let mut output = Map::new();
    output.insert("name".into(), Value::String(name.into()));
    output.insert("mount_point".into(), Value::String(mount_point));
    if operation == "network_share_add" {
        let server = share_text(payload, "server", false, 253)?;
        if !share_host_re().is_match(server) {
            return Err("invalid share server".to_string());
        }
        let share_path = share_text(payload, "share_path", false, 4096)?.trim_start_matches('/');
        if share_path.is_empty()
            || share_path.starts_with('.')
            || share_path.contains("//")
            || share_path.contains('%')
            || share_path.split('/').any(|part| part == "..")
        {
            return Err("invalid share_path".to_string());
        }
        let username = share_text(payload, "username", false, 256)?;
        let password = share_text(payload, "password", true, 4096)?;
        let domain = share_text(payload, "domain", true, 256)?;
        output.insert("server".into(), Value::String(server.into()));
        output.insert("share_path".into(), Value::String(share_path.into()));
        output.insert("username".into(), Value::String(username.into()));
        output.insert("password".into(), Value::String(password.into()));
        output.insert("domain".into(), Value::String(domain.into()));
        output.insert(
            "auto_mount".into(),
            json!(payload
                .get("auto_mount")
                .and_then(Value::as_bool)
                .unwrap_or(false)),
        );
        output.insert(
            "mount_now".into(),
            json!(payload
                .get("mount_now")
                .and_then(Value::as_bool)
                .unwrap_or(false)),
        );
        // These identities come from SO_PEERCRED, never from the JSON client.
        output.insert("uid".into(), json!(uid));
        output.insert("gid".into(), json!(gid));
    }
    serde_json::to_vec(&Value::Object(output))
        .map_err(|_| "network share payload is invalid".to_string())
}

fn valid_flatpak_id(value: &str) -> bool {
    flatpak_id_re().is_match(value)
}

fn valid_block_device(value: &str) -> bool {
    crate::system::software_catalog::valid_block_device_path(value)
}

/// Validate a request into a fixed executable/argument shape.
fn validate_request(request: &Value, uid: u32, gid: u32) -> Result<ExecSpec, String> {
    let object = request
        .as_object()
        .ok_or_else(|| "request must be an object".to_string())?;
    let operation = object
        .get("operation")
        .and_then(Value::as_str)
        .unwrap_or("");
    let (argv, stdin) = match operation {
        "flatpak_update" => (vec!["/usr/bin/flatpak", "update", "--system", "-y"], None),
        "flatpak_uninstall" => {
            let app_id = text(request, "app_id");
            if !valid_flatpak_id(app_id) {
                return Err("invalid Flatpak application id".to_string());
            }
            (
                vec!["/usr/bin/flatpak", "uninstall", "--system", "-y", app_id],
                None,
            )
        }
        "firmware_update" => (vec!["/usr/bin/fwupdmgr", "update"], None),
        "nvidia_install" => (vec!["/usr/bin/ujust", "install-nvidia-driver"], None),
        "kernel_switch" => {
            let flavor = text(request, "flavor");
            if !matches!(flavor, "fedora" | "cachy") {
                return Err("kernel flavor must be fedora or cachy".to_string());
            }
            (vec!["/usr/bin/ujust", "switch-kernel", flavor], None)
        }
        "secureboot_enroll" => (vec!["/usr/bin/ujust", "enroll-secureboot"], None),
        "bitlocker_unlock" => {
            let device = text(request, "device");
            let key = text(request, "key");
            if !valid_block_device(device) {
                return Err("invalid block device".to_string());
            }
            if !(8..=128).contains(&key.chars().count()) || key.contains(['\n', '\r']) {
                return Err("invalid BitLocker key".to_string());
            }
            (
                vec![
                    "/usr/bin/udisksctl",
                    "unlock",
                    "-b",
                    device,
                    "--key-file",
                    "/dev/stdin",
                ],
                Some(key.as_bytes().to_vec()),
            )
        }
        "network_share_add" | "network_share_remove" => (
            vec![
                "/usr/libexec/kyth-network-share",
                if operation == "network_share_add" {
                    "add"
                } else {
                    "remove"
                },
            ],
            Some(network_share_stdin(request, operation, uid, gid)?),
        ),
        _ => return Err("operation is not allowlisted".to_string()),
    };
    Ok(ExecSpec {
        argv: argv.into_iter().map(String::from).collect(),
        stdin,
    })
}

fn display_detail(stdout: &[u8], stderr: &[u8], status: std::process::ExitStatus) -> String {
    // stderr wins on failure: helpers print progress chatter on stdout and
    // the real error on stderr, so preferring stdout masks the actionable
    // message. On success either stream may carry the result.
    let output = if !status.success() && stderr.iter().any(|byte| !byte.is_ascii_whitespace()) {
        stderr
    } else if stdout.iter().any(|byte| !byte.is_ascii_whitespace()) {
        stdout
    } else {
        stderr
    };
    let detail = sanitize(String::from_utf8_lossy(output).trim());
    if !detail.trim().is_empty() {
        detail
    } else if let Some(code) = status.code() {
        format!("operation exited with {code}")
    } else {
        "operation terminated without an exit code".to_string()
    }
}

fn run_operation(spec: ExecSpec) -> Result<String, String> {
    use std::os::unix::process::CommandExt;
    let mut command = Command::new(&spec.argv[0]);
    command
        .args(&spec.argv[1..])
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    // Stdin is /dev/null unless the op carries explicit input: a pipe held
    // open forever turns any unexpected helper prompt (new fwupd flow,
    // recipe confirmation) into a 900s hang. Fail fast instead; ops that
    // need input (keys, shares) keep piped+close below.
    if spec.stdin.is_some() {
        command.stdin(Stdio::piped());
    } else {
        command.stdin(Stdio::null());
    }
    // Own process group so the timeout kill below reaches forked
    // grandchildren (fwupdmgr helpers, ujust chains) instead of leaving
    // root orphans a retry would race.
    command.process_group(0);
    let mut child = command
        .spawn()
        .map_err(|error| format!("could not start privileged operation: {error}"))?;
    if let Some(input) = spec.stdin {
        let mut stdin = child
            .stdin
            .take()
            .ok_or_else(|| "privileged operation has no piped stdin".to_string())?;
        stdin
            .write_all(&input)
            .map_err(|error| format!("could not provide privileged input: {error}"))?;
    }
    let stdout = child
        .stdout
        .take()
        .ok_or_else(|| "privileged operation has no piped stdout".to_string())?;
    let stderr = child
        .stderr
        .take()
        .ok_or_else(|| "privileged operation has no piped stderr".to_string())?;
    let stdout_thread = thread::spawn(move || {
        let mut bytes = Vec::new();
        let _ = BufReader::new(stdout)
            .take(64 * 1024)
            .read_to_end(&mut bytes);
        bytes
    });
    let stderr_thread = thread::spawn(move || {
        let mut bytes = Vec::new();
        let _ = BufReader::new(stderr)
            .take(64 * 1024)
            .read_to_end(&mut bytes);
        bytes
    });
    let deadline = Instant::now() + OPERATION_TIMEOUT;
    let status = loop {
        match child
            .try_wait()
            .map_err(|error| format!("could not wait for privileged operation: {error}"))?
        {
            Some(status) => break status,
            None if Instant::now() >= deadline => {
                crate::system::process::kill_process_group(&mut child);
                let _ = child.wait();
                return Err("privileged operation timed out after 900 seconds".to_string());
            }
            None => thread::sleep(Duration::from_millis(50)),
        }
    };
    let stdout = stdout_thread.join().unwrap_or_default();
    let stderr = stderr_thread.join().unwrap_or_default();
    let detail = display_detail(&stdout, &stderr, status);
    if status.success() {
        Ok(detail)
    } else {
        Err(detail)
    }
}

fn sanitize(value: &str) -> String {
    value.replace(['\n', '\r'], " ").chars().take(400).collect()
}

fn audit(uid: u32, operation: &str, ok: bool, detail: &str) {
    let result = (|| -> io::Result<()> {
        fs::create_dir_all("/var/log/kyth")?;
        let mut file = OpenOptions::new()
            .create(true)
            .append(true)
            .open(AUDIT_LOG)?;
        let timestamp = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap_or_default()
            .as_secs();
        writeln!(
            file,
            "{timestamp} uid={uid} operation={} ok={} detail={}",
            sanitize(operation),
            u8::from(ok),
            sanitize(detail)
        )
    })();
    if result.is_err() {
        eprintln!("kyth-privileged: could not write audit log");
    }
}

fn wheel_gid() -> Result<u32, String> {
    let groups = fs::read_to_string("/etc/group")
        .map_err(|error| format!("could not read groups: {error}"))?;
    parse_wheel_gid(&groups)
}

fn parse_wheel_gid(groups: &str) -> Result<u32, String> {
    groups
        .lines()
        .find_map(|line| {
            let mut fields = line.split(':');
            if fields.next() != Some("wheel") {
                return None;
            }
            fields.next()?; // password placeholder
            fields.next()?.parse().ok()
        })
        .ok_or_else(|| "wheel group is unavailable".to_string())
}

fn peer_credentials(stream: &UnixStream) -> io::Result<(u32, u32, u32)> {
    let mut credentials = libc::ucred {
        pid: 0,
        uid: 0,
        gid: 0,
    };
    let mut length = std::mem::size_of::<libc::ucred>() as libc::socklen_t;
    let result = unsafe {
        libc::getsockopt(
            stream.as_raw_fd(),
            libc::SOL_SOCKET,
            libc::SO_PEERCRED,
            &mut credentials as *mut _ as *mut libc::c_void,
            &mut length,
        )
    };
    if result != 0 {
        return Err(io::Error::last_os_error());
    }
    Ok((credentials.pid as u32, credentials.uid, credentials.gid))
}

fn peer_allowed(stream: &UnixStream) -> Result<(u32, u32, u32), String> {
    let (pid, uid, gid) = peer_credentials(stream).map_err(|error| error.to_string())?;
    let wheel = wheel_gid()?;
    if uid == 0 || gid == wheel {
        return Ok((pid, uid, gid));
    }
    let status = fs::read_to_string(format!("/proc/{pid}/status")).unwrap_or_default();
    let supplementary = status
        .lines()
        .find_map(|line| line.strip_prefix("Groups:"))
        .map(|line| {
            line.split_whitespace()
                .filter_map(|value| value.parse::<u32>().ok())
                .any(|group| group == wheel)
        })
        .unwrap_or(false);
    if !supplementary {
        return Err("caller is not root or a wheel member".to_string());
    }
    Ok((pid, uid, gid))
}

fn response(ok: bool, detail: &str) -> Vec<u8> {
    format!("{}\n", json!({"ok": ok, "detail": detail})).into_bytes()
}

/// Redact secrets from helper output before it crosses either the audit or UI
/// boundary. The request is still sent only over the local socket and secret
/// inputs remain stdin-only for the privileged child.
pub fn redact_request_detail(request: &Value, detail: &str) -> String {
    let mut safe = detail.to_string();
    let secrets = [
        request.get("key").and_then(Value::as_str),
        request
            .get("payload")
            .and_then(Value::as_object)
            .and_then(|payload| payload.get("password"))
            .and_then(Value::as_str),
    ];
    for secret in secrets
        .into_iter()
        .flatten()
        .filter(|value| !value.is_empty())
    {
        safe = safe.replace(secret, "<redacted>");
    }
    crate::system::process::redact_sensitive_text(&safe)
}

fn handle_client(stream: UnixStream) {
    let (_pid, uid, gid) = match peer_allowed(&stream) {
        Ok(credentials) => credentials,
        Err(error) => {
            let mut stream = stream;
            let _ = stream.write_all(&response(false, &error));
            return;
        }
    };
    let reader_stream = match stream.try_clone() {
        Ok(stream) => stream,
        Err(_) => return,
    };
    let mut reader = BufReader::new(reader_stream);
    let mut writer = stream;
    let mut line = String::new();
    loop {
        line.clear();
        // A single unbounded line can OOM the root daemon: cap at 128 KiB
        // and drop the connection past it. take() ends the read at the
        // cap, and any bytes beyond a full line mean the peer is hostile.
        let mut capped = (&mut reader).take(MAX_REQUEST_LINE_BYTES);
        match capped.read_line(&mut line) {
            Ok(0) => break,
            Ok(_) => {
                if line.len() as u64 >= MAX_REQUEST_LINE_BYTES && !line.ends_with('\n') {
                    audit(uid, "oversize", false, "request line exceeded cap");
                    break;
                }
                let request = serde_json::from_str::<Value>(&line);
                let operation = request
                    .as_ref()
                    .ok()
                    .and_then(|value| value.get("operation"))
                    .and_then(Value::as_str)
                    .unwrap_or("invalid")
                    .to_string();
                let result = match request.as_ref() {
                    Ok(value) => validate_request(value, uid, gid).and_then(run_operation),
                    Err(error) => Err(error.to_string()),
                };
                let (ok, detail) = match result {
                    Ok(detail) => (true, detail),
                    Err(error) => (false, error),
                };
                let detail = request.as_ref().map_or_else(
                    |_| crate::system::process::redact_sensitive_text(&detail),
                    |value| redact_request_detail(value, &detail),
                );
                audit(uid, &operation, ok, &detail);
                if writer.write_all(&response(ok, &detail)).is_err() {
                    break;
                }
                let _ = writer.flush();
            }
            Err(error) => {
                let detail = error.to_string();
                audit(uid, "invalid", false, &detail);
                let _ = writer.write_all(&response(false, &detail));
                break;
            }
        }
    }
}

pub fn serve() -> Result<(), String> {
    if !rustix::process::getuid().is_root() {
        return Err("kyth-privileged must run as root".to_string());
    }
    let wheel = wheel_gid()?;
    fs::create_dir_all("/run/kyth")
        .map_err(|error| format!("could not create runtime directory: {error}"))?;
    match fs::symlink_metadata(SOCKET) {
        Ok(metadata) if metadata.file_type().is_socket() => {
            fs::remove_file(SOCKET).map_err(|error| error.to_string())?
        }
        Ok(_) => return Err("privileged socket path exists and is not a socket".to_string()),
        Err(error) if error.kind() == io::ErrorKind::NotFound => {}
        Err(error) => return Err(error.to_string()),
    }
    let listener = UnixListener::bind(SOCKET)
        .map_err(|error| format!("could not bind privileged socket: {error}"))?;
    let fd = listener.as_raw_fd();
    let chown_result = unsafe { libc::fchown(fd, 0, wheel) };
    if chown_result != 0 {
        return Err(format!(
            "could not set socket owner: {}",
            io::Error::last_os_error()
        ));
    }
    // fchmod(2) on a UNIX-domain socket fd does not update the mode of the
    // bound pathname's directory entry on Linux; the mode must be set via
    // the path instead.
    fs::set_permissions(SOCKET, fs::Permissions::from_mode(0o660))
        .map_err(|error| format!("could not set socket mode: {error}"))?;
    for stream in listener.incoming() {
        match stream {
            Ok(stream) => {
                // Bound concurrent clients: without this, one peer opening
                // connections in a loop exhausts daemon threads (root DoS).
                static CLIENTS: std::sync::atomic::AtomicUsize =
                    std::sync::atomic::AtomicUsize::new(0);
                let active = CLIENTS.fetch_add(1, std::sync::atomic::Ordering::SeqCst);
                if active >= MAX_CLIENTS {
                    CLIENTS.fetch_sub(1, std::sync::atomic::Ordering::SeqCst);
                    eprintln!("kyth-privileged: client cap reached, refusing connection");
                    continue;
                }
                thread::spawn(|| {
                    handle_client(stream);
                    CLIENTS.fetch_sub(1, std::sync::atomic::Ordering::SeqCst);
                });
            }
            Err(error) => eprintln!("kyth-privileged: incoming connection failed: {error}"),
        }
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use serde_json::json;

    use super::display_detail;
    use super::{
        parse_wheel_gid, redact_request_detail, run_operation, validate_request, ExecSpec,
    };

    fn exit_status(success: bool) -> std::process::ExitStatus {
        std::process::Command::new(if success { "true" } else { "false" })
            .status()
            .expect("exit probe")
    }

    #[test]
    fn operation_without_input_gets_null_stdin_not_a_dead_pipe() {
        // `cat` with no input spec must fail fast (EOF on /dev/null),
        // not hang until the operation timeout.
        let started = std::time::Instant::now();
        let result = run_operation(ExecSpec {
            argv: vec!["cat".to_string()],
            stdin: None,
        });
        assert!(started.elapsed() < std::time::Duration::from_secs(30));
        // cat with empty stdin exits 0 with empty output; the point is it
        // returned at all instead of hanging.
        assert!(result.is_ok());
    }

    #[test]
    fn failure_detail_prefers_stderr_over_stdout_chatter() {
        let detail = display_detail(
            b"step 1/10\nstep 2/10\n",
            b"cryptsetup failed: no key available\n",
            exit_status(false),
        );
        assert!(detail.contains("cryptsetup failed"), "{detail}");
    }

    #[test]
    fn success_detail_still_uses_stdout_and_collapses_lines() {
        let detail = display_detail(b"line one\nline two\n", b"", exit_status(true));
        assert_eq!(detail, "line one line two");
    }

    #[test]
    fn empty_output_reports_exit_code() {
        let detail = display_detail(b"", b"  \n", exit_status(false));
        assert!(detail.contains("exited"), "{detail}");
    }

    #[test]
    fn wheel_gid_reads_third_field_not_password_placeholder() {
        let groups = "root:x:0:\nwheel:x:10:phendrick\nusers:x:100:\n";
        assert_eq!(parse_wheel_gid(groups), Ok(10));
    }

    #[test]
    fn wheel_gid_errors_when_group_missing() {
        let groups = "root:x:0:\nusers:x:100:\n";
        assert!(parse_wheel_gid(groups).is_err());
    }

    #[test]
    fn only_fixed_operations_are_constructed() {
        assert!(validate_request(&json!({"operation":"not-allowed"}), 1000, 1000).is_err());
        assert!(validate_request(&json!({"operation":"windows_verify"}), 1000, 1000).is_err());
        let request = validate_request(
            &json!({"operation":"kernel_switch","flavor":"cachy"}),
            1000,
            1000,
        )
        .unwrap();
        assert_eq!(request.argv, ["/usr/bin/ujust", "switch-kernel", "cachy"]);
        assert!(validate_request(
            &json!({"operation":"flatpak_uninstall","app_id":"org.example.App"}),
            1000,
            1000
        )
        .is_ok());
        assert!(validate_request(
            &json!({"operation":"flatpak_uninstall","app_id":"_org.example"}),
            1000,
            1000
        )
        .is_err());
    }

    #[test]
    fn bitlocker_key_is_stdin_only_and_validation_never_echoes_it() {
        let error = validate_request(
            &json!({"operation":"bitlocker_unlock","device":"/tmp/disk","key":"secret-key"}),
            1000,
            1000,
        )
        .unwrap_err();
        assert_eq!(error, "invalid block device");
        let error = validate_request(
            &json!({"operation":"bitlocker_unlock","device":"/dev/sda1","key":"short"}),
            1000,
            1000,
        )
        .unwrap_err();
        assert_eq!(error, "invalid BitLocker key");
        let request = validate_request(
            &json!({"operation":"bitlocker_unlock","device":"/dev/sda1","key":"12345678"}),
            1000,
            1000,
        )
        .unwrap();
        assert_eq!(request.argv.last().unwrap(), "/dev/stdin");
        assert_eq!(request.stdin.unwrap(), b"12345678");
    }

    #[test]
    fn network_share_uses_peer_identity_and_drops_untrusted_fields() {
        let request = validate_request(&json!({"operation":"network_share_add","payload":{"name":"media","server":"nas.local","share_path":"media","mount_point":"/mnt/media","username":"pat","password":"secret","domain":"","auto_mount":true,"mount_now":false,"uid":1}}), 1001, 1002).unwrap();
        let payload: serde_json::Value = serde_json::from_slice(&request.stdin.unwrap()).unwrap();
        assert_eq!(payload["uid"], 1001);
        assert_eq!(payload["gid"], 1002);
        assert!(payload.get("untrusted").is_none());
        assert!(validate_request(
            &json!({"operation":"network_share_add","payload":{"name":"bad/name"}}),
            1000,
            1000
        )
        .is_err());
    }

    #[test]
    fn helper_detail_redacts_request_secrets() {
        let request = json!({
            "operation": "network_share_add",
            "payload": {"password": "share-secret"}
        });
        let detail = redact_request_detail(&request, "mount failed password=share-secret");
        assert!(!detail.contains("share-secret"));
        assert!(detail.contains("password=<redacted>"));
    }

    #[test]
    fn operation_spawn_failure_returns_err_instead_of_panicking() {
        let missing = run_operation(ExecSpec {
            argv: vec!["/nonexistent-kyth-helper-binary".into()],
            stdin: None,
        });
        assert!(missing.is_err());
        let failing = run_operation(ExecSpec {
            argv: vec!["false".into()],
            stdin: None,
        });
        assert!(failing.is_err());
        let passing = run_operation(ExecSpec {
            argv: vec!["true".into()],
            stdin: None,
        });
        assert!(passing.is_ok());
    }
}
