//! Native root-facing installer daemon.
//!
//! This binary owns the privileged Unix socket, request authentication,
//! native job lifecycle, storage/configuration execution, recovery actions,
//! and the typed helper boundary. The Python installer tree is source-only
//! compatibility material and never binds or serves the packaged socket.

use std::ffi::CString;
use std::fs::{self, OpenOptions};
use std::io::{self, Read, Write};
use std::os::fd::AsRawFd;
use std::os::unix::fs::{FileTypeExt, MetadataExt, OpenOptionsExt, PermissionsExt};
use std::os::unix::net::{UnixListener, UnixStream};
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::sync::Arc;
use std::sync::Mutex;
use std::thread;
use std::time::Duration;

use super::installer_job::{EventReplay, JobSnapshot, JobSupervisor, StartReceipt};
use super::installer_job_executor::{NativeInstallRequest, NativePhaseExecutor};
use super::installer_plan::{build_plan, InstallerPlanInput};
use super::installer_runtime::RuntimeCoordinator;
use super::installer_storage;

const MAX_REQUEST_BYTES: usize = 16 * 1024 * 1024;
const MAX_LOG_RESPONSE_BYTES: u64 = 1024 * 1024;
fn transaction_path() -> PathBuf {
    std::env::var_os("KYTH_INSTALLER_TRANSACTION")
        .map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from("/run/kyth-installer/transaction.json"))
}

fn failure_summary_path() -> PathBuf {
    std::env::var_os("KYTH_INSTALLER_FAILURE_SUMMARY")
        .map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from("/run/kyth-installer/failure.json"))
}

fn installer_log_path() -> PathBuf {
    std::env::var_os("KYTH_INSTALLER_LOG")
        .map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from("/run/kyth-installer/log"))
}

type NativeSupervisor = JobSupervisor<NativePhaseExecutor>;

/// Live AC-power attestation from sysfs for shrink commits. Mirrors the
/// Slint shell's `on_ac_power_in`: no battery discharging and no offline
/// AC/ADP supply means on-AC; machines without a power-supply tree (desktops,
/// VMs) read as on-AC because there is nothing to gate on. Pure over an
/// explicit sysfs root so it is unit-testable.
pub(super) fn ac_online_in(root: &Path) -> bool {
    let Ok(entries) = std::fs::read_dir(root) else {
        return true;
    };
    let mut saw_battery = false;
    let mut ac_online = false;
    let mut saw_ac = false;
    for entry in entries.flatten() {
        let name = entry.file_name().to_string_lossy().into_owned();
        if name.starts_with("BAT") {
            saw_battery = true;
            if let Ok(status) = std::fs::read_to_string(entry.path().join("status")) {
                if status.trim() == "Discharging" {
                    return false;
                }
            }
        } else if name.starts_with("AC") || name.starts_with("ADP") {
            saw_ac = true;
            if let Ok(online) = std::fs::read_to_string(entry.path().join("online")) {
                if online.trim() == "1" {
                    ac_online = true;
                }
            }
        }
    }
    if saw_battery {
        // A battery-backed machine must positively report external power.
        // Missing status/AC nodes are unknown, not proof that shrinking is safe.
        saw_ac && ac_online
    } else {
        true
    }
}

/// Build the staged params for a `/api/disk/resize` op, carrying the shrink
/// attestations the commit gate demands. A GPT backup path that is not on
/// external media fails here with an honest error instead of at commit time.
/// Pure over the request value so it is unit-testable without live disks.
fn resize_op_params(
    partition: &str,
    new_size_bytes: u64,
    value: &serde_json::Value,
) -> Result<serde_json::Value, serde_json::Value> {
    let mut params = serde_json::json!({"partition": partition, "new_size_bytes": new_size_bytes});
    if let Some(backup) = value
        .get("gpt_backup_path")
        .and_then(serde_json::Value::as_str)
        .map(str::trim)
        .filter(|backup| !backup.is_empty())
    {
        if !super::installer_journal::path_on_external_media(backup) {
            return Err(
                serde_json::json!({"ok": false, "message": format!("GPT backup {backup:?} must be on external media (/run/media/…, /mnt/…) — a backup on the disk being shrunk is lost with it.")}),
            );
        }
        params["gpt_backup_path"] = serde_json::Value::String(backup.to_string());
    }
    if let Some(ntfs_clean) = value
        .get("ntfs_verified_clean")
        .and_then(serde_json::Value::as_bool)
    {
        params["ntfs_verified_clean"] = serde_json::Value::Bool(ntfs_clean);
    }
    if let Some(ac) = value
        .get("on_ac_power")
        .and_then(serde_json::Value::as_bool)
    {
        params["on_ac_power"] = serde_json::Value::Bool(ac);
    }
    Ok(params)
}

/// Replace every staged resize's client value with a live root-owned sysfs
/// reading at commit time, when the shrink gate evaluates power state.
fn stamp_shrink_power_attestation(journal: &mut super::installer_journal::PartitionJournal) {
    stamp_shrink_power_attestation_in(journal, Path::new("/sys/class/power_supply"));
}

fn stamp_shrink_power_attestation_in(
    journal: &mut super::installer_journal::PartitionJournal,
    power_root: &Path,
) {
    // The browser's value is advisory at best. Commit-time power state must
    // come from this root-owned sysfs probe, even when a client supplied a
    // forged `true` value while running on battery.
    let online = ac_online_in(power_root);
    for op in &mut journal.ops {
        if op.kind == "resize" {
            op.params["on_ac_power"] = serde_json::Value::Bool(online);
        }
    }
}

struct NativeJournalRegistry {
    active: Mutex<Option<super::installer_journal::PartitionJournal>>,
}

impl Default for NativeJournalRegistry {
    fn default() -> Self {
        Self {
            active: Mutex::new(None),
        }
    }
}

impl NativeJournalRegistry {
    fn disk(value: &serde_json::Value) -> Result<String, serde_json::Value> {
        value
            .get("disk")
            .and_then(serde_json::Value::as_str)
            .and_then(super::installer_plan::normalize_device_path)
            .ok_or_else(|| serde_json::json!({"ok": false, "message": "No disk specified."}))
    }

