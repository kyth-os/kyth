//! Native root-facing transport for the installer compatibility backend.
//!
//! The destructive installer phases are still implemented by the Python
//! backend while their Rust equivalents gain parity coverage.  This binary
//! owns the privileged Unix socket, validates the session boundary, and
//! exposes the backend only through a loopback connection.  The Python
//! process never binds the user-visible socket.

use std::ffi::CString;
use std::fs::{self, OpenOptions};
use std::io::{self, Read, Write};
use std::os::fd::AsRawFd;
use std::os::unix::fs::{FileTypeExt, MetadataExt, OpenOptionsExt, PermissionsExt};
use std::os::unix::net::{UnixListener, UnixStream};
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::thread;
use std::time::{Duration, Instant};

const MAX_REQUEST_BYTES: usize = 16 * 1024 * 1024;
const BACKEND_SOCKET_SUFFIX: &str = ".backend";

struct Options {
    socket_path: PathBuf,
    session_token_file: PathBuf,
    socket_group: Option<String>,
    peer_uid: Option<u32>,
}

fn value(args: &[String], name: &str) -> Result<String, String> {
    let index = args.iter().position(|arg| arg == name).ok_or_else(|| format!("missing {name}"))?;
    args.get(index + 1).cloned().ok_or_else(|| format!("missing value for {name}"))
}

fn options(args: &[String]) -> Result<Options, String> {
    let socket_group = args.iter().position(|arg| arg == "--socket-group").map(|index| {
        args.get(index + 1).cloned().ok_or_else(|| "missing value for --socket-group".to_string())
    }).transpose()?;
    let peer_uid = args.iter().position(|arg| arg == "--peer-uid").map(|index| {
        args.get(index + 1).ok_or_else(|| "missing value for --peer-uid".to_string())?.parse::<u32>().map_err(|_| "invalid --peer-uid".to_string())
    }).transpose()?;
    Ok(Options {
        socket_path: PathBuf::from(value(args, "--socket-path")?),
        session_token_file: PathBuf::from(value(args, "--session-token-file")?),
        socket_group,
        peer_uid,
    })
}

fn read_session_token(path: &Path) -> Result<String, String> {
    let file = OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_NOFOLLOW)
        .open(path)
        .map_err(|error| format!("could not open installer session token: {error}"))?;
    let metadata = file.metadata().map_err(|error| format!("could not stat installer session token: {error}"))?;
    if !metadata.is_file() || metadata.uid() != 0 || metadata.mode() & 0o077 != 0 {
        return Err("installer session token must be a root-owned private regular file".to_string());
    }
    let mut token = String::new();
    (&file).take(513).read_to_string(&mut token).map_err(|error| format!("could not read installer session token: {error}"))?;
    let token = token.trim();
    if !(32..=512).contains(&token.len()) || !token.bytes().all(|byte| byte.is_ascii_alphanumeric() || byte == b'_' || byte == b'-') {
        return Err("installer session token has an invalid format".to_string());
    }
    Ok(token.to_string())
}

fn group_id(name: &str) -> Result<u32, String> {
    let name = CString::new(name).map_err(|_| "socket group contains NUL".to_string())?;
    // SAFETY: getgrnam reads the process' system group database and returns a
    // pointer owned by libc; it is used only for the scalar gid value.
    let entry = unsafe { libc::getgrnam(name.as_ptr()) };
    if entry.is_null() {
        return Err(format!("socket group does not exist: {}", name.to_string_lossy()));
    }
    // SAFETY: entry was checked non-null above.
    Ok(unsafe { (*entry).gr_gid })
}

fn chown(path: &Path, gid: u32) -> Result<(), String> {
    let path = CString::new(path.as_os_str().as_encoded_bytes()).map_err(|_| "socket path contains NUL".to_string())?;
    // SAFETY: path is a NUL-free CString and -1 preserves the current owner.
    if unsafe { libc::chown(path.as_ptr(), u32::MAX, gid) } != 0 {
        return Err(format!("could not set socket group: {}", io::Error::last_os_error()));
    }
    Ok(())
}

