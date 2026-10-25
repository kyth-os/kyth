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
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, OnceLock};
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

/// Normalize a mount-point path. `..` components are REJECTED, not
/// popped: popping silently rewrote `/mnt/../home/user/share` into a
/// prefix the Hub frontend refuses but the daemon accepted.
fn normalize_mount_point(value: &str) -> Result<String, String> {
    let mut parts = Vec::new();
    for part in value.split('/') {
        match part {
            "" | "." => {}
            ".." => {
                return Err("mount_point must not contain '..'".to_string());
            }
            part => parts.push(part),
        }
    }
    Ok(if parts.is_empty() {
        "/".to_string()
    } else {
        format!("/{}", parts.join("/"))
    })
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
    let mount_point = normalize_mount_point(value)?;
    if !mount_path_re().is_match(&mount_point)
        || mount_point.contains("//")
        || !["/mnt/", "/media/", "/run/media/"]
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
    // Most shapes are fixed literals; collect them as owned strings so an
    // arm can also build its argv from a shared helper (firmware below).
    let argv_of =
        |parts: &[&str]| -> Vec<String> { parts.iter().map(|part| part.to_string()).collect() };
    let (argv, stdin) = match operation {
        "flatpak_update" => (
            argv_of(&["/usr/bin/flatpak", "update", "--system", "-y"]),
            None,
        ),
        "flatpak_uninstall" => {
            let app_id = text(request, "app_id");
            if !valid_flatpak_id(app_id) {
                return Err("invalid Flatpak application id".to_string());
            }
            (
                argv_of(&["/usr/bin/flatpak", "uninstall", "--system", "-y", app_id]),
                None,
            )
        }
        "firmware_update" => {
            // The shared helper owns the flag set: fwupdmgr prompts unless
            // told --assume-yes, and daemon children run with stdin
            // /dev/null, so a bare `fwupdmgr update` reads EOF at the first
            // prompt and aborts. The daemon pins the absolute path like
            // every other shape here; the helper spells the tool bare.
            let mut argv = crate::system::firmware::firmware_update_command();
            argv[0] = format!("/usr/bin/{}", argv[0]);
            (argv, None)
        }
        "nvidia_install" => (argv_of(&["/usr/bin/ujust", "install-nvidia-driver"]), None),
        "kernel_switch" => {
            let flavor = text(request, "flavor");
            if !matches!(flavor, "fedora" | "cachy") {
                return Err("kernel flavor must be fedora or cachy".to_string());
            }
            (argv_of(&["/usr/bin/ujust", "switch-kernel", flavor]), None)
        }
        "secureboot_enroll" => (argv_of(&["/usr/bin/ujust", "enroll-secureboot"]), None),
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
                argv_of(&[
                    "/usr/bin/udisksctl",
                    "unlock",
                    "-b",
                    device,
                    "--key-file",
                    "/dev/stdin",
                ]),
                Some(key.as_bytes().to_vec()),
            )
        }
        "network_share_add" | "network_share_remove" => (
            argv_of(&[
                "/usr/libexec/kyth-network-share",
                if operation == "network_share_add" {
                    "add"
                } else {
                    "remove"
                },
            ]),
            Some(network_share_stdin(request, operation, uid, gid)?),
        ),
        _ => return Err("operation is not allowlisted".to_string()),
    };
    Ok(ExecSpec { argv, stdin })
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

/// Serializes flatpak mutations across client threads. The daemon spawns
/// one thread per connection with no other operation mutex, so a
/// system-scope app update and a system-scope uninstall from two Hub
/// actions could run two `flatpak` processes against the same installation
/// at once; flatpak's own transaction lock then fails one of them
/// spuriously. Non-flatpak operations are unaffected.
static FLATPAK_OP_LOCK: std::sync::Mutex<()> = std::sync::Mutex::new(());

fn is_flatpak_mutation(argv: &[String]) -> bool {
    argv.first().map(String::as_str) == Some("/usr/bin/flatpak")
        && argv
            .get(1)
            .map(String::as_str)
            .is_some_and(|verb| matches!(verb, "update" | "uninstall" | "install"))
}