    fn journal_for<'a>(
        active: &'a mut Option<super::installer_journal::PartitionJournal>,
        disk: &str,
    ) -> Result<&'a mut super::installer_journal::PartitionJournal, serde_json::Value> {
        match active {
            Some(journal) if journal.disk == disk => Ok(journal),
            _ => Err(serde_json::json!({
                "ok": false,
                "message": "No active partition journal for this disk. Create a new partition table first."
            })),
        }
    }

    fn pending(&self, value: &serde_json::Value) -> Result<serde_json::Value, String> {
        let requested_disk = value
            .get("disk")
            .and_then(serde_json::Value::as_str)
            .and_then(super::installer_plan::normalize_device_path);
        let active = self
            .active
            .lock()
            .map_err(|_| "native partition journal state is unavailable".to_string())?;
        Ok(serde_json::to_value(
            active
                .as_ref()
                .filter(|journal| {
                    requested_disk
                        .as_deref()
                        .is_none_or(|disk| journal.disk == disk)
                })
                .map(super::installer_journal::PartitionJournal::pending)
                .unwrap_or_default(),
        )
        .unwrap_or_else(|_| serde_json::json!([])))
    }

    fn filesystems() -> serde_json::Value {
        serde_json::json!([
            {"id": "btrfs", "name": "Btrfs", "root_ok": true, "efi_ok": false},
            {"id": "ext4", "name": "ext4", "root_ok": false, "efi_ok": false},
            {"id": "xfs", "name": "XFS", "root_ok": false, "efi_ok": false},
            {"id": "fat32", "name": "FAT32", "root_ok": false, "efi_ok": true},
            {"id": "linux-swap", "name": "Swap", "root_ok": false, "efi_ok": false}
        ])
    }

    fn dispatch(&self, route: &str, value: serde_json::Value) -> (u16, serde_json::Value) {
        let disk = match Self::disk(&value) {
            Ok(disk) => disk,
            Err(error) => return (400, error),
        };
        let mut active = match self.active.lock() {
            Ok(active) => active,
            Err(_) => {
                return (
                    500,
                    serde_json::json!({"ok": false, "message": "native partition journal state is unavailable"}),
                )
            }
        };
        match route {
            "/api/disk/new-table" => {
                let table_type = value
                    .get("table_type")
                    .and_then(serde_json::Value::as_str)
                    .unwrap_or("gpt");
                if !matches!(table_type, "gpt" | "msdos") {
                    return (
                        400,
                        serde_json::json!({"ok": false, "message": "Table type must be 'gpt' or 'msdos'."}),
                    );
                }
                if let Err(error) = disk_exists(&disk) {
                    return (400, serde_json::json!({"ok": false, "message": error}));
                }
                let mut journal = match super::installer_journal::PartitionJournal::new(&disk) {
                    Ok(journal) => journal,
                    Err(error) => return (400, serde_json::json!({"ok": false, "message": error})),
                };
                journal.add_op("new_table", serde_json::json!({"table_type": table_type}));
                let pending = journal.ops.len();
                *active = Some(journal);
                (200, serde_json::json!({"ok": true, "pending": pending}))
            }
            "/api/disk/create" => {
                let journal = match Self::journal_for(&mut active, &disk) {
                    Ok(journal) => journal,
                    Err(error) => return (400, error),
                };
                let Some(start_bytes) =
                    value.get("start_bytes").and_then(serde_json::Value::as_u64)
                else {
                    return (
                        400,
                        serde_json::json!({"ok": false, "message": "Invalid start offset or size."}),
                    );
                };
                let Some(size_bytes) = value.get("size_bytes").and_then(serde_json::Value::as_u64)
                else {
                    return (
                        400,
                        serde_json::json!({"ok": false, "message": "Invalid start offset or size."}),
                    );
                };
                if size_bytes == 0 {
                    return (
                        400,
                        serde_json::json!({"ok": false, "message": "Invalid start offset or size."}),
                    );
                }
                let fs_type = value
                    .get("fs_type")
                    .and_then(serde_json::Value::as_str)
                    .unwrap_or("btrfs");
                if !matches!(fs_type, "btrfs" | "ext4" | "xfs" | "fat32" | "linux-swap") {
                    return (
                        400,
                        serde_json::json!({"ok": false, "message": format!("Unsupported filesystem: {fs_type}")}),
                    );
                }
                journal.add_op(
                    "create",
                    serde_json::json!({
                        "start_bytes": start_bytes,
                        "size_bytes": size_bytes,
                        "fs_type": fs_type,
                        "label": value.get("label").and_then(serde_json::Value::as_str).unwrap_or_default(),
                        "mountpoint": value.get("mountpoint").and_then(serde_json::Value::as_str).unwrap_or_default(),
                    }),
                );
                let pending = journal.ops.len();
                (
                    200,
                    serde_json::json!({"ok": true, "pending": pending, "errors": []}),
                )
            }
            "/api/disk/pending/remove" => {
                let journal = match Self::journal_for(&mut active, &disk) {
                    Ok(journal) => journal,
                    Err(error) => return (400, error),
                };
                if journal.committed {
                    return (
                        400,
                        serde_json::json!({"ok": false, "message": "Partition changes have already been committed and cannot be edited."}),
                    );
                }
                let Some(index) = value.get("index").and_then(serde_json::Value::as_u64) else {
                    return (
                        400,
                        serde_json::json!({"ok": false, "message": "Invalid pending operation index."}),
                    );
                };
                if !journal.remove_op(index as usize) {
                    return (
                        400,
                        serde_json::json!({"ok": false, "message": "Invalid pending operation index."}),
                    );
                }
                (
                    200,
                    serde_json::json!({"ok": true, "pending": journal.ops.len()}),
                )
            }
            "/api/disk/delete"
            | "/api/disk/resize"
            | "/api/disk/format"
            | "/api/disk/set-mountpoint" => {
                let journal = match Self::journal_for(&mut active, &disk) {
                    Ok(journal) => journal,
                    Err(error) => return (400, error),
                };
                let Some(partition) = value
                    .get("partition")
                    .and_then(serde_json::Value::as_str)
                    .and_then(super::installer_plan::normalize_device_path)
                else {
                    return (
                        400,
                        serde_json::json!({"ok": false, "message": "Disk and partition are required."}),
                    );
                };
                let valid = super::installer_journal::validate_target_request(
                    super::installer_journal::JournalTargetInput {
                        disk: disk.clone(),
                        partition: partition.clone(),
                    },
                );
                if !valid
                    .get("valid")
                    .and_then(serde_json::Value::as_bool)
                    .unwrap_or(false)
                {
                    return (
                        400,
                        serde_json::json!({"ok": false, "message": valid.get("error").cloned().unwrap_or_else(|| serde_json::json!("Partition target is invalid."))}),
                    );
                }
                let (kind, params) = match route {
                    "/api/disk/delete" => ("delete", serde_json::json!({"partition": partition})),
                    "/api/disk/resize" => {
                        let Some(new_size_bytes) = value
                            .get("new_size_bytes")
                            .and_then(serde_json::Value::as_u64)
                        else {
                            return (
                                400,
                                serde_json::json!({"ok": false, "message": "A new size is required."}),
                            );
                        };
                        let params = match resize_op_params(&partition, new_size_bytes, &value) {
                            Ok(params) => params,
                            Err(error) => return (400, error),
                        };
                        ("resize", params)
                    }
                    "/api/disk/format" => {
                        let fs_type = value
                            .get("fs_type")
                            .and_then(serde_json::Value::as_str)
                            .unwrap_or("btrfs");
                        if !matches!(fs_type, "btrfs" | "ext4" | "xfs" | "fat32" | "linux-swap") {
                            return (
                                400,
                                serde_json::json!({"ok": false, "message": format!("Unsupported filesystem: {fs_type}")}),
                            );
                        }
                        (
                            "format",
                            serde_json::json!({"partition": partition, "fs_type": fs_type, "label": value.get("label").and_then(serde_json::Value::as_str).unwrap_or_default()}),
                        )
                    }
                    _ => {
                        let mountpoint = value
                            .get("mountpoint")
                            .and_then(serde_json::Value::as_str)
                            .unwrap_or_default();
                        if !mountpoint.is_empty()
                            && mountpoint != "swap"
                            && !mountpoint.starts_with('/')
                        {
                            return (
                                400,
                                serde_json::json!({"ok": false, "message": "Mount point must be an absolute path (e.g. /, /home)."}),
                            );
                        }
                        (
                            "set_mountpoint",
                            serde_json::json!({"partition": partition, "mountpoint": mountpoint}),
                        )
                    }
                };
                journal.add_op(kind, params);
                (
                    200,
                    serde_json::json!({"ok": true, "pending": journal.ops.len()}),
                )
            }
            "/api/disk/commit" => {
                let mut journal = match Self::journal_for(&mut active, &disk) {
                    Ok(journal) => journal.clone(),
                    Err(error) => return (400, error),
                };
                // Commit-time AC attestation for shrinks: the journal demands
                // `on_ac_power`, and the daemon — root on the target machine —
                // is the trustworthy party to confirm it. Stamp it live here
                // (per the documented "confirmed online at commit time"
                // contract), replacing any client-supplied value.
                stamp_shrink_power_attestation(&mut journal);
                match super::installer_journal::commit_request(
                    super::installer_journal::JournalCommitInput { journal },
                ) {
                    Ok(response) => {
                        if response.get("ok").and_then(serde_json::Value::as_bool) == Some(true) {
                            if let Ok(committed) = serde_json::from_value::<
                                super::installer_journal::PartitionJournal,
                            >(
                                response["journal"].clone()
                            ) {
                                *active = Some(committed);
                            }
                            (200, response)
                        } else if response.get("errors").is_some() {
                            (400, response)
                        } else {
                            (500, response)
                        }
                    }
                    Err(error) => (500, serde_json::json!({"ok": false, "message": error})),
                }
            }
            "/api/disk/rollback" => {
                let journal = match Self::journal_for(&mut active, &disk) {
                    Ok(journal) => journal,
                    Err(error) => return (400, error),
                };
                journal.rollback_metadata();
                (200, serde_json::json!({"ok": true}))
            }
            _ => (
                404,
                serde_json::json!({"ok": false, "message": "Route not found."}),
            ),
        }
    }
}

/// Shared native job ownership for the daemon's request threads.
///
/// A supervisor is bound to one validated install request, so the registry
/// stores the active supervisor rather than a reusable executor. The slot is
/// claimed while holding this mutex, closing the race between concurrent
/// `/api/start` requests.
struct NativeJobRegistry {
    active: Mutex<Option<NativeSupervisor>>,
}

impl Default for NativeJobRegistry {
    fn default() -> Self {
        Self {
            active: Mutex::new(None),
        }
    }
}

impl NativeJobRegistry {
    fn start(&self, request: NativeInstallRequest) -> Result<StartReceipt, String> {
        let mut active = self
            .active
            .lock()
            .map_err(|_| "native installer job state is unavailable".to_string())?;
        if let Some(supervisor) = active.as_ref() {
            if supervisor.snapshot()?.worker_active {
                return Err("An installation is already running.".to_string());
            }
        }
        let supervisor = NativeSupervisor::new(NativePhaseExecutor::from_request(request)?);
        let receipt = supervisor.start()?;
        *active = Some(supervisor);
        Ok(receipt)
    }

    fn cancel(&self) -> Result<(), String> {
        let active = self
            .active
            .lock()
            .map_err(|_| "native installer job state is unavailable".to_string())?;
        active
            .as_ref()
            .ok_or_else(|| "No installation is running to cancel.".to_string())?
            .cancel()
    }

    fn snapshot(&self) -> Result<Option<JobSnapshot>, String> {
        let active = self
            .active
            .lock()
            .map_err(|_| "native installer job state is unavailable".to_string())?;
        active.as_ref().map(JobSupervisor::snapshot).transpose()
    }

    fn replay(&self, last_event_id: u64) -> Result<Option<EventReplay>, String> {
        let active = self
            .active
            .lock()
            .map_err(|_| "native installer job state is unavailable".to_string())?;
        active
            .as_ref()
            .map(|supervisor| supervisor.replay(last_event_id))
            .transpose()
    }

    fn wait_for_events(
        &self,
        last_event_id: u64,
        timeout: Duration,
    ) -> Result<Option<EventReplay>, String> {
        let active = self
            .active
            .lock()
            .map_err(|_| "native installer job state is unavailable".to_string())?;
        active
            .as_ref()
            .map(|supervisor| supervisor.wait_for_events(last_event_id, timeout))
            .transpose()
    }
}