fn listener(options: &Options) -> Result<UnixListener, String> {
    let parent = options.socket_path.parent().ok_or_else(|| "socket path has no parent".to_string())?;
    fs::create_dir_all(parent).map_err(|error| format!("could not create installer socket directory: {error}"))?;
    fs::set_permissions(parent, fs::Permissions::from_mode(0o750)).map_err(|error| format!("could not secure installer socket directory: {error}"))?;
    let gid = options.socket_group.as_deref().map(group_id).transpose()?;
    if let Some(gid) = gid { chown(parent, gid)?; }

    if fs::symlink_metadata(&options.socket_path).is_ok() {
        let metadata = fs::symlink_metadata(&options.socket_path).map_err(|error| error.to_string())?;
        if !metadata.file_type().is_socket() {
            return Err("installer socket path is not a socket".to_string());
        }
        fs::remove_file(&options.socket_path).map_err(|error| format!("could not replace installer socket: {error}"))?;
    }
    let socket = UnixListener::bind(&options.socket_path).map_err(|error| format!("could not bind installer socket: {error}"))?;
    fs::set_permissions(&options.socket_path, fs::Permissions::from_mode(if gid.is_some() { 0o660 } else { 0o600 }))
        .map_err(|error| format!("could not secure installer socket: {error}"))?;
    if let Some(gid) = gid { chown(&options.socket_path, gid)?; }
    Ok(socket)
}

fn peer_uid(stream: &UnixStream) -> Result<u32, String> {
    let mut credentials = libc::ucred { pid: 0, uid: 0, gid: 0 };
    let mut length = std::mem::size_of::<libc::ucred>() as libc::socklen_t;
    // SAFETY: credentials and length point to valid writable storage for the
    // socket option requested from this connected Unix stream.
    let result = unsafe {
        libc::getsockopt(stream.as_raw_fd(), libc::SOL_SOCKET, libc::SO_PEERCRED, &mut credentials as *mut _ as *mut _, &mut length)
    };
    if result != 0 { return Err(format!("could not inspect installer peer: {}", io::Error::last_os_error())); }
    Ok(credentials.uid)
}

fn route_allowed(method: &str, target: &str) -> bool {
    let path = target.split('?').next().unwrap_or(target);
    match method {
        "GET" => matches!(path, "/api/config" | "/api/disks" | "/api/partitions" | "/api/free-space" | "/api/timezones" | "/api/locales" | "/api/keymaps" | "/api/disk/pending" | "/api/disk/filesystems" | "/api/report" | "/api/rescue/probe" | "/api/log" | "/api/stream"),
        "POST" => matches!(path, "/api/start" | "/api/cancel" | "/api/reboot" | "/api/disk/new-table" | "/api/disk/create" | "/api/disk/delete" | "/api/disk/resize" | "/api/disk/format" | "/api/disk/set-mountpoint" | "/api/disk/pending/remove" | "/api/disk/commit" | "/api/disk/rollback" | "/api/rescue/logs-to-usb"),
        _ => false,
    }
}

fn header_value<'a>(headers: &'a str, name: &str) -> Option<&'a str> {
    headers.lines().skip(1).find_map(|line| {
        let (key, value) = line.split_once(':')?;
        key.trim().eq_ignore_ascii_case(name).then_some(value.trim())
    })
}

fn request_parts(request: &[u8]) -> Result<(&str, &str, &str), String> {
    let header_end = request.windows(4).position(|window| window == b"\r\n\r\n").ok_or_else(|| "installer request has no complete headers".to_string())?;
    let headers = std::str::from_utf8(&request[..header_end]).map_err(|_| "installer request headers are not UTF-8".to_string())?;
    let mut line = headers.lines().next().unwrap_or_default().split_whitespace();
    let method = line.next().unwrap_or_default();
    let target = line.next().unwrap_or_default();
    if line.next().is_some() || method.is_empty() || target.is_empty() { return Err("installer request line is invalid".to_string()); }
    Ok((method, target, headers))
}

fn read_request(stream: &mut UnixStream) -> Result<Vec<u8>, String> {
    let mut request = Vec::with_capacity(4096);
    let mut buffer = [0_u8; 4096];
    let header_end = loop {
        let count = stream.read(&mut buffer).map_err(|error| format!("could not read installer request: {error}"))?;
        if count == 0 { return Err("installer client closed before sending a request".to_string()); }
        request.extend_from_slice(&buffer[..count]);
        if request.len() > MAX_REQUEST_BYTES { return Err("installer request is too large".to_string()); }
        if let Some(position) = request.windows(4).position(|window| window == b"\r\n\r\n") { break position + 4; }
    };
    let header_text = std::str::from_utf8(&request[..header_end - 4]).map_err(|_| "installer request headers are not UTF-8".to_string())?;
    let content_length = header_value(header_text, "Content-Length").unwrap_or("0").parse::<usize>().map_err(|_| "installer content length is invalid".to_string())?;
    if content_length > MAX_REQUEST_BYTES || header_end + content_length > MAX_REQUEST_BYTES { return Err("installer request body is too large".to_string()); }
    while request.len() < header_end + content_length {
        let count = stream.read(&mut buffer).map_err(|error| format!("could not read installer request body: {error}"))?;
        if count == 0 { return Err("installer request body is incomplete".to_string()); }
        request.extend_from_slice(&buffer[..count]);
    }
    request.truncate(header_end + content_length);
    Ok(request)
}