/// Read a child pipe to EOF, keeping only the first `cap` bytes (plus a
/// truncation marker). The pipe must be drained *past* the cap: the old
/// `take(cap)` readers stopped at the cap and dropped the read end, so a
/// verbose child (a system update touching many refs) blocked on a full
/// pipe or died on SIGPIPE and the operation burned its whole timeout.
fn drain_capped<R: Read>(reader: R, cap: usize) -> Vec<u8> {
    let mut kept = Vec::with_capacity(cap.min(64 * 1024));
    let mut reader = BufReader::new(reader);
    let mut chunk = [0u8; 8192];
    let mut truncated = false;
    loop {
        match reader.read(&mut chunk) {
            Ok(0) => break,
            Ok(count) => {
                let room = cap.saturating_sub(kept.len());
                let take = count.min(room);
                kept.extend_from_slice(&chunk[..take]);
                truncated |= take < count;
            }
            Err(_) => break,
        }
    }
    if truncated {
        kept.extend_from_slice(b"\n...[truncated]");
    }
    kept
}

/// Unbounded-context entry for tests: full timeout budget from now and
/// no client whose disappearance should abandon the operation.
fn run_operation(spec: ExecSpec) -> Result<String, String> {
    let never_gone = AtomicBool::new(false);
    run_operation_bounded(spec, Instant::now() + OPERATION_TIMEOUT, &never_gone)
}

/// Acquire the flatpak mutex without waiting past `deadline` or past the
/// client going away. A std Mutex has no timed lock, so poll try_lock:
/// operations here run for seconds-to-minutes, so a 25 ms poll is cheap.
fn acquire_flatpak_lock(
    deadline: Instant,
    client_gone: &AtomicBool,
) -> Result<std::sync::MutexGuard<'static, ()>, String> {
    loop {
        match FLATPAK_OP_LOCK.try_lock() {
            Ok(guard) => return Ok(guard),
            Err(std::sync::TryLockError::Poisoned(poisoned)) => {
                return Ok(poisoned.into_inner());
            }
            Err(std::sync::TryLockError::WouldBlock) => {
                if client_gone.load(Ordering::SeqCst) {
                    return Err(
                        "privileged operation cancelled: the client disconnected".to_string()
                    );
                }
                if Instant::now() >= deadline {
                    return Err(
                        "timed out waiting for another privileged operation to finish".to_string(),
                    );
                }
                thread::sleep(Duration::from_millis(25));
            }
        }
    }
}