struct Options {
    socket_path: PathBuf,
    session_token_file: PathBuf,
    socket_group: Option<String>,
    peer_uid: Option<u32>,
}

fn value(args: &[String], name: &str) -> Result<String, String> {
    let index = args
        .iter()
        .position(|arg| arg == name)
        .ok_or_else(|| format!("missing {name}"))?;
    args.get(index + 1)
        .cloned()
        .ok_or_else(|| format!("missing value for {name}"))
}

fn options(args: &[String]) -> Result<Options, String> {
    let socket_group = args
        .iter()
        .position(|arg| arg == "--socket-group")
        .map(|index| {
            args.get(index + 1)
                .cloned()
                .ok_or_else(|| "missing value for --socket-group".to_string())
        })
        .transpose()?;
    let peer_uid = args
        .iter()
        .position(|arg| arg == "--peer-uid")
        .map(|index| {
            args.get(index + 1)
                .ok_or_else(|| "missing value for --peer-uid".to_string())?
                .parse::<u32>()
                .map_err(|_| "invalid --peer-uid".to_string())
        })
        .transpose()?;
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
    let metadata = file
        .metadata()
        .map_err(|error| format!("could not stat installer session token: {error}"))?;
    if !metadata.is_file() || metadata.uid() != 0 || metadata.mode() & 0o077 != 0 {
        return Err(
            "installer session token must be a root-owned private regular file".to_string(),
        );
    }
    let mut token = String::new();
    (&file)
        .take(513)
        .read_to_string(&mut token)
        .map_err(|error| format!("could not read installer session token: {error}"))?;
    let token = token.trim();
    if !(32..=512).contains(&token.len())
        || !token
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || byte == b'_' || byte == b'-')
    {
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
        return Err(format!(
            "socket group does not exist: {}",
            name.to_string_lossy()
        ));
    }
    // SAFETY: entry was checked non-null above.
    Ok(unsafe { (*entry).gr_gid })
}

fn chown(path: &Path, gid: u32) -> Result<(), String> {
    let path = CString::new(path.as_os_str().as_encoded_bytes())
        .map_err(|_| "socket path contains NUL".to_string())?;
    // SAFETY: path is a NUL-free CString and -1 preserves the current owner.
    if unsafe { libc::chown(path.as_ptr(), u32::MAX, gid) } != 0 {
        return Err(format!(
            "could not set socket group: {}",
            io::Error::last_os_error()
        ));
    }
    Ok(())
}

fn listener(options: &Options) -> Result<UnixListener, String> {
    let parent = options
        .socket_path
        .parent()
        .ok_or_else(|| "socket path has no parent".to_string())?;
    fs::create_dir_all(parent)
        .map_err(|error| format!("could not create installer socket directory: {error}"))?;
    fs::set_permissions(parent, fs::Permissions::from_mode(0o750))
        .map_err(|error| format!("could not secure installer socket directory: {error}"))?;
    let gid = options.socket_group.as_deref().map(group_id).transpose()?;
    if let Some(gid) = gid {
        chown(parent, gid)?;
    }

    if fs::symlink_metadata(&options.socket_path).is_ok() {
        let metadata =
            fs::symlink_metadata(&options.socket_path).map_err(|error| error.to_string())?;
        if !metadata.file_type().is_socket() {
            return Err("installer socket path is not a socket".to_string());
        }
        fs::remove_file(&options.socket_path)
            .map_err(|error| format!("could not replace installer socket: {error}"))?;
    }
    let socket = UnixListener::bind(&options.socket_path)
        .map_err(|error| format!("could not bind installer socket: {error}"))?;
    fs::set_permissions(
        &options.socket_path,
        fs::Permissions::from_mode(if gid.is_some() { 0o660 } else { 0o600 }),
    )
    .map_err(|error| format!("could not secure installer socket: {error}"))?;
    if let Some(gid) = gid {
        chown(&options.socket_path, gid)?;
    }
    Ok(socket)
}

fn peer_uid(stream: &UnixStream) -> Result<u32, String> {
    let mut credentials = libc::ucred {
        pid: 0,
        uid: 0,
        gid: 0,
    };
    let mut length = std::mem::size_of::<libc::ucred>() as libc::socklen_t;
    // SAFETY: credentials and length point to valid writable storage for the
    // socket option requested from this connected Unix stream.
    let result = unsafe {
        libc::getsockopt(
            stream.as_raw_fd(),
            libc::SOL_SOCKET,
            libc::SO_PEERCRED,
            &mut credentials as *mut _ as *mut _,
            &mut length,
        )
    };
    if result != 0 {
        return Err(format!(
            "could not inspect installer peer: {}",
            io::Error::last_os_error()
        ));
    }
    Ok(credentials.uid)
}

fn route_allowed(method: &str, target: &str) -> bool {
    let path = target.split('?').next().unwrap_or(target);
    match method {
        "GET" => matches!(
            path,
            "/api/config"
                | "/api/disks"
                | "/api/partitions"
                | "/api/free-space"
                | "/api/timezones"
                | "/api/locales"
                | "/api/keymaps"
                | "/api/disk/pending"
                | "/api/disk/filesystems"
                | "/api/report"
                | "/api/runtime"
                | "/api/rescue/probe"
                | "/api/log"
                | "/api/stream"
        ),
        "POST" => matches!(
            path,
            "/api/start"
                | "/api/cancel"
                | "/api/reboot"
                | "/api/disk/new-table"
                | "/api/disk/create"
                | "/api/disk/delete"
                | "/api/disk/resize"
                | "/api/disk/format"
                | "/api/disk/set-mountpoint"
                | "/api/disk/pending/remove"
                | "/api/disk/commit"
                | "/api/disk/rollback"
                | "/api/rescue/logs-to-usb"
        ),
        _ => false,
    }
}

fn header_value<'a>(headers: &'a str, name: &str) -> Option<&'a str> {
    headers.lines().skip(1).find_map(|line| {
        let (key, value) = line.split_once(':')?;
        key.trim()
            .eq_ignore_ascii_case(name)
            .then_some(value.trim())
    })
}

fn request_parts(request: &[u8]) -> Result<(&str, &str, &str), String> {
    let header_end = header_end(request)?;
    let headers = std::str::from_utf8(&request[..header_end])
        .map_err(|_| "installer request headers are not UTF-8".to_string())?;
    let mut line = headers
        .lines()
        .next()
        .unwrap_or_default()
        .split_whitespace();
    let method = line.next().unwrap_or_default();
    let target = line.next().unwrap_or_default();
    let version = line.next().unwrap_or_default();
    if line.next().is_some()
        || method.is_empty()
        || target.is_empty()
        || !matches!(version, "HTTP/1.0" | "HTTP/1.1")
    {
        return Err("installer request line is invalid".to_string());
    }
    Ok((method, target, headers))
}

fn header_end(request: &[u8]) -> Result<usize, String> {
    request
        .windows(4)
        .position(|window| window == b"\r\n\r\n")
        .map(|position| position + 4)
        .ok_or_else(|| "installer request has no complete headers".to_string())
}

fn read_request(stream: &mut UnixStream) -> Result<Vec<u8>, String> {
    stream
        .set_read_timeout(Some(std::time::Duration::from_secs(15)))
        .map_err(|error| format!("could not set installer request timeout: {error}"))?;
    let mut request = Vec::with_capacity(4096);
    let mut buffer = [0_u8; 4096];
    let header_end = loop {
        let count = stream
            .read(&mut buffer)
            .map_err(|error| format!("could not read installer request: {error}"))?;
        if count == 0 {
            return Err("installer client closed before sending a request".to_string());
        }
        request.extend_from_slice(&buffer[..count]);
        if request.len() > MAX_REQUEST_BYTES {
            return Err("installer request is too large".to_string());
        }
        if let Some(position) = request.windows(4).position(|window| window == b"\r\n\r\n") {
            break position + 4;
        }
    };
    let header_text = std::str::from_utf8(&request[..header_end - 4])
        .map_err(|_| "installer request headers are not UTF-8".to_string())?;
    let content_length = header_value(header_text, "Content-Length")
        .unwrap_or("0")
        .parse::<usize>()
        .map_err(|_| "installer content length is invalid".to_string())?;
    if content_length > MAX_REQUEST_BYTES || header_end + content_length > MAX_REQUEST_BYTES {
        return Err("installer request body is too large".to_string());
    }
    while request.len() < header_end + content_length {
        let count = stream
            .read(&mut buffer)
            .map_err(|error| format!("could not read installer request body: {error}"))?;
        if count == 0 {
            return Err("installer request body is incomplete".to_string());
        }
        request.extend_from_slice(&buffer[..count]);
    }
    request.truncate(header_end + content_length);
    Ok(request)
}

fn forbidden(stream: &mut UnixStream) {
    let _ = stream
        .write_all(b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\nConnection: close\r\n\r\n");
}

fn bad_start_request(stream: &mut UnixStream, message: &str) {
    let body = serde_json::json!({"started": false, "message": message}).to_string();
    let response = format!(
        "HTTP/1.1 400 Bad Request\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{}",
        body.len(), body
    );
    let _ = stream.write_all(response.as_bytes());
}

fn json_response(stream: &mut UnixStream, status: &str, value: &serde_json::Value) {
    let body = value.to_string();
    let response = format!(
        "HTTP/1.1 {status}\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{body}",
        body.len()
    );
    let _ = stream.write_all(response.as_bytes());
}

fn json_status(status: u16) -> &'static str {
    match status {
        200 => "200 OK",
        400 => "400 Bad Request",
        404 => "404 Not Found",
        409 => "409 Conflict",
        500 => "500 Internal Server Error",
        503 => "503 Service Unavailable",
        _ => "500 Internal Server Error",
    }
}