fn forbidden(stream: &mut UnixStream) {
    let _ = stream.write_all(b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\nConnection: close\r\n\r\n");
}

fn handle(mut client: UnixStream, backend_path: &Path, token: &str, expected_uid: Option<u32>) -> Result<(), String> {
    if let Some(expected_uid) = expected_uid {
        if peer_uid(&client)? != expected_uid { forbidden(&mut client); return Ok(()); }
    }
    let request = read_request(&mut client)?;
    let (method, target, headers) = request_parts(&request)?;
    if !route_allowed(method, target) || header_value(headers, "X-Kyth-Session-Token") != Some(token) { forbidden(&mut client); return Ok(()); }
    let mut backend = UnixStream::connect(backend_path).map_err(|error| format!("could not connect to installer compatibility backend: {error}"))?;
    backend.write_all(&request).map_err(|error| format!("could not forward installer request: {error}"))?;
    io::copy(&mut backend, &mut client).map_err(|error| format!("could not forward installer response: {error}"))?;
    Ok(())
}

struct ChildGuard(Child);

impl Drop for ChildGuard {
    fn drop(&mut self) { let _ = self.0.kill(); let _ = self.0.wait(); }
}

fn start_backend(token_path: &Path, backend_path: &Path) -> Result<ChildGuard, String> {
    let child = Command::new("/usr/bin/python3")
        .args(["-m", "kyth_installer.daemon", "--socket-path"])
        .arg(backend_path)
        .args(["--session-token-file"])
        .arg(token_path)
        .stdin(Stdio::null())
        .spawn()
        .map_err(|error| format!("could not start installer compatibility backend: {error}"))?;
    Ok(ChildGuard(child))
}

fn wait_for_backend(backend_path: &Path) -> Result<(), String> {
    let deadline = Instant::now() + Duration::from_secs(10);
    loop {
        match UnixStream::connect(backend_path) {
            Ok(_) => return Ok(()),
            Err(_error) if Instant::now() < deadline => thread::sleep(Duration::from_millis(25)),
            Err(error) => return Err(format!("installer compatibility backend did not start: {error}")),
        }
    }
}

pub fn run(args: &[String]) -> Result<(), String> {
    if unsafe { libc::geteuid() } != 0 { return Err("kyth-installerd must run as root".to_string()); }
    let options = options(args)?;
    let token = read_session_token(&options.session_token_file)?;
    let backend_path = PathBuf::from(format!("{}{}", options.socket_path.display(), BACKEND_SOCKET_SUFFIX));
    let _backend = start_backend(&options.session_token_file, &backend_path)?;
    wait_for_backend(&backend_path)?;
    let listener = listener(&options)?;
    for stream in listener.incoming() {
        match stream {
            Ok(stream) => {
                let token = token.clone();
                let expected_uid = options.peer_uid;
                let backend_path = backend_path.clone();
                thread::spawn(move || { if let Err(error) = handle(stream, &backend_path, &token, expected_uid) { eprintln!("installer request failed: {error}"); } });
            }
            Err(error) => return Err(format!("installer socket accept failed: {error}")),
        }
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::{options, read_session_token, route_allowed};
    use std::fs;
    use std::os::unix::fs::PermissionsExt;
    use tempfile::tempdir;

    #[test]
    fn options_require_the_native_socket_boundary() {
        let parsed = options(&["--socket-path".into(), "/run/kyth-installer/api.sock".into(), "--session-token-file".into(), "/run/kyth-installer/session-token".into()]).unwrap();
        assert_eq!(parsed.socket_path.to_str(), Some("/run/kyth-installer/api.sock"));
        assert!(parsed.socket_group.is_none());
    }

    #[test]
    fn route_allowlist_excludes_arbitrary_execution() {
        assert!(route_allowed("GET", "/api/disks"));
        assert!(route_allowed("POST", "/api/start"));
        assert!(!route_allowed("POST", "/api/exec"));
        assert!(!route_allowed("GET", "http://127.0.0.1:7777/api/disks"));
    }

    #[test]
    fn token_reader_rejects_loose_modes_and_bad_format() {
        let directory = tempdir().unwrap();
        let path = directory.path().join("token");
        fs::write(&path, "short").unwrap();
        fs::set_permissions(&path, fs::Permissions::from_mode(0o600)).unwrap();
        assert!(read_session_token(&path).is_err());
        fs::write(&path, "A".repeat(43)).unwrap();
        fs::set_permissions(&path, fs::Permissions::from_mode(0o640)).unwrap();
        assert!(read_session_token(&path).is_err());
    }
}