fn run_operation_bounded(
    spec: ExecSpec,
    deadline: Instant,
    client_gone: &AtomicBool,
) -> Result<String, String> {
    use std::os::unix::process::CommandExt;
    // Held for the whole operation when this is a flatpak mutation; the
    // guard is intentionally unused-named so it drops at function exit —
    // including the kill paths below, so a cancelled or timed-out
    // operation never wedges the lock for the next client.
    let _flatpak_guard = if is_flatpak_mutation(&spec.argv) {
        Some(acquire_flatpak_lock(deadline, client_gone)?)
    } else {
        None
    };
    let mut command = Command::new(&spec.argv[0]);
    command
        .args(&spec.argv[1..])
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    // This daemon runs as root: never let children inherit its environment.
    // LD_PRELOAD / LD_LIBRARY_PATH / PYTHONPATH etc. from the daemon's
    // environment would apply to every privileged helper. Start from a
    // minimal explicit set instead (allowlist, not denylist).
    command.env_clear();
    command.env("PATH", "/usr/sbin:/usr/bin:/sbin:/bin");
    command.env("LANG", "C.UTF-8");
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
    let stdout_thread = thread::spawn(move || drain_capped(stdout, 64 * 1024));
    let stderr_thread = thread::spawn(move || drain_capped(stderr, 64 * 1024));
    // `deadline` was fixed when the request was received, before any lock
    // wait, so queueing behind another operation consumes the same budget
    // the caller's read timeout is sized against: a queued operation can
    // no longer be reported failed by the caller and then succeed here.
    let status = loop {
        match child
            .try_wait()
            .map_err(|error| format!("could not wait for privileged operation: {error}"))?
        {
            Some(status) => break status,
            // The client that asked for this operation has gone away (the
            // Hub's cancel shuts its connection down): nobody is waiting
            // for the result, so the operation is abandoned — kill it
            // like a timeout instead of letting root work run unobserved.
            None if client_gone.load(Ordering::SeqCst) => {
                crate::system::process::kill_process_group(&mut child);
                let _ = child.wait();
                return Err("privileged operation cancelled: the client disconnected".to_string());
            }
            None if Instant::now() >= deadline => {
                crate::system::process::kill_process_group(&mut child);
                let _ = child.wait();
                return Err(format!(
                    "privileged operation timed out after {} seconds",
                    OPERATION_TIMEOUT.as_secs()
                ));
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

/// Authorization model: any process running as root or as a wheel
/// member may use the daemon; the peer is NOT verified to be the Hub
/// binary. That is a deliberate trade-off, not an oversight: wheel
/// membership is already sudo-equivalent on this system (a wheel member
/// can obtain a root shell, and with it everything this daemon can do),
/// so pinning the peer to one binary would add fragility — binary
/// identity checks that must survive updates — without raising the bar
/// for anyone the model excludes. The fixed operation allowlist, not
/// peer identity, is the boundary that limits what root can be asked
/// to do.
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
    // The pid above came from SO_PEERCRED, but the peer may have exited and
    // its pid recycled between the getsockopt and the /proc read, in which
    // case the group check evaluated the wrong process. Re-read the peer
    // credentials and require the pid to be unchanged: an attacker would now
    // have to win the race twice with the same recycled pid.
    let (pid_after, _, _) = peer_credentials(stream).map_err(|error| error.to_string())?;
    if pid_after != pid {
        return Err("peer changed during authorization; retry the request".to_string());
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

/// Watch one client connection for the peer going away. Uses poll(2) +
/// MSG_PEEK rather than a read timeout: a timeout set on this socket
/// would apply to the shared connection and break the request loop's
/// blocking reads, and peeking never consumes bytes the loop needs.
fn watch_client(stream: UnixStream, gone: Arc<AtomicBool>) {
    let fd = stream.as_raw_fd();
    let mut pollfd = libc::pollfd {
        fd,
        events: libc::POLLIN,
        revents: 0,
    };
    loop {
        pollfd.revents = 0;
        let ready = unsafe { libc::poll(&mut pollfd, 1, 250) };
        if ready < 0 {
            if io::Error::last_os_error().raw_os_error() == Some(libc::EINTR) {
                continue;
            }
            gone.store(true, Ordering::SeqCst);
            return;
        }
        if ready == 0 {
            continue; // still connected, nothing pending
        }
        if pollfd.revents & (libc::POLLHUP | libc::POLLERR | libc::POLLNVAL) != 0 {
            gone.store(true, Ordering::SeqCst);
            return;
        }
        if pollfd.revents & libc::POLLIN != 0 {
            let mut byte = [0u8; 1];
            let count = unsafe {
                libc::recv(
                    fd,
                    byte.as_mut_ptr() as *mut libc::c_void,
                    byte.len(),
                    libc::MSG_PEEK | libc::MSG_DONTWAIT,
                )
            };
            if count == 0 {
                // Orderly shutdown: the peer closed its side.
                gone.store(true, Ordering::SeqCst);
                return;
            }
            if count < 0 && io::Error::last_os_error().raw_os_error() != Some(libc::EAGAIN) {
                gone.store(true, Ordering::SeqCst);
                return;
            }
            // Bytes are pending (the next request arriving early is not a
            // disconnect). They stay buffered for the request loop; pause
            // so peek does not spin on the same byte.
            thread::sleep(Duration::from_millis(50));
        }
    }
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
    // One watcher per connection: it notices the peer going away while an
    // operation runs (see watch_client) so run_operation_bounded can
    // abandon work nobody is waiting for. The flag is per-connection and
    // reset before each operation; requests on one connection are handled
    // sequentially, so there is no cross-request race.
    let client_gone = Arc::new(AtomicBool::new(false));
    if let Ok(watch_stream) = stream.try_clone() {
        let gone = Arc::clone(&client_gone);
        thread::spawn(move || watch_client(watch_stream, gone));
    }
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
                // The operation budget starts at request receipt, before
                // validation and before any flatpak-lock wait inside the
                // operation (the Hub's read timeout is sized against the
                // same 900 s from its side of the socket).
                let deadline = Instant::now() + OPERATION_TIMEOUT;
                client_gone.store(false, Ordering::SeqCst);
                let result = match request.as_ref() {
                    Ok(value) => validate_request(value, uid, gid)
                        .and_then(|spec| run_operation_bounded(spec, deadline, &client_gone)),
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
        acquire_flatpak_lock, drain_capped, is_flatpak_mutation, parse_wheel_gid,
        redact_request_detail, run_operation, run_operation_bounded, validate_request, ExecSpec,
        FLATPAK_OP_LOCK,
    };

    #[test]
    fn drain_capped_keeps_draining_past_the_cap() {
        // 200 KiB through a 64 KiB cap: the reader must consume everything
        // (a stopped reader deadlocks a verbose child), keep the prefix,
        // and mark the truncation.
        let source = vec![b'x'; 200 * 1024];
        let kept = drain_capped(std::io::Cursor::new(source), 64 * 1024);
        assert!(kept.starts_with(&[b'x'; 64 * 1024][..]));
        assert!(kept.ends_with(b"\n...[truncated]"));
        // Under the cap the bytes pass through untouched.
        let small = drain_capped(std::io::Cursor::new(b"hello".to_vec()), 64 * 1024);
        assert_eq!(small, b"hello");
    }

    #[test]
    fn flatpak_mutation_detection_covers_only_flatpak_writes() {
        let argv = |parts: &[&str]| parts.iter().map(|s| s.to_string()).collect::<Vec<_>>();
        assert!(is_flatpak_mutation(&argv(&[
            "/usr/bin/flatpak",
            "update",
            "--system",
            "-y"
        ])));
        assert!(is_flatpak_mutation(&argv(&[
            "/usr/bin/flatpak",
            "uninstall",
            "--system",
            "-y",
            "org.example.App"
        ])));
        assert!(!is_flatpak_mutation(&argv(&[
            "/usr/bin/fwupdmgr",
            "update"
        ])));
        assert!(!is_flatpak_mutation(&argv(&["/usr/bin/flatpak", "list"])));
    }

    fn exit_status(success: bool) -> std::process::ExitStatus {
        std::process::Command::new(if success { "true" } else { "false" })
            .status()
            .expect("exit probe")
    }

    #[test]
    fn mount_point_rejects_home_prefix_and_parent_dirs() {
        use super::share_mount_point;
        use serde_json::{Map, Value};
        fn payload(mount_point: &str) -> Map<String, Value> {
            let mut map = Map::new();
            map.insert("mount_point".into(), Value::String(mount_point.into()));
            map
        }
        // /home/ is not an approved prefix; '..' fails closed instead of
        // being popped into a different prefix.
        assert!(share_mount_point(&payload("/home/alice/share")).is_err());
        assert!(share_mount_point(&payload("/mnt/../home/alice/share")).is_err());
        assert!(share_mount_point(&payload("/mnt/media")).is_ok());
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
    fn firmware_update_uses_the_shared_noninteractive_argv() {
        // fwupdmgr prompts without --assume-yes, and daemon children get
        // stdin /dev/null, so the bare `fwupdmgr update` shape aborted on
        // EOF at the first prompt. Pin the daemon to the shared helper's
        // flag set (with the daemon's absolute-path convention).
        let request =
            validate_request(&json!({"operation":"firmware_update"}), 1000, 1000).unwrap();
        assert_eq!(
            request.argv,
            [
                "/usr/bin/fwupdmgr",
                "update",
                "--assume-yes",
                "--no-reboot-check"
            ]
        );
        assert!(request.stdin.is_none());
    }

    #[test]
    fn client_disconnect_mid_operation_kills_the_child() {
        use std::sync::atomic::{AtomicBool, Ordering};
        use std::sync::Arc;
        let gone = Arc::new(AtomicBool::new(false));
        let thread_gone = Arc::clone(&gone);
        let started = std::time::Instant::now();
        let handle = std::thread::spawn(move || {
            run_operation_bounded(
                ExecSpec {
                    argv: vec!["sleep".to_string(), "60".to_string()],
                    stdin: None,
                },
                std::time::Instant::now() + std::time::Duration::from_secs(120),
                &thread_gone,
            )
        });
        std::thread::sleep(std::time::Duration::from_millis(300));
        gone.store(true, Ordering::SeqCst);
        let result = handle.join().expect("operation thread panicked");
        assert!(
            started.elapsed() < std::time::Duration::from_secs(10),
            "disconnect must kill promptly, took {:?}",
            started.elapsed()
        );
        let error = result.unwrap_err();
        assert!(error.contains("client disconnected"), "{error}");
    }

    #[test]
    fn flatpak_lock_wait_respects_the_operation_deadline() {
        use std::time::{Duration, Instant};
        // Hold the lock: acquisition with a 300 ms budget must give up
        // with the queueing error, not wait for the holder — the wait used
        // to be unbounded and outside the operation timeout entirely.
        let _held = FLATPAK_OP_LOCK.lock().unwrap();
        let never_gone = std::sync::atomic::AtomicBool::new(false);
        let started = Instant::now();
        match acquire_flatpak_lock(Instant::now() + Duration::from_millis(300), &never_gone) {
            Ok(_) => panic!("lock acquisition must time out while the lock is held"),
            Err(error) => assert!(error.contains("timed out waiting"), "{error}"),
        }
        assert!(started.elapsed() < Duration::from_secs(5));
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