fn add_display_sizes(value: &mut serde_json::Value) {
    let Some(items) = value.as_array_mut() else {
        return;
    };
    for item in items {
        let Some(object) = item.as_object_mut() else {
            continue;
        };
        let Some(size) = object.get("size_bytes").and_then(serde_json::Value::as_u64) else {
            continue;
        };
        object.insert(
            "size".to_string(),
            serde_json::json!(kyth_shared::transfer::human_bytes(size as f64)),
        );
    }
}

fn command_output(program: &str, args: &[&str]) -> Result<String, String> {
    let output = Command::new(program)
        .args(args)
        .output()
        .map_err(|error| format!("could not run {program}: {error}"))?;
    if !output.status.success() {
        return Err(format!(
            "{program} failed with exit code {}: {}",
            output.status.code().unwrap_or(1),
            String::from_utf8_lossy(&output.stderr).trim()
        ));
    }
    String::from_utf8(output.stdout).map_err(|_| format!("{program} returned non-UTF-8 output"))
}

fn disk_exists(disk: &str) -> Result<(), String> {
    let disk = super::installer_plan::normalize_device_path(disk)
        .ok_or_else(|| "Invalid or unsafe disk.".to_string())?;
    let output = Command::new("/usr/bin/lsblk")
        .args(["--noheadings", "--output", "TYPE", &disk])
        .output()
        .map_err(|error| format!("could not inspect {disk}: {error}"))?;
    if !output.status.success()
        || !String::from_utf8_lossy(&output.stdout)
            .lines()
            .any(|line| line.trim() == "disk")
    {
        return Err("Invalid or unsafe disk.".to_string());
    }
    Ok(())
}

fn request_body(request: &[u8]) -> Result<serde_json::Value, String> {
    let end = header_end(request)?;
    serde_json::from_slice(&request[end..])
        .map_err(|error| format!("Invalid installer request JSON: {error}"))
}

fn run_native_helper(
    operation: &str,
    value: &serde_json::Value,
) -> Result<serde_json::Value, String> {
    if operation != "recovery-export" {
        return Err("unsupported native helper operation".to_string());
    }
    let input = serde_json::to_vec(value)
        .map_err(|error| format!("could not encode native helper request: {error}"))?;
    let mut command = Command::new("/usr/bin/kyth-installer-exec");
    command
        .args(["--operation", operation])
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    let mut child = command
        .spawn()
        .map_err(|error| format!("could not start native helper: {error}"))?;
    if let Some(mut stdin) = child.stdin.take() {
        stdin
            .write_all(&input)
            .map_err(|error| format!("could not provide native helper input: {error}"))?;
    }
    let output = child
        .wait_with_output()
        .map_err(|error| format!("could not wait for native helper: {error}"))?;
    if !output.status.success() {
        let detail = String::from_utf8_lossy(&output.stderr).trim().to_string();
        return Err(if detail.is_empty() {
            format!("native helper exited with status {}", output.status)
        } else {
            detail
        });
    }
    serde_json::from_slice(&output.stdout)
        .map_err(|error| format!("native helper returned malformed JSON: {error}"))
}

fn run_native_action(operation: &str, value: &serde_json::Value) -> Result<(), String> {
    let input = serde_json::to_vec(value)
        .map_err(|error| format!("could not encode native {operation} request: {error}"))?;
    let mut child = Command::new("/usr/bin/kyth-installer-exec")
        .args(["--operation", operation])
        .stdin(Stdio::piped())
        .stdout(Stdio::null())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|error| format!("could not start native {operation}: {error}"))?;
    if let Some(mut stdin) = child.stdin.take() {
        stdin
            .write_all(&input)
            .map_err(|error| format!("could not provide native {operation} input: {error}"))?;
    }
    let output = child
        .wait_with_output()
        .map_err(|error| format!("could not wait for native {operation}: {error}"))?;
    if output.status.success() {
        return Ok(());
    }
    let detail = String::from_utf8_lossy(&output.stderr).trim().to_string();
    Err(if detail.is_empty() {
        format!("native {operation} exited with status {}", output.status)
    } else {
        detail
    })
}

fn first_usb_mount() -> Option<String> {
    let output = command_output(
        "/usr/bin/findmnt",
        &["-R", "-n", "-o", "TARGET", "/run/media"],
    )
    .ok()?;
    output.lines().map(str::trim).find_map(|path| {
        let path = Path::new(path);
        (path.starts_with("/run/media/") && path.is_dir() && !path.is_symlink())
            .then(|| path.to_string_lossy().into_owned())
    })
}

fn native_rescue_probe() -> serde_json::Value {
    let transaction = fs::read_to_string(transaction_path())
        .ok()
        .and_then(|contents| serde_json::from_str::<serde_json::Value>(&contents).ok())
        .filter(serde_json::Value::is_object)
        .unwrap_or_else(|| serde_json::json!({}));
    let status = transaction
        .get("status")
        .and_then(serde_json::Value::as_str);
    let mut probe = serde_json::json!({
        "log_tail": "",
        "sgdisk_verify": "",
        "efibootmgr": "",
        "transaction": transaction,
        "bootc_status": "",
        "rescue_guidance": crate::installer_recovery::rescue_guidance(status),
    });
    if let Ok(contents) = fs::read_to_string(installer_log_path()) {
        let lines = contents.lines().collect::<Vec<_>>();
        probe["log_tail"] = serde_json::json!(lines[lines.len().saturating_sub(80)..].join("\n"));
    }
    if let Some(disk) = probe["transaction"]["disk"]
        .as_str()
        .and_then(crate::installer_plan::normalize_device_path)
    {
        if let Ok(output) = command_output("/usr/sbin/sgdisk", &["--verify", &disk]) {
            probe["sgdisk_verify"] = serde_json::json!(output);
        }
    }
    if let Ok(output) = command_output("/usr/bin/efibootmgr", &["-v"]) {
        probe["efibootmgr"] = serde_json::json!(output);
    }
    if let Ok(output) = command_output("/usr/bin/bootc", &["status", "--json"]) {
        probe["bootc_status"] = serde_json::json!(output.chars().take(8000).collect::<String>());
        probe["bootc_status_summary"] = crate::installer_recovery::bootc_status_summary(&output);
    }
    probe
}

fn findmnt_sources(path: &str, recursive: bool) -> Result<Vec<String>, String> {
    let mut args = Vec::with_capacity(5);
    if recursive {
        args.push("-R");
    }
    args.extend(["-n", "-o", "SOURCE", path]);
    let output = Command::new("/usr/bin/findmnt")
        .args(args)
        .output()
        .map_err(|error| format!("could not run findmnt: {error}"))?;
    // findmnt uses exit code 1 for a path with no matching mount. That is a
    // normal result for optional live-media paths, unlike a probe failure.
    if !output.status.success() && output.status.code() != Some(1) {
        return Err(format!(
            "findmnt failed with exit code {}: {}",
            output.status.code().unwrap_or(1),
            String::from_utf8_lossy(&output.stderr).trim()
        ));
    }
    Ok(String::from_utf8(output.stdout)
        .map_err(|_| "findmnt returned non-UTF-8 output".to_string())?
        .lines()
        .map(str::trim)
        .filter(|source| source.starts_with("/dev/"))
        .map(str::to_string)
        .collect())
}

fn storage_lsblk_args(disk: Option<&str>) -> Vec<String> {
    let mut args = vec![
        "--json".to_string(),
        "--bytes".to_string(),
        "--paths".to_string(),
        "--output".to_string(),
        "NAME,SIZE,TYPE,FSTYPE,PARTTYPE,PARTN,LABEL,MOUNTPOINT,MOUNTPOINTS,START,RO,MODEL,TRAN,ROTA,RM,PTTYPE,PKNAME".to_string(),
    ];
    if let Some(disk) = disk {
        args.push(disk.to_string());
    }
    args
}

fn read_only_storage_route(
    method: &str,
    target: &str,
    runtime: &RuntimeCoordinator,
) -> Result<Option<serde_json::Value>, String> {
    if method != "GET" {
        return Ok(None);
    }
    let path = target.split('?').next().unwrap_or(target);
    match path {
        "/api/config" => Ok(Some(super::installer_readonly::config())),
        "/api/timezones" => Ok(Some(
            serde_json::to_value(super::installer_readonly::timezones())
                .map_err(|error| format!("could not serialize timezone inventory: {error}"))?,
        )),
        "/api/locales" => Ok(Some(
            serde_json::to_value(super::installer_readonly::locales())
                .map_err(|error| format!("could not serialize locale inventory: {error}"))?,
        )),
        "/api/keymaps" => Ok(Some(
            serde_json::to_value(super::installer_readonly::keymaps())
                .map_err(|error| format!("could not serialize keymap inventory: {error}"))?,
        )),
        "/api/runtime" => Ok(Some(serde_json::to_value(runtime.snapshot()?).map_err(
            |error| format!("could not serialize installer runtime: {error}"),
        )?)),
        "/api/disks" => {
            let disk_snapshot = command_output(
                "/usr/bin/lsblk",
                &storage_lsblk_args(None)
                    .iter()
                    .map(String::as_str)
                    .collect::<Vec<_>>(),
            )?;
            let ancestry_snapshot = command_output(
                "/usr/bin/lsblk",
                &[
                    "--json",
                    "--bytes",
                    "--paths",
                    "--output",
                    "NAME,PKNAME,TYPE",
                ],
            )?;
            let mut protected_sources = Vec::new();
            for mount in [
                "/",
                "/boot",
                "/boot/efi",
                "/sysroot",
                "/run/initramfs/live",
                "/run/initramfs/iso",
            ] {
                protected_sources.extend(findmnt_sources(mount, false)?);
            }
            protected_sources.extend(findmnt_sources("/run/initramfs", true)?);
            protected_sources.extend(findmnt_sources("/run/media", true)?);
            let current_source = findmnt_sources("/", false)?.into_iter().next();
            let records = installer_storage::runtime_disks_from_snapshots(
                &disk_snapshot,
                &ancestry_snapshot,
                &protected_sources,
                current_source.as_deref(),
            )?;
            let mut value = serde_json::to_value(records)
                .map_err(|error| format!("could not serialize disk inventory: {error}"))?;
            add_display_sizes(&mut value);
            Ok(Some(value))
        }
        "/api/partitions" => {
            let Some(disk) = query_value(target, "disk") else {
                return Ok(Some(serde_json::json!([])));
            };
            let disk = super::installer_plan::normalize_device_path(&disk)
                .ok_or_else(|| "invalid disk query path".to_string())?;
            let args = storage_lsblk_args(Some(&disk));
            let snapshot = command_output(
                "/usr/bin/lsblk",
                &args.iter().map(String::as_str).collect::<Vec<_>>(),
            )?;
            let mut value =
                serde_json::to_value(installer_storage::parse_partitions(&snapshot)?)
                    .map_err(|error| format!("could not serialize partition inventory: {error}"))?;
            add_display_sizes(&mut value);
            Ok(Some(value))
        }
        "/api/free-space" => {
            let Some(disk) = query_value(target, "disk") else {
                return Ok(Some(serde_json::json!([])));
            };
            let disk = super::installer_plan::normalize_device_path(&disk)
                .ok_or_else(|| "invalid disk query path".to_string())?;
            let args = storage_lsblk_args(Some(&disk));
            let snapshot = command_output(
                "/usr/bin/lsblk",
                &args.iter().map(String::as_str).collect::<Vec<_>>(),
            )?;
            let sector = command_output("/usr/bin/blockdev", &["--getss", &disk])?
                .trim()
                .parse::<u64>()
                .map_err(|_| "blockdev returned an invalid sector size".to_string())?;
            let mut value =
                serde_json::to_value(installer_storage::free_regions(&snapshot, &disk, sector)?)
                    .map_err(|error| {
                        format!("could not serialize free-space inventory: {error}")
                    })?;
            add_display_sizes(&mut value);
            Ok(Some(value))
        }
        _ => Ok(None),
    }
}

fn query_value(target: &str, name: &str) -> Option<String> {
    let encoded = target
        .split_once('?')?
        .1
        .split('&')
        .find_map(|part| part.strip_prefix(&format!("{name}=")))?;
    let bytes = encoded.as_bytes();
    let mut decoded = Vec::with_capacity(bytes.len());
    let mut index = 0;
    while index < bytes.len() {
        match bytes[index] {
            b'+' => {
                decoded.push(b' ');
                index += 1;
            }
            b'%' => {
                let hex = bytes.get(index + 1..index + 3)?;
                let digits = std::str::from_utf8(hex).ok()?;
                decoded.push(u8::from_str_radix(digits, 16).ok()?);
                index += 3;
            }
            byte => {
                decoded.push(byte);
                index += 1;
            }
        }
    }
    String::from_utf8(decoded).ok()
}

fn native_pending_request(target: &str) -> serde_json::Value {
    query_value(target, "disk")
        .map(|disk| serde_json::json!({"disk": disk}))
        .unwrap_or_else(|| serde_json::json!({}))
}

fn rebuild_request(request: &[u8], body: &[u8]) -> Result<Vec<u8>, String> {
    let end = header_end(request)?;
    let headers = std::str::from_utf8(&request[..end - 4])
        .map_err(|_| "installer request headers are not UTF-8".to_string())?;
    let retained = headers
        .lines()
        .filter(|line| {
            line.split_once(':')
                .map(|(name, _)| !name.trim().eq_ignore_ascii_case("Content-Length"))
                .unwrap_or(true)
        })
        .collect::<Vec<_>>()
        .join("\r\n");
    let mut rebuilt = format!("{retained}\r\nContent-Length: {}\r\n\r\n", body.len()).into_bytes();
    rebuilt.extend_from_slice(body);
    Ok(rebuilt)
}

/// Normalize only the pure storage portion of an authenticated start request.
///
/// The native executor repeats live discovery, current-disk policy, user
/// acknowledgements, locale checks, and every destructive safety check. This
/// boundary owns the request shape and canonical device/region projection so
/// malformed paths and impossible guided-plan values never reach mutation.
fn normalize_start_request(request: &[u8]) -> Result<Vec<u8>, String> {
    let (method, target, _headers) = request_parts(request)?;
    let path = target.split('?').next().unwrap_or(target);
    if method != "POST" || path != "/api/start" {
        return Ok(request.to_vec());
    }

    let end = header_end(request)?;
    let mut value: serde_json::Value = serde_json::from_slice(&request[end..])
        .map_err(|error| format!("Invalid installer request JSON: {error}"))?;
    let input: InstallerPlanInput = serde_json::from_value(value.clone())
        .map_err(|error| format!("Invalid installer plan: {error}"))?;
    let plan = build_plan(input)?;
    let object = value
        .as_object_mut()
        .ok_or_else(|| "Installer start request must be a JSON object.".to_string())?;

    object.insert("disk".to_string(), serde_json::json!(plan.disk));
    object.insert("install_mode".to_string(), serde_json::json!(plan.mode));
    object.insert(
        "target_partition".to_string(),
        serde_json::json!(plan.target_partition.unwrap_or_default()),
    );
    object.insert(
        "resize_partition".to_string(),
        serde_json::json!(plan.resize_partition.unwrap_or_default()),
    );
    object.insert(
        "resize_gib".to_string(),
        serde_json::json!(plan.resize_bytes / (1024 * 1024 * 1024)),
    );
    object.insert(
        "free_region_start".to_string(),
        serde_json::json!(plan.free_region_start.unwrap_or_default()),
    );
    object.insert(
        "free_region_end".to_string(),
        serde_json::json!(plan.free_region_end.unwrap_or_default()),
    );
    let body = serde_json::to_vec(&value)
        .map_err(|error| format!("Could not serialize normalized installer request: {error}"))?;
    rebuild_request(request, &body)
}

/// Validate and construct the native executor at the daemon boundary.
///
/// This is deliberately separate from route handling so the eventual native
/// cutover can atomically install a request-specific supervisor only after all
/// typed plans have passed validation.
fn native_executor_from_start(request: &[u8]) -> Result<NativePhaseExecutor, String> {
    let (method, target, _headers) = request_parts(request)?;
    if method != "POST" || target.split('?').next().unwrap_or(target) != "/api/start" {
        return Err("native executor requires POST /api/start".to_string());
    }
    let end = header_end(request)?;
    let value: serde_json::Value = serde_json::from_slice(&request[end..])
        .map_err(|error| format!("Invalid installer request JSON: {error}"))?;
    NativePhaseExecutor::from_request(NativeInstallRequest::from_http(value)?)
}

fn native_request_from_start(request: &[u8]) -> Result<NativeInstallRequest, String> {
    let (method, target, _headers) = request_parts(request)?;
    if method != "POST" || target.split('?').next().unwrap_or(target) != "/api/start" {
        return Err("native request requires POST /api/start".to_string());
    }
    let end = header_end(request)?;
    let value: serde_json::Value = serde_json::from_slice(&request[end..])
        .map_err(|error| format!("Invalid installer request JSON: {error}"))?;
    validate_start_acknowledgements(&value)?;
    NativeInstallRequest::from_http(value)
}

/// The React review page is not the safety boundary. Require its explicit
/// backup, erase, and login credentials again at the privileged API before
/// claiming the install slot or touching storage.
fn validate_start_acknowledgements(value: &serde_json::Value) -> Result<(), String> {
    let object = value
        .as_object()
        .ok_or_else(|| "Installer start request must be a JSON object.".to_string())?;
    if object
        .get("confirm_backup")
        .and_then(serde_json::Value::as_bool)
        != Some(true)
    {
        return Err(
            "Confirm that you have backed up anything you want to keep before installing."
                .to_string(),
        );
    }
    if object
        .get("confirm_erase")
        .and_then(serde_json::Value::as_bool)
        != Some(true)
    {
        return Err(
            "Confirm that the selected target may be erased before installing.".to_string(),
        );
    }
    if object
        .get("username")
        .and_then(serde_json::Value::as_str)
        .is_none_or(|username| username.trim().is_empty())
    {
        return Err("A login username is required to install KythOS.".to_string());
    }
    if object
        .get("password")
        .and_then(serde_json::Value::as_str)
        .is_none_or(str::is_empty)
    {
        return Err("A login password is required to install KythOS.".to_string());
    }
    Ok(())
}

fn native_report(snapshot: &JobSnapshot) -> Result<serde_json::Value, String> {
    let mut value = serde_json::json!({
        "job_id": snapshot.job_id,
        "lifecycle": snapshot.runtime.lifecycle,
        "phase": snapshot.runtime.phase,
        "cancel_requested": snapshot.runtime.cancel_requested,
        "worker_active": snapshot.worker_active,
        "terminal_event_id": snapshot.terminal_event_id,
        "status": match snapshot.runtime.lifecycle {
            super::installer_runtime::Lifecycle::Done => "complete",
            super::installer_runtime::Lifecycle::Failed => "failed",
            super::installer_runtime::Lifecycle::Idle => "idle",
            _ => "installing",
        },
        "message": "Native installer job state",
    });
    if let Ok(contents) = fs::read_to_string(transaction_path()) {
        if let Ok(transaction) = serde_json::from_str::<serde_json::Value>(&contents) {
            if transaction.is_object() {
                value = transaction;
            }
        }
    }
    Ok(value)
}

fn native_log(mut client: UnixStream) -> Result<(), String> {
    let path = installer_log_path();
    let body = match OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_NOFOLLOW)
        .open(&path)
    {
        Ok(file) => {
            let mut bytes = Vec::new();
            file.take(MAX_LOG_RESPONSE_BYTES)
                .read_to_end(&mut bytes)
                .map_err(|error| format!("could not read native installer log: {error}"))?;
            String::from_utf8_lossy(&bytes).into_owned()
        }
        Err(error) => format!("Installer log is not available yet: {error}\n"),
    };
    let response = format!(
        "HTTP/1.1 200 OK\r\nContent-Type: text/plain; charset=utf-8\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{}",
        body.len(), body
    );
    client
        .write_all(response.as_bytes())
        .map_err(|error| format!("could not write native installer log: {error}"))
}

fn native_stream(
    mut client: UnixStream,
    registry: &NativeJobRegistry,
    last_event_id: u64,
) -> Result<(), String> {
    client
        .write_all(
            b"HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\nCache-Control: no-cache\r\nX-Accel-Buffering: no\r\nConnection: close\r\n\r\n",
        )
        .map_err(|error| format!("could not write native stream headers: {error}"))?;
    let mut sent = last_event_id.saturating_add(1);
    loop {
        let replay = registry
            .replay(sent.saturating_sub(1))?
            .or_else(|| {
                Some(EventReplay {
                    events: Vec::new(),
                    next_event_id: sent,
                    reset_required: false,
                })
            })
            .expect("native stream replay fallback is always present");
        if replay.reset_required {
            sent = replay.events.first().map(|event| event.id).unwrap_or(sent);
        }
        for event in replay.events {
            let payload = serde_json::to_string(&event)
                .map_err(|error| format!("could not encode native installer event: {error}"))?;
            let frame = format!("id: {}\ndata: {payload}\n\n", event.id);
            client
                .write_all(frame.as_bytes())
                .and_then(|_| client.flush())
                .map_err(|error| format!("could not forward native installer event: {error}"))?;
            sent = event.id.saturating_add(1);
            if matches!(
                event.kind,
                super::installer_job::JobEventKind::Done { .. }
                    | super::installer_job::JobEventKind::Error { .. }
            ) {
                return Ok(());
            }
        }
        if let Some(replay) =
            registry.wait_for_events(sent.saturating_sub(1), Duration::from_secs(15))?
        {
            if replay.events.is_empty() && !replay.reset_required {
                client
                    .write_all(b":ka\n\n")
                    .and_then(|_| client.flush())
                    .map_err(|error| format!("could not write native stream keepalive: {error}"))?;
            }
        } else {
            client
                .write_all(b":ka\n\n")
                .and_then(|_| client.flush())
                .map_err(|error| format!("could not write native stream keepalive: {error}"))?;
        }
    }
}

fn handle(
    mut client: UnixStream,
    token: &str,
    expected_uid: Option<u32>,
    runtime: Arc<RuntimeCoordinator>,
    native_registry: Arc<NativeJobRegistry>,
    native_journal: Arc<NativeJournalRegistry>,
    storage_gate: Arc<Mutex<()>>,
) -> Result<(), String> {
    if let Some(expected_uid) = expected_uid {
        if peer_uid(&client)? != expected_uid {
            forbidden(&mut client);
            return Ok(());
        }
    }
    let request = read_request(&mut client)?;
    let (method, target, headers) = request_parts(&request)?;
    if !route_allowed(method, target)
        || header_value(headers, "X-Kyth-Session-Token") != Some(token)
    {
        forbidden(&mut client);
        return Ok(());
    }
    if method == "GET" && target.split('?').next().unwrap_or(target) == "/api/runtime" {
        if let Some(snapshot) = native_registry.snapshot()? {
            let value = serde_json::to_value(snapshot.runtime).map_err(|error| {
                format!("could not serialize native installer runtime: {error}")
            })?;
            json_response(&mut client, "200 OK", &value);
            return Ok(());
        }
    }
    match read_only_storage_route(method, target, &runtime) {
        Ok(Some(value)) => {
            json_response(&mut client, "200 OK", &value);
            return Ok(());
        }
        Err(error)
            if method == "GET"
                && matches!(
                    target.split('?').next().unwrap_or(target),
                    "/api/disks" | "/api/partitions" | "/api/free-space"
                ) =>
        {
            json_response(
                &mut client,
                "503 Service Unavailable",
                &serde_json::json!({"error": error}),
            );
            return Ok(());
        }
        Ok(None) => {}
        Err(error) => return Err(error),
    }
    let request = match normalize_start_request(&request) {
        Ok(request) => request,
        Err(error) => {
            if method == "POST" && target.split('?').next().unwrap_or(target) == "/api/start" {
                bad_start_request(&mut client, &error);
                return Ok(());
            }
            return Err(error);
        }
    };
    let route = target.split('?').next().unwrap_or(target);
    if method == "GET" && route == "/api/disk/pending" {
        match native_journal.pending(&native_pending_request(target)) {
            Ok(value) => json_response(&mut client, "200 OK", &value),
            Err(error) => json_response(
                &mut client,
                "500 Internal Server Error",
                &serde_json::json!({"ok": false, "message": error}),
            ),
        }
        return Ok(());
    }
    if method == "GET" && route == "/api/disk/filesystems" {
        json_response(&mut client, "200 OK", &NativeJournalRegistry::filesystems());
        return Ok(());
    }
    if method == "POST"
        && matches!(
            route,
            "/api/disk/new-table"
                | "/api/disk/create"
                | "/api/disk/delete"
                | "/api/disk/resize"
                | "/api/disk/format"
                | "/api/disk/set-mountpoint"
                | "/api/disk/pending/remove"
                | "/api/disk/commit"
                | "/api/disk/rollback"
        )
    {
        // Serialize partition commits against install start. Checking the
        // worker state without this shared gate leaves a check-then-act race:
        // an install can begin after the check but before the journal writes.
        let _storage_guard = storage_gate
            .lock()
            .map_err(|_| "installer storage operation gate is unavailable".to_string())?;
        if native_registry
            .snapshot()?
            .is_some_and(|snapshot| snapshot.worker_active)
        {
            json_response(
                &mut client,
                "409 Conflict",
                &serde_json::json!({
                    "ok": false,
                    "message": "Partition changes are locked while installation is running."
                }),
            );
            return Ok(());
        }
        let body = match request_body(&request) {
            Ok(value) if value.is_object() => value,
            Ok(_) => {
                json_response(
                    &mut client,
                    "400 Bad Request",
                    &serde_json::json!({
                        "ok": false,
                        "message": "Partition request must be a JSON object."
                    }),
                );
                return Ok(());
            }
            Err(error) => {
                json_response(
                    &mut client,
                    "400 Bad Request",
                    &serde_json::json!({"ok": false, "message": error}),
                );
                return Ok(());
            }
        };
        let (status, value) = native_journal.dispatch(route, body);
        json_response(&mut client, json_status(status), &value);
        return Ok(());
    }
    if method == "GET" && route == "/api/report" {
        if let Some(snapshot) = native_registry.snapshot()? {
            let value = native_report(&snapshot)?;
            json_response(&mut client, "200 OK", &value);
            return Ok(());
        }
        let value = match fs::read_to_string(transaction_path()) {
            Ok(contents) => serde_json::from_str(&contents)
                .map_err(|error| format!("could not decode installer transaction: {error}"))?,
            Err(error) if error.kind() == io::ErrorKind::NotFound => serde_json::json!({}),
            Err(error) => return Err(format!("could not read installer transaction: {error}")),
        };
        json_response(&mut client, "200 OK", &value);
        return Ok(());
    }
    if method == "GET" && route == "/api/rescue/probe" {
        let value = native_rescue_probe();
        json_response(&mut client, "200 OK", &value);
        return Ok(());
    }
    if method == "GET" && route == "/api/log" {
        return native_log(client);
    }
    if method == "POST" && route == "/api/rescue/logs-to-usb" {
        let body = match request_body(&request) {
            Ok(value) if value.is_object() => value,
            Ok(_) => {
                json_response(
                    &mut client,
                    "400 Bad Request",
                    &serde_json::json!({"ok": false, "message": "Recovery export request must be a JSON object."}),
                );
                return Ok(());
            }
            Err(error) => {
                json_response(
                    &mut client,
                    "400 Bad Request",
                    &serde_json::json!({"ok": false, "message": error}),
                );
                return Ok(());
            }
        };
        let usb_mount = body
            .get("usb_mount")
            .and_then(serde_json::Value::as_str)
            .filter(|value| !value.trim().is_empty())
            .map(str::to_string)
            .or_else(first_usb_mount);
        let Some(usb_mount) = usb_mount else {
            json_response(
                &mut client,
                "400 Bad Request",
                &serde_json::json!({
                    "ok": false,
                    "message": "No USB drive found. Insert a USB stick and try again."
                }),
            );
            return Ok(());
        };
        let export = serde_json::json!({
            "usb_mount": usb_mount,
            "log_path": installer_log_path(),
            "transaction_path": transaction_path(),
            "failure_summary_path": failure_summary_path(),
        });
        match run_native_helper("recovery-export", &export) {
            Ok(value) => json_response(&mut client, "200 OK", &value),
            Err(error) => json_response(
                &mut client,
                "500 Internal Server Error",
                &serde_json::json!({"ok": false, "message": error}),
            ),
        }
        return Ok(());
    }
    if method == "POST" && route == "/api/reboot" {
        let _storage_guard = storage_gate
            .lock()
            .map_err(|_| "installer storage operation gate is unavailable".to_string())?;
        if native_registry
            .snapshot()?
            .is_some_and(|snapshot| snapshot.worker_active)
        {
            json_response(
                &mut client,
                "409 Conflict",
                &serde_json::json!({
                    "ok": false,
                    "error": "Cannot reboot while installation is running."
                }),
            );
            return Ok(());
        }
        match run_native_action("reboot", &serde_json::json!({})) {
            Ok(()) => json_response(&mut client, "200 OK", &serde_json::json!({"ok": true})),
            Err(error) => json_response(
                &mut client,
                "500 Internal Server Error",
                &serde_json::json!({"ok": false, "error": error}),
            ),
        }
        return Ok(());
    }
    if method == "POST" && route == "/api/start" {
        let _storage_guard = storage_gate
            .lock()
            .map_err(|_| "installer storage operation gate is unavailable".to_string())?;
        let native_request = match native_request_from_start(&request) {
            Ok(request) => request,
            Err(error) => {
                bad_start_request(&mut client, &error);
                return Ok(());
            }
        };
        match native_registry.start(native_request) {
            Ok(receipt) => {
                json_response(
                    &mut client,
                    "200 OK",
                    &serde_json::json!({
                        "started": true,
                        "job_id": receipt.job_id,
                        "first_event_id": receipt.first_event_id,
                    }),
                );
            }
            Err(error) if error.contains("already running") => {
                json_response(
                    &mut client,
                    "409 Conflict",
                    &serde_json::json!({"started": false, "message": error}),
                );
            }
            Err(error) => {
                json_response(
                    &mut client,
                    "400 Bad Request",
                    &serde_json::json!({"started": false, "message": error}),
                );
            }
        }
        return Ok(());
    }
    if method == "POST" && route == "/api/cancel" {
        if native_registry.snapshot()?.is_none() {
            json_response(
                &mut client,
                "409 Conflict",
                &serde_json::json!({
                    "ok": false,
                    "message": "No installation is running to cancel."
                }),
            );
            return Ok(());
        }
        match native_registry.cancel() {
            Ok(()) => json_response(
                &mut client,
                "200 OK",
                &serde_json::json!({
                    "ok": true,
                    "message": "Cancellation requested."
                }),
            ),
            Err(error) => json_response(
                &mut client,
                "409 Conflict",
                &serde_json::json!({"ok": false, "message": error}),
            ),
        }
        return Ok(());
    }
    if method == "GET" && route == "/api/stream" {
        if native_registry.snapshot()?.is_some() {
            let last_event_id = header_value(headers, "Last-Event-ID")
                .and_then(|value| value.parse::<u64>().ok())
                .unwrap_or(0);
            return native_stream(client, &native_registry, last_event_id);
        }
        json_response(
            &mut client,
            "409 Conflict",
            &serde_json::json!({"error": "No installation is running."}),
        );
        return Ok(());
    }
    json_response(
        &mut client,
        "404 Not Found",
        &serde_json::json!({"ok": false, "message": "Route not found."}),
    );
    Ok(())
}

pub fn run(args: &[String]) -> Result<(), String> {
    if unsafe { libc::geteuid() } != 0 {
        return Err("kyth-installerd must run as root".to_string());
    }
    let options = options(args)?;
    let token = read_session_token(&options.session_token_file)?;
    let listener = listener(&options)?;
    let runtime = Arc::new(RuntimeCoordinator::default());
    let native_registry = Arc::new(NativeJobRegistry::default());
    let native_journal = Arc::new(NativeJournalRegistry::default());
    let storage_gate = Arc::new(Mutex::new(()));
    for stream in listener.incoming() {
        match stream {
            Ok(stream) => {
                if let Err(error) =
                    stream.set_read_timeout(Some(std::time::Duration::from_secs(15)))
                {
                    eprintln!("could not set installer client timeout: {error}");
                    continue;
                }
                let token = token.clone();
                let expected_uid = options.peer_uid;
                let runtime = Arc::clone(&runtime);
                let native_registry = Arc::clone(&native_registry);
                let native_journal = Arc::clone(&native_journal);
                let storage_gate = Arc::clone(&storage_gate);
                thread::spawn(move || {
                    if let Err(error) = handle(
                        stream,
                        &token,
                        expected_uid,
                        runtime,
                        native_registry,
                        native_journal,
                        storage_gate,
                    ) {
                        eprintln!("installer request failed: {error}");
                    }
                });
            }
            Err(error) => return Err(format!("installer socket accept failed: {error}")),
        }
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::{
        json_status, native_executor_from_start, native_request_from_start,
        normalize_start_request, options, query_value, read_session_token, route_allowed,
        NativeJournalRegistry,
    };
    use serde_json::Value;
    use std::fs;
    use std::os::unix::fs::PermissionsExt;
    use tempfile::tempdir;

    #[test]
    fn options_require_the_native_socket_boundary() {
        let parsed = options(&[
            "--socket-path".into(),
            "/run/kyth-installer/api.sock".into(),
            "--session-token-file".into(),
            "/run/kyth-installer/session-token".into(),
        ])
        .unwrap();
        assert_eq!(
            parsed.socket_path.to_str(),
            Some("/run/kyth-installer/api.sock")
        );
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
    fn preserves_service_unavailable_status_for_storage_failures() {
        assert_eq!(json_status(503), "503 Service Unavailable");
    }

    #[test]
    fn query_value_decodes_encoded_device_paths_and_rejects_malformed_escapes() {
        assert_eq!(
            query_value("/api/partitions?disk=%2Fdev%2Fnvme0n1p2", "disk").as_deref(),
            Some("/dev/nvme0n1p2")
        );
        assert_eq!(query_value("/api/partitions?disk=%ZZ", "disk"), None);
        assert_eq!(query_value("/api/partitions?other=sda", "disk"), None);
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

    fn start_request(body: &str) -> Vec<u8> {
        format!(
            "POST /api/start HTTP/1.1\r\nHost: installer\r\nContent-Length: {}\r\n\r\n{}",
            body.len(),
            body
        )
        .into_bytes()
    }

    #[test]
    fn normalizes_start_request_before_forwarding() {
        let request = start_request(
            r#"{"disk":" sda ","install_mode":" Wipe ","resize_gib":0,"free_region_start":0,"free_region_end":0,"username":"alice","password":"secret"}"#,
        );
        let normalized = normalize_start_request(&request).expect("start request should normalize");
        let end = normalized
            .windows(4)
            .position(|window| window == b"\r\n\r\n")
            .unwrap()
            + 4;
        let body: Value =
            serde_json::from_slice(&normalized[end..]).expect("normalized body is JSON");
        assert_eq!(body["disk"], "/dev/sda");
        assert_eq!(body["install_mode"], "wipe");
        assert_eq!(body["target_partition"], "");
        assert_eq!(body["resize_partition"], "");
        assert_eq!(body["resize_gib"], 0);
        assert!(String::from_utf8_lossy(&normalized)
            .contains(&format!("Content-Length: {}", normalized.len() - end)));
    }

    #[test]
    fn rejects_invalid_start_plan_before_forwarding() {
        let request = start_request(r#"{"disk":"../../etc/passwd","install_mode":"wipe"}"#);
        let error = normalize_start_request(&request).expect_err("unsafe disk must fail closed");
        assert!(error.contains("target disk"), "{error}");
    }

    #[test]
    fn leaves_other_routes_byte_for_byte_unchanged() {
        let request = b"GET /api/disks HTTP/1.1\r\nHost: installer\r\nContent-Length: 0\r\n\r\n";
        assert_eq!(normalize_start_request(request).unwrap(), request);
    }

    #[test]
    fn native_start_boundary_builds_typed_executor() {
        let request = start_request(
            r#"{"disk":"sda","install_mode":"wipe","source_imgref":"oci:/image","target_imgref":"kyth:latest","hostname":"kyth","acknowledged-irreversible":true}"#,
        );
        let executor = native_executor_from_start(&request).expect("native plan should validate");
        assert_eq!(executor.storage_plan().disk, "/dev/sda");
        assert_eq!(executor.execution_plan().bootc.target, "/dev/sda");
    }

    #[test]
    fn native_start_boundary_keeps_start_route_native() {
        let request = start_request(
            r#"{"disk":"sda","install_mode":"wipe","username":"alice","password":"secret","password_hash":"$6$hash","confirm_backup":true,"confirm_erase":true,"acknowledged-irreversible":true}"#,
        );
        let native = native_request_from_start(&request).expect("native request should decode");
        assert_eq!(native.storage.disk, "sda");
        assert_eq!(native.execution.account.unwrap().username, "alice");
    }

    #[test]
    fn native_start_requires_review_acknowledgements_and_a_login() {
        for body in [
            serde_json::json!({"disk":"sda", "username":"alice", "password":"secret"}),
            serde_json::json!({"disk":"sda", "confirm_erase":true, "username":"alice", "password":"secret"}),
            serde_json::json!({"disk":"sda", "confirm_backup":true, "confirm_erase":true, "password":"secret"}),
            serde_json::json!({"disk":"sda", "confirm_backup":true, "confirm_erase":true, "username":"alice"}),
        ] {
            let request = start_request(&body.to_string());
            assert!(native_request_from_start(&request).is_err());
        }

        let request = start_request(
            r#"{"disk":"sda","username":"alice","password":"secret","confirm_backup":true,"confirm_erase":true,"acknowledged-irreversible":true}"#,
        );
        assert!(native_request_from_start(&request).is_ok());
    }

    #[test]
    fn native_job_registry_starts_empty_and_rejects_cancel_without_job() {
        let registry = super::NativeJobRegistry::default();
        assert!(registry.snapshot().unwrap().is_none());
        assert!(registry.replay(0).unwrap().is_none());
        assert_eq!(
            registry.cancel().unwrap_err(),
            "No installation is running to cancel."
        );
    }

    #[test]
    fn native_journal_routes_preserve_pending_metadata_without_python() {
        let registry = NativeJournalRegistry::default();
        let (status, response) = registry.dispatch(
            "/api/create",
            serde_json::json!({"disk": "/dev/sda", "size_bytes": 4096}),
        );
        assert_eq!(status, 404);
        assert_eq!(response["ok"], false);

        *registry.active.lock().unwrap() =
            Some(super::super::installer_journal::PartitionJournal::new("/dev/sda").unwrap());
        let (status, response) = registry.dispatch(
            "/api/disk/create",
            serde_json::json!({
                "disk": "/dev/sda",
                "start_bytes": 4 * 1024 * 1024,
                "size_bytes": 32 * 1024 * 1024 * 1024_u64,
                "fs_type": "btrfs",
                "mountpoint": "/"
            }),
        );
        assert_eq!(status, 200);
        assert_eq!(response["ok"], true);
        assert_eq!(response["pending"], 1);
        let pending = registry.pending(&serde_json::json!({})).unwrap();
        assert_eq!(pending.as_array().unwrap().len(), 1);
        assert_eq!(pending[0]["kind"], "create");
        assert_eq!(pending[0]["params"]["mountpoint"], "/");
    }

    #[test]
    fn native_journal_routes_fail_closed_for_unsafe_and_unsupported_requests() {
        let registry = NativeJournalRegistry::default();
        let (status, response) = registry.dispatch(
            "/api/disk/new-table",
            serde_json::json!({"disk": "../../etc/passwd", "table_type": "gpt"}),
        );
        assert_eq!(status, 400);
        assert_eq!(response["ok"], false);

        *registry.active.lock().unwrap() =
            Some(super::super::installer_journal::PartitionJournal::new("/dev/sda").unwrap());
        let (status, response) = registry.dispatch(
            "/api/disk/create",
            serde_json::json!({
                "disk": "/dev/sda",
                "start_bytes": 4 * 1024 * 1024,
                "size_bytes": 32 * 1024 * 1024 * 1024_u64,
                "fs_type": "zfs"
            }),
        );
        assert_eq!(status, 400);
        assert_eq!(response["ok"], false);
        assert!(response["message"]
            .as_str()
            .unwrap()
            .contains("Unsupported"));
    }

    #[test]
    fn native_journal_pending_remove_and_rollback_clear_state() {
        let registry = NativeJournalRegistry::default();
        *registry.active.lock().unwrap() =
            Some(super::super::installer_journal::PartitionJournal::new("/dev/sda").unwrap());
        let (_, response) = registry.dispatch(
            "/api/disk/create",
            serde_json::json!({
                "disk": "/dev/sda",
                "start_bytes": 4 * 1024 * 1024,
                "size_bytes": 32 * 1024 * 1024 * 1024_u64
            }),
        );
        assert_eq!(response["pending"], 1);
        let (status, response) = registry.dispatch(
            "/api/disk/pending/remove",
            serde_json::json!({"disk": "/dev/sda", "index": 0}),
        );
        assert_eq!(status, 200);
        assert_eq!(response["pending"], 0);

        let (_, response) = registry.dispatch(
            "/api/disk/create",
            serde_json::json!({
                "disk": "/dev/sda",
                "start_bytes": 4 * 1024 * 1024,
                "size_bytes": 32 * 1024 * 1024 * 1024_u64
            }),
        );
        assert_eq!(response["pending"], 1);
        let (status, response) = registry.dispatch(
            "/api/disk/rollback",
            serde_json::json!({"disk": "/dev/sda"}),
        );
        assert_eq!(status, 200);
        assert_eq!(response["ok"], true);
        assert!(registry
            .pending(&serde_json::json!({}))
            .unwrap()
            .as_array()
            .unwrap()
            .is_empty());
    }

    #[test]
    fn resize_stage_carries_shrink_attestations_and_rejects_same_disk_backup() {
        use super::resize_op_params;
        // Same-disk backup path fails fast with an honest error, not at commit.
        let error = resize_op_params(
            "/dev/sda2",
            32 * 1024 * 1024 * 1024,
            &serde_json::json!({"gpt_backup_path": "/root/gpt.bak"}),
        )
        .expect_err("same-disk backup must fail");
        assert!(error["message"]
            .as_str()
            .unwrap()
            .contains("external media"));
        // External backup path + NTFS/AC attestations ride into staged params.
        let params = resize_op_params(
            "/dev/sda2",
            32 * 1024 * 1024 * 1024,
            &serde_json::json!({
                "gpt_backup_path": "/run/media/alice/BACKUP/sda-gpt.bak",
                "ntfs_verified_clean": true,
                "on_ac_power": true,
            }),
        )
        .expect("external backup must stage");
        assert_eq!(
            params["gpt_backup_path"],
            "/run/media/alice/BACKUP/sda-gpt.bak"
        );
        assert_eq!(params["ntfs_verified_clean"], true);
        assert_eq!(params["on_ac_power"], true);
        // Bare resize stages without attestations; AC is stamped at commit.
        let params = resize_op_params("/dev/sda2", 32 * 1024 * 1024 * 1024, &serde_json::json!({}))
            .expect("bare resize must stage");
        assert!(params.get("gpt_backup_path").is_none());
        assert!(params.get("on_ac_power").is_none());
    }

    #[test]
    fn shrink_power_stamp_attests_live_and_never_overrides_explicit() {
        use super::super::installer_journal::PartitionJournal;
        use super::{ac_online_in, stamp_shrink_power_attestation_in};
        // Empty power tree reads as on-AC (desktop/VM: nothing to gate on).
        let empty = tempdir().unwrap();
        assert!(ac_online_in(empty.path()));
        // A discharging battery reads as off-AC.
        let battery = tempdir().unwrap();
        let bat = battery.path().join("BAT0");
        fs::create_dir_all(&bat).unwrap();
        fs::write(bat.join("status"), "Discharging\n").unwrap();
        assert!(!ac_online_in(battery.path()));
        fs::remove_file(bat.join("status")).unwrap();
        assert!(
            !ac_online_in(battery.path()),
            "unknown battery state must fail closed"
        );
        let ac = battery.path().join("AC");
        fs::create_dir_all(&ac).unwrap();
        fs::write(ac.join("online"), "0\n").unwrap();
        fs::write(bat.join("status"), "Not charging\n").unwrap();
        assert!(!ac_online_in(battery.path()), "offline AC must fail closed");

        let mut journal = PartitionJournal::new("/dev/sda").unwrap();
        journal.add_op(
            "resize",
            serde_json::json!({"partition": "/dev/sda2", "new_size_bytes": 1}),
        );
        stamp_shrink_power_attestation_in(&mut journal, battery.path());
        assert_eq!(journal.ops[0].params["on_ac_power"], false);

        // The privileged commit probe overrides a client-supplied claim.
        let mut journal = PartitionJournal::new("/dev/sda").unwrap();
        journal.add_op(
            "resize",
            serde_json::json!({
                "partition": "/dev/sda2",
                "new_size_bytes": 1,
                "on_ac_power": true,
            }),
        );
        stamp_shrink_power_attestation_in(&mut journal, battery.path());
        assert_eq!(journal.ops[0].params["on_ac_power"], false);
    }
}
