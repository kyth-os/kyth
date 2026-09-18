use std::collections::{HashMap, HashSet};
use std::fs;
use std::io::{BufRead, BufReader, Write};
use std::os::unix::fs::{OpenOptionsExt, PermissionsExt};
use std::os::unix::process::CommandExt;
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::{mpsc, Arc, Mutex, OnceLock};
use std::thread;

use tauri::{AppHandle, Emitter, Manager, WebviewUrl, WebviewWindowBuilder};
use url::Url;

use crate::InstallStatus;
use kyth_shared::system::network_preset;

static JOBS: OnceLock<Mutex<HashMap<String, Arc<VpnRuntime>>>> = OnceLock::new();

/// Jobs whose SAML cookie was already consumed by a first callback. The
/// portal page can fire the navigation hook twice (form submit + synthetic
/// redirect); the second callback for the same job must be ignored so it
/// cannot restart or disturb the reconnect the first one started.
static SAML_CONSUMED: OnceLock<Mutex<HashSet<String>>> = OnceLock::new();

fn saml_consumed() -> &'static Mutex<HashSet<String>> {
    SAML_CONSUMED.get_or_init(|| Mutex::new(HashSet::new()))
}

/// Claim the cookie for `job`. Returns false when a previous callback
/// already consumed it — the caller must ignore the duplicate.
fn claim_saml_cookie(job: &str) -> bool {
    saml_consumed()
        .lock()
        .map(|mut consumed| consumed.insert(job.to_string()))
        .unwrap_or(true)
}

/// Upper bound on tracked VPN runtimes. Connects are rare user actions, so
/// this cap is generous headroom, not a tight budget: it only stops an
/// unbounded accumulate-across-the-process-lifetime leak.
const MAX_VPN_JOBS: usize = 16;

fn jobs() -> &'static Mutex<HashMap<String, Arc<VpnRuntime>>> {
    JOBS.get_or_init(|| Mutex::new(HashMap::new()))
}

struct VpnRuntime {
    status: Mutex<(String, String)>,
    /// Child slot tagged with the worker generation that spawned it. A
    /// superseded worker (reconnect/disconnect bumped `generation`) must
    /// only take and kill its own generation — never a newer one's child.
    child: Mutex<Option<(u64, Child)>>,
    stopped: AtomicBool,
    generation: AtomicU64,
    gateway: String,
    protocol: String,
    os_emulation: String,
    username: String,
    interface: Mutex<String>,
}

fn status(runtime: &VpnRuntime, state: &str, detail: impl Into<String>) {
    if let Ok(mut current) = runtime.status.lock() {
        *current = (state.to_string(), detail.into());
    }
}

fn get_job(job: &str) -> Result<Arc<VpnRuntime>, String> {
    jobs()
        .lock()
        .map_err(|_| "VPN job store is unavailable".to_string())?
        .get(job)
        .cloned()
        .ok_or_else(|| "VPN job not found".to_string())
}

/// Fixed askpass helper for every `sudo -A` spawn in this module. One
/// constant, not per-call literals, so a helper relocation updates every
/// privileged path at once instead of leaving one silently unpinned.
pub(crate) const SUDO_ASKPASS_PATH: &str = "/usr/bin/ksshaskpass";

/// Scrub a `sudo -A` child down to the minimal desktop environment and pin
/// the askpass helper. Fails closed when the helper is missing: `sudo -A`
/// with no helper dies without ever prompting, so every caller must treat
/// this `Err` as "no admin prompt possible" and land in its own terminal
/// state instead of spawning sudo.
///
/// Ordering is load-bearing: the desktop sanitizer passes through an
/// inherited `SUDO_ASKPASS`, so the fixed helper is set *after* the
/// scrubbed environment is applied and always wins. No `-E` passthrough
/// anywhere on this path.
fn prepare_sudo_command(command: &mut Command) -> Result<(), String> {
    let inherited = std::env::vars().collect::<std::collections::BTreeMap<_, _>>();
    let desktop = kyth_shared::commands::environment_for(
        kyth_shared::commands::EnvironmentPolicy::Desktop,
        &inherited,
    );
    command.env_clear().envs(desktop);
    if std::path::Path::new(SUDO_ASKPASS_PATH).exists() {
        command.env("SUDO_ASKPASS", SUDO_ASKPASS_PATH);
        Ok(())
    } else {
        Err(
            "VPN cannot prompt for administrator access: the askpass helper is missing."
                .to_string(),
        )
    }
}

/// Counter disambiguating staging files when two toggles land in the same
/// nanosecond (pid + clock alone could collide on a fast retry).
static STAGING_COUNTER: AtomicU64 = AtomicU64::new(0);

/// Stage validated preset text for the privileged copy.
///
/// The file is created with `O_EXCL` (`create_new`) at `0o600` under a
/// pid/clock/counter-unique name: the old `$TMPDIR/kyth-network-{pid}` was
/// guessable from outside, and plain `fs::write` follows a pre-planted
/// symlink straight into root's `cp`. Returns the staging path; the caller
/// removes it after the copy settles either way.
fn stage_network_preset(rendered: &str) -> Result<PathBuf, String> {
    let pid = std::process::id();
    let nanos = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap_or_default()
        .as_nanos();
    for _ in 0..8 {
        let slot = STAGING_COUNTER.fetch_add(1, Ordering::SeqCst);
        let staging = std::env::temp_dir().join(format!("kyth-network-{pid}-{nanos}-{slot}.toml"));
        let mut options = std::fs::OpenOptions::new();
        options.write(true).create_new(true).mode(0o600);
        match options.open(&staging) {
            Ok(mut file) => {
                if let Err(error) = file.write_all(rendered.as_bytes()) {
                    let _ = std::fs::remove_file(&staging);
                    return Err(format!("could not stage network preset: {error}"));
                }
                return Ok(staging);
            }
            Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => continue,
            Err(error) => return Err(format!("could not stage network preset: {error}")),
        }
    }
    Err("could not stage network preset: no unique staging name".to_string())
}

fn save_profile(
    gateway: &str,
    protocol: &str,
    os_emulation: &str,
    username: &str,
) -> Result<(), String> {
    let home = std::env::var_os("HOME").ok_or_else(|| "HOME is unavailable".to_string())?;
    let path = PathBuf::from(home).join(".config/kyth-vpn-connect");
    let parent = path
        .parent()
        .ok_or_else(|| "VPN config path is invalid".to_string())?;
    fs::create_dir_all(parent)
        .map_err(|error| format!("could not create VPN config directory: {error}"))?;
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        fs::set_permissions(parent, fs::Permissions::from_mode(0o700))
            .map_err(|error| error.to_string())?;
    }
    let content = format!("[vpn]\ngateway = {gateway}\nprotocol = {protocol}\nos = {os_emulation}\nusername = {username}\n");
    kyth_shared::atomic_io::atomic_write_text(&path, &content, Some(0o600))
        .map_err(|error| format!("could not save VPN profile: {error}"))
}

fn terminate_child(runtime: &VpnRuntime) {
    // Take the child out of the slot instead of borrowing it: the reap
    // below blocks, and holding the lock across it would stall any other
    // thread that wants the slot (including the worker's own take).
    let taken = runtime
        .child
        .lock()
        .ok()
        .and_then(|mut slot| slot.take().map(|(_, child)| child));
    if let Some(mut child) = taken {
        kyth_shared::system::process::kill_process_group(&mut child);
        // Reap so a disconnected openconnect never lingers as a zombie.
        let _ = child.wait();
    }
}

/// Terminal VPN states: the frontend stops polling on these. Any new
/// terminal state introduced here must also be added to `TERMINAL_VPN_STATES`
/// in `VpnSection.tsx` (and the `VpnConnectionStatus` union in `liveData.ts`),
/// or the Hub will poll a finished job for 300 intervals.
pub(crate) const VPN_TERMINAL_STATES: &[&str] = &[
    "connected",
    "failed",
    "disconnected",
    "complete",
    "failed_lockdown",
    "failed_lockdown_open",
    "connected_firewall_open",
    "complete_firewall_open",
];

/// Desired firewalld default zone for a lockdown transition. Returns `None`
/// when the Hub did not opt into `vpn_fail_closed`: lockdown is a no-op and
/// the caller keeps its own status. Pure over the loaded preset so it is
/// unit-testable without touching sudo.
fn vpn_lockdown_target(preset: &network_preset::NetworkPreset, lockdown: bool) -> Option<String> {
    if !preset.vpn_fail_closed {
        return None;
    }
    Some(if lockdown {
        "block".to_string()
    } else {
        preset.firewall_zone.clone()
    })
}

/// Whether the Hub opted into fail-closed VPN lockdown.
fn vpn_fail_closed_enabled() -> bool {
    network_preset::load(preset_path()).vpn_fail_closed
}

/// Fail-closed lockdown (Hub opt-in `vpn_fail_closed`): flip firewalld to
/// the `block` zone through the same sudo/askpass path openconnect uses,
/// so traffic cannot silently return to the raw LAN when the tunnel drops
/// unexpectedly.
///
/// Returns true when lockdown is a no-op (opt-out) or the zone flip
/// succeeded. Status ownership: engaging lockdown (`lockdown == true`) sets
/// a terminal state itself — `failed_lockdown` on success,
/// `failed_lockdown_open` when the admin prompt goes unanswered, `failed`
/// when the Hub never opted into fail-closed (an engage that turns out to
/// be opted out must still land somewhere terminal, or the job sits on a
/// stale `connecting` while the frontend polls past it) — so the
/// prior `failed` is never clobbered with a generic `warning` the frontend
/// polls past. Releasing lockdown leaves the caller's status alone; the
/// caller sets its own `*_firewall_open` terminal state on failure.
fn set_vpn_lockdown(runtime: &VpnRuntime, lockdown: bool) -> bool {
    set_vpn_lockdown_at(runtime, lockdown, &preset_path())
}

/// `set_vpn_lockdown` against an explicit preset path so unit tests can
/// drive the opt-out no-op (and the opt-in target computation) without
/// touching `/etc/kyth/network.toml` or sudo.
fn set_vpn_lockdown_at(
    runtime: &VpnRuntime,
    lockdown: bool,
    preset_file: &std::path::Path,
) -> bool {
    let preset = network_preset::load(preset_file);
    let Some(zone) = vpn_lockdown_target(&preset, lockdown) else {
        // Opt-out no-op. Releasing lockdown stays silent — the caller owns
        // `connected`/`complete` there. But an *engage* that turns out to be
        // opted out (preset flipped between the drop check and this load)
        // must still land in an explicit terminal state, or the job keeps a
        // stale `connecting` the frontend polls for 300 intervals.
        if lockdown {
            status(runtime, "failed", "VPN connection ended unexpectedly.");
        }
        return true;
    };
    let mut command = std::process::Command::new("sudo");
    command
        .arg("-A")
        .arg("firewall-cmd")
        .arg(format!("--set-default-zone={zone}"))
        .stdin(std::process::Stdio::null())
        .stdout(std::process::Stdio::piped())
        .stderr(std::process::Stdio::piped());
    // Same fail-closed askpass gate as the openconnect spawn: without the
    // helper no admin prompt is possible, so report the lockdown as open
    // (engage) instead of letting `sudo -A` die cryptically, or let the
    // caller set its own `*_firewall_open` terminal state (release).
    if prepare_sudo_command(&mut command).is_err() {
        if lockdown {
            status(
                runtime,
                "failed_lockdown_open",
                "VPN dropped but the network lockdown needs an admin password; traffic may leave the tunnel.",
            );
        }
        return false;
    }
    let ok = kyth_shared::system::process::run_bounded_command(
        command,
        std::time::Duration::from_secs(60),
    )
    .map(|output| output.status.success())
    .unwrap_or(false);
    if lockdown {
        if ok {
            status(
                runtime,
                "failed_lockdown",
                "VPN dropped unexpectedly; the network is blocked until you reconnect or disconnect.",
            );
        } else {
            status(
                runtime,
                "failed_lockdown_open",
                "VPN dropped but the network lockdown needs an admin password; traffic may leave the tunnel.",
            );
        }
    }
    ok
}

/// Take the child only when its tag matches `generation`. A superseded
/// worker exiting late must not reap or kill the newer generation's child.
fn take_child_for_generation(runtime: &VpnRuntime, generation: u64) -> Option<Child> {
    runtime.child.lock().ok().and_then(|mut slot| {
        if slot.as_ref().is_some_and(|(tag, _)| *tag == generation) {
            slot.take().map(|(_, child)| child)
        } else {
            None
        }
    })
}

fn reader<R: std::io::Read + Send + 'static>(stream: R, tx: mpsc::Sender<String>) {
    for line in BufReader::new(stream).lines().map_while(Result::ok) {
        let _ = tx.send(line);
    }
}

fn start_process(
    runtime: Arc<VpnRuntime>,
    app: AppHandle,
    job: String,
    command: kyth_shared::system::vpn_saml::OpenconnectCommand,
) {
    let generation = runtime.generation.fetch_add(1, Ordering::SeqCst) + 1;
    thread::spawn(move || {
        let Some((program, args)) = command.argv.split_first() else {
            status(&runtime, "failed", "VPN command was empty.");
            return;
        };
        let mut child_command = Command::new(program);
        child_command
            .args(args)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped());
        // Never inherit the webview-adjacent environment into a sudo child:
        // scrub it to the minimal desktop set, then pin the askpass helper
        // (shared `prepare_sudo_command`; no `-E` passthrough anywhere in
        // this path). A missing helper fails closed here with a clear
        // message instead of a cryptic openconnect error downstream.
        if let Err(error) = prepare_sudo_command(&mut child_command) {
            status(&runtime, "failed", error);
            return;
        }
        // Own process group so a later disconnect kills forked openconnect
        // grandchildren too, not just the sudo wrapper.
        child_command.process_group(0);
        let mut child = match child_command.spawn() {
            Ok(child) => child,
            Err(error) => {
                status(&runtime, "failed", format!("Could not start VPN: {error}"));
                return;
            }
        };
        if let Some(mut stdin) = child.stdin.take() {
            if let Some(input) = command.stdin {
                let _ = stdin.write_all(input.as_bytes());
            }
        }
        let stdout = child.stdout.take();
        let stderr = child.stderr.take();
        if let Ok(mut slot) = runtime.child.lock() {
            *slot = Some((generation, child));
        }
        let (tx, rx) = mpsc::channel();
        if let Some(stdout) = stdout {
            let tx = tx.clone();
            thread::spawn(move || reader(stdout, tx));
        }
        if let Some(stderr) = stderr {
            let tx = tx.clone();
            thread::spawn(move || reader(stderr, tx));
        }
        drop(tx);
        let mut saml_opened = false;
        loop {
            match rx.recv_timeout(std::time::Duration::from_millis(250)) {
                Ok(line) => {
                    let redacted = kyth_shared::system::vpn_saml::redact_log_line(&line);
                    if let Some(interface) =
                        kyth_shared::system::vpn_saml::gp_interface_from_log_line(&line)
                    {
                        if let Ok(mut current) = runtime.interface.lock() {
                            *current = interface.to_string();
                        }
                    }
                    if let Some(saml_url) =
                        kyth_shared::system::vpn_saml::saml_url_from_log_line(&line)
                    {
                        status(
                            &runtime,
                            "authentication_required",
                            "VPN sign-in is required; complete the secure sign-in window.",
                        );
                        if !saml_opened {
                            saml_opened = true;
                            open_saml_window(&app, &job, &runtime.gateway, &saml_url);
                        }
                    } else if kyth_shared::system::vpn_saml::line_is_connected(&line) {
                        status(&runtime, "connected", "VPN connection established.");
                        // Tunnel is up: lift any fail-closed lockdown from an
                        // earlier drop (no-op unless the Hub opted in). A
                        // failed restore must not clobber `connected` with a
                        // polled-past warning: it gets its own terminal state.
                        if !set_vpn_lockdown(&runtime, false) {
                            status(
                                &runtime,
                                "connected_firewall_open",
                                "VPN is connected but restoring the firewall zone needs an admin password; check your zone.",
                            );
                        }
                    } else if !redacted.trim().is_empty() {
                        status(&runtime, "connecting", redacted);
                    }
                }
                Err(mpsc::RecvTimeoutError::Timeout) => {
                    // Bounded wait: a hung child that prints nothing must
                    // not park this worker forever. Stop and supersede take
                    // effect on the next tick; an already-exited child means
                    // the readers are just flushing their last lines.
                    if runtime.stopped.load(Ordering::SeqCst)
                        || runtime.generation.load(Ordering::SeqCst) != generation
                    {
                        break;
                    }
                    let exited = runtime
                        .child
                        .lock()
                        .ok()
                        .and_then(|mut slot| {
                            slot.as_mut().and_then(|(_, child)| child.try_wait().ok())
                        })
                        .is_some_and(|status| status.is_some());
                    if exited {
                        break;
                    }
                }
                Err(mpsc::RecvTimeoutError::Disconnected) => break,
            }
        }
        // Take the child out of the slot before waiting so a concurrent
        // disconnect never blocks on this worker's reap. An early break
        // above (stop/supersede) still has a live child here: kill its
        // whole group so no openconnect outlives its job. Only take on a
        // tag match: a superseded worker exiting late must leave the newer
        // generation's child alone.
        let mut child = take_child_for_generation(&runtime, generation);
        if runtime.stopped.load(Ordering::SeqCst)
            || runtime.generation.load(Ordering::SeqCst) != generation
        {
            if let Some(child) = child.as_mut() {
                kyth_shared::system::process::kill_process_group(child);
            }
        }
        let exit_status = child.as_mut().and_then(|child| child.wait().ok());
        let exit_success = exit_status.map(|status| status.success()).unwrap_or(false);
        if runtime.generation.load(Ordering::SeqCst) != generation {
            return;
        }
        // Only clear our own generation's slot: a reconnect may have stored
        // a newer child since we took ours above; blanking it would orphan
        // (and leak) the new openconnect.
        if let Ok(mut slot) = runtime.child.lock() {
            if slot
                .as_ref()
                .map(|(tag, _)| *tag == generation)
                .unwrap_or(true)
            {
                *slot = None;
            }
        }
        if runtime.stopped.load(Ordering::SeqCst) {
            return;
        }
        let current = runtime
            .status
            .lock()
            .ok()
            .map(|value| value.0.clone())
            .unwrap_or_default();
        if current == "authentication_required" {
            return;
        }
        if exit_success {
            status(&runtime, "disconnected", "VPN connection ended.");
        } else if vpn_fail_closed_enabled() {
            // Unexpected drop with fail-closed opted in: block the raw LAN
            // before background traffic can leak out of the dead tunnel.
            // `set_vpn_lockdown` owns the terminal state here
            // (`failed_lockdown` or `failed_lockdown_open`).
            set_vpn_lockdown(&runtime, true);
        } else {
            status(&runtime, "failed", "VPN connection ended unexpectedly.");
        }
    });
}

fn start_reconnect(app: AppHandle, job: String, cookie: String) {
    let Ok(runtime) = get_job(&job) else {
        return;
    };
    terminate_child(&runtime);
    let interface = runtime
        .interface
        .lock()
        .ok()
        .map(|value| value.clone())
        .unwrap_or_else(|| "portal".into());
    match kyth_shared::system::vpn_saml::build_reconnect_command(
        &runtime.gateway,
        &runtime.protocol,
        &runtime.os_emulation,
        &interface,
        &cookie,
        &runtime.username,
    ) {
        Ok(command) => {
            runtime.stopped.store(false, Ordering::SeqCst);
            status(
                &runtime,
                "connecting",
                "SAML sign-in complete; reconnecting VPN…",
            );
            start_process(runtime, app, job, command);
        }
        Err(_) => status(
            &runtime,
            "failed",
            "VPN authentication response was invalid.",
        ),
    }
}

fn callback_value(url: &Url, key: &str) -> Option<String> {
    url.query_pairs()
        .find_map(|(name, value)| (name == key).then(|| value.into_owned()))
}

fn handle_saml_callback(
    app: AppHandle,
    label: String,
    job: String,
    gateway: String,
    callback: String,
) {
    thread::spawn(move || {
        let Ok(url) = Url::parse(&callback) else {
            if let Ok(runtime) = get_job(&job) {
                status(&runtime, "failed", "VPN sign-in callback was invalid.");
            }
            return;
        };
        if callback.len() > 8 * 1024 * 1024
            || url.scheme() != "http"
            || url.host_str() != Some("127.0.0.1")
            || url.path() != "/kyth-vpn/saml-acs"
            || callback_value(&url, "token").as_deref() != Some(job.as_str())
        {
            if let Ok(runtime) = get_job(&job) {
                status(&runtime, "failed", "VPN sign-in callback was rejected.");
            }
            return;
        }
        if let Some(cookie) = callback_value(&url, "cookie") {
            // Debounce: the portal can deliver the same cookie twice (form
            // submit + synthetic redirect). The second callback is ignored
            // once the first has consumed the cookie.
            if !claim_saml_cookie(&job) {
                return;
            }
            if let Some(window) = app.get_webview_window(&label) {
                let _ = window.close();
            }
            start_reconnect(app, job, cookie);
            return;
        }
        let form = callback_value(&url, "url").zip(callback_value(&url, "body"));
        if kyth_shared::system::vpn_saml::classify_saml_callback(false, form.is_some())
            == kyth_shared::system::vpn_saml::SamlCallbackKind::Empty
        {
            // The page finished without yielding credentials. This used to
            // be a silent return that left the Hub stuck on "sign-in
            // required" with no way forward.
            if let Ok(runtime) = get_job(&job) {
                status(
                    &runtime,
                    "failed",
                    "VPN sign-in completed without an authentication response.",
                );
            }
            return;
        }
        let (action_url, body) = form.unwrap_or_default();
        let (argv, input) = match kyth_shared::system::vpn_saml::replay_saml_command(
            &action_url,
            &body,
            &gateway,
        ) {
            Ok(command) => command,
            Err(error) => {
                if let Ok(runtime) = get_job(&job) {
                    status(
                        &runtime,
                        "failed",
                        format!("VPN sign-in response failed validation: {error}"),
                    );
                }
                return;
            }
        };
        let response = kyth_shared::system::process::run_bounded_with_input(
            &argv,
            &input,
            std::time::Duration::from_secs(35),
        );
        let cookie = response.ok().and_then(|output| {
            // The bounded runner already caps each pipe at 8 MiB; refuse an
            // over-cap capture here too and bound the slice handed to the
            // header/body parser so a hostile portal cannot grow it.
            if output.stdout.len() > kyth_shared::system::process::MAX_CAPTURE_BYTES {
                return None;
            }
            let text = String::from_utf8_lossy(&output.stdout);
            let cut = text
                .char_indices()
                .nth(8 * 1024 * 1024)
                .map(|(index, _)| index);
            let text = match cut {
                Some(index) => text[..index].to_string(),
                None => text.into_owned(),
            };
            let (headers, body) = kyth_shared::system::vpn_saml::split_http_response(&text);
            if body.len() > kyth_shared::system::process::MAX_CAPTURE_BYTES {
                return None;
            }
            kyth_shared::system::vpn_saml::parse_saml_acs_response(headers, body)
        });
        if let Some(window) = app.get_webview_window(&label) {
            let _ = window.close();
        }
        match cookie {
            Some(cookie) => {
                // Same debounce as the direct-cookie path: only the first
                // callback that yields a cookie may start the reconnect.
                if !claim_saml_cookie(&job) {
                    return;
                }
                start_reconnect(app, job, cookie)
            }
            None => {
                if let Ok(runtime) = get_job(&job) {
                    status(
                        &runtime,
                        "failed",
                        "VPN portal did not return an authentication token.",
                    );
                }
            }
        }
    });
}

fn open_saml_window(app: &AppHandle, job: &str, gateway: &str, saml_url: &str) {
    let label = format!("vpn-saml-{job}");
    if let Some(window) = app.get_webview_window(&label) {
        let _ = window.show();
        let _ = window.set_focus();
        return;
    }
    if kyth_shared::system::vpn_saml::validate_saml_redirect_url(saml_url).is_err() {
        if let Ok(runtime) = get_job(job) {
            status(&runtime, "failed", "VPN sign-in redirect was rejected.");
        }
        return;
    }
    let callback_app = app.clone();
    let callback_label = label.clone();
    let callback_job = job.to_string();
    let callback_gateway = gateway.to_string();
    let init_script = r#"(function(){
      function submitToKyth(form){
        if(!form)return false;
        if(form.__kythVpnCaptured)return true;
        var action=form.getAttribute('action')||form.action||'';
        if(!/\/SAML20\/SP\/ACS(?:[/?#]|$)/i.test(action))return false;
        var fd; try{fd=new FormData(form)}catch(e){return false};
        if(typeof fd.get('SAMLResponse')!=='string' || !fd.get('SAMLResponse'))return false;
        form.__kythVpnCaptured=true;
        var p=new URLSearchParams(); fd.forEach(function(value,key){if(typeof value==='string')p.append(key,value)});
        window.location.replace('http://127.0.0.1/kyth-vpn/saml-acs?token=__KYTH_VPN_TOKEN__&url='+encodeURIComponent(action)+'&body='+encodeURIComponent(p.toString()));
        return true;
      }
      function inspect(node){
        if(!node || node.nodeType!==1)return;
        if(node.matches && node.matches('form'))submitToKyth(node);
        if(node.closest) { var parent=node.closest('form'); if(parent)submitToKyth(parent); }
        if(node.querySelectorAll)node.querySelectorAll('form').forEach(submitToKyth);
      }
      var original=HTMLFormElement.prototype.submit;
      HTMLFormElement.prototype.submit=function(){if(!submitToKyth(this))original.call(this)};
      document.addEventListener('submit',function(e){if(submitToKyth(e.target)){e.preventDefault();e.stopImmediatePropagation()}},true);
      function watch(){
        if(!document.documentElement)return;
        new MutationObserver(function(records){records.forEach(function(record){record.addedNodes.forEach(inspect)})}).observe(document.documentElement,{childList:true,subtree:true});
        document.querySelectorAll('form').forEach(submitToKyth);
      }
      if(document.documentElement)watch();else document.addEventListener('DOMContentLoaded',watch);
    })();"#.replace("__KYTH_VPN_TOKEN__", job);
    let Ok(initial_url) = Url::parse(saml_url) else {
        if let Ok(runtime) = get_job(job) {
            status(&runtime, "failed", "VPN sign-in redirect was invalid.");
        }
        return;
    };
    if initial_url.scheme() != "https"
        || initial_url.host_str().is_none()
        || !initial_url.username().is_empty()
        || initial_url.password().is_some()
        || initial_url.fragment().is_some()
    {
        if let Ok(runtime) = get_job(job) {
            status(&runtime, "failed", "VPN sign-in redirect was rejected.");
        }
        return;
    }
    let result = WebviewWindowBuilder::new(app, &label, WebviewUrl::External(initial_url))
        .title("VPN — Secure sign-in")
        .inner_size(960.0, 720.0)
        .initialization_script_for_all_frames(init_script)
        .on_navigation(move |url| {
            if url.scheme() == "http"
                && url.host_str() == Some("127.0.0.1")
                && url.path() == "/kyth-vpn/saml-acs"
            {
                handle_saml_callback(
                    callback_app.clone(),
                    callback_label.clone(),
                    callback_job.clone(),
                    callback_gateway.clone(),
                    url.as_str().to_string(),
                );
                false
            } else {
                true
            }
        })
        .build();
    if result.is_err() {
        if let Ok(runtime) = get_job(job) {
            status(
                &runtime,
                "failed",
                "Could not open the secure VPN sign-in window.",
            );
        }
    }
}

#[tauri::command]
pub(crate) fn open_vpn_app(app: AppHandle) -> Result<String, String> {
    let window = app
        .get_webview_window("main")
        .ok_or_else(|| "Hub window is unavailable".to_string())?;
    window.show().map_err(|error| error.to_string())?;
    window.set_focus().map_err(|error| error.to_string())?;
    let _ = window.emit("navigate", "VPN");
    Ok("Opened native VPN controls in the Hub.".into())
}

#[tauri::command]
pub(crate) fn vpn_connect(
    app: AppHandle,
    gateway: String,
    protocol: String,
    os_emulation: String,
    username: String,
    password: String,
) -> Result<String, String> {
    // A second connect to the same gateway while one is already up would
    // fork a duplicate openconnect fighting over the tunnel route. Reject
    // it; the UI disconnects or reuses the live job instead.
    let already_connected = jobs().lock().map(|store| {
        store.values().any(|runtime| {
            runtime.gateway == gateway
                && runtime
                    .status
                    .lock()
                    .ok()
                    .is_some_and(|guard| guard.0 == "connected")
        })
    });
    if already_connected.unwrap_or(false) {
        return Err(format!("Already connected to {gateway}; disconnect first."));
    }
    let command = kyth_shared::system::vpn_saml::build_initial_command(
        &gateway,
        &protocol,
        &os_emulation,
        &username,
        &password,
    )?;
    save_profile(&gateway, &protocol, &os_emulation, &username)?;
    let job = format!(
        "vpn-{}",
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap_or_default()
            .as_nanos()
    );
    let runtime = Arc::new(VpnRuntime {
        status: Mutex::new(("connecting".into(), "Starting VPN connection…".into())),
        child: Mutex::new(None),
        stopped: AtomicBool::new(false),
        generation: AtomicU64::new(0),
        gateway,
        protocol,
        os_emulation,
        username,
        interface: Mutex::new("portal".into()),
    });
    {
        let mut store = jobs()
            .lock()
            .map_err(|_| "VPN job store is unavailable".to_string())?;
        // Disconnect keeps its final status for the UI poller, so entries
        // are only reaped here: past this cap, drop runtimes that already
        // reached a terminal state. Live connections are never evicted.
        if store.len() >= MAX_VPN_JOBS {
            let reaped: Vec<String> = store
                .iter()
                .filter_map(|(id, runtime)| {
                    runtime
                        .status
                        .lock()
                        .ok()
                        .filter(|guard| VPN_TERMINAL_STATES.contains(&guard.0.as_str()))
                        .map(|_| id.clone())
                })
                .collect();
            for id in reaped {
                store.remove(&id);
            }
        }
        store.insert(job.clone(), runtime.clone());
    }
    start_process(runtime, app, job.clone(), command);
    Ok(job)
}

#[tauri::command]
pub(crate) fn vpn_status(job: String) -> InstallStatus {
    let Ok(runtime) = get_job(&job) else {
        return InstallStatus {
            id: job,
            state: "unknown".into(),
            detail: "VPN job not found.".into(),
        };
    };
    let (state, detail) = runtime
        .status
        .lock()
        .ok()
        .map(|value| value.clone())
        .unwrap_or(("unknown".into(), "VPN status unavailable.".into()));
    InstallStatus {
        id: job,
        state,
        detail,
    }
}

#[tauri::command]
pub(crate) fn vpn_disconnect(job: String) -> Result<String, String> {
    let runtime = get_job(&job)?;
    runtime.stopped.store(true, Ordering::SeqCst);
    runtime.generation.fetch_add(1, Ordering::SeqCst);
    terminate_child(&runtime);
    status(&runtime, "complete", "VPN disconnected.");
    // Clean user disconnect lifts any fail-closed lockdown. A failed
    // restore gets its own terminal state rather than clobbering `complete`.
    if !set_vpn_lockdown(&runtime, false) {
        status(
            &runtime,
            "complete_firewall_open",
            "VPN disconnected but restoring the firewall zone needs an admin password; check your zone.",
        );
    }
    Ok("VPN disconnected.".into())
}

/// Hub-readable VPN protection flags: the two `network.toml` opt-ins the
/// Hub can toggle, plus the zone a clean disconnect restores. Read-only:
/// never prompts, never writes.
#[derive(serde::Serialize)]
pub(crate) struct VpnProtectionStatus {
    pub(crate) vpn_fail_closed: bool,
    pub(crate) vpn_dns_exclusive: bool,
    pub(crate) firewall_zone: String,
}

fn preset_path() -> PathBuf {
    network_preset::config_path(None::<&std::path::Path>)
}

fn vpn_protection_status_at(path: &std::path::Path) -> VpnProtectionStatus {
    let preset = network_preset::load(path);
    VpnProtectionStatus {
        vpn_fail_closed: preset.vpn_fail_closed,
        vpn_dns_exclusive: preset.vpn_dns_exclusive,
        firewall_zone: preset.firewall_zone,
    }
}

#[tauri::command]
pub(crate) fn vpn_protection_status() -> VpnProtectionStatus {
    vpn_protection_status_at(&preset_path())
}

/// Flip the two VPN protection opt-ins in `network.toml`, preserving the
/// DNS/firewall choices already there. The preset file is root-owned, so a
/// user-run Hub writes through a fixed `sudo -A cp --preserve=mode` of a
/// validated staging file (same askpass gate as the lockdown flip); a Hub
/// that can write the file directly (test mode, root) takes that path
/// instead. Either way the rendered text is re-loaded and compared before
/// it is persisted, and the persisted file is read back and compared after:
/// a rendering that does not decode to the intended preset fails closed and
/// never reports success on a half-configured system.
fn set_vpn_protection_at(
    path: &std::path::Path,
    vpn_fail_closed: bool,
    vpn_dns_exclusive: bool,
) -> Result<String, String> {
    let mut preset = network_preset::load(path);
    preset.vpn_fail_closed = vpn_fail_closed;
    preset.vpn_dns_exclusive = vpn_dns_exclusive;
    let rendered = network_preset::render_network_toml(&preset);
    // Exclusive-create 0600 staging under an unpredictable name (see
    // `stage_network_preset`): the old `$TMPDIR/kyth-network-{pid}` plus
    // plain `fs::write` let a local observer pre-plant the staging path.
    let staging = stage_network_preset(&rendered)?;
    let round_trips = network_preset::load(&staging) == preset;
    if !round_trips {
        let _ = std::fs::remove_file(&staging);
        return Err("refusing to persist a network preset that does not decode back".to_string());
    }
    if kyth_shared::atomic_io::atomic_write_text(path, &rendered, Some(0o644)).is_ok() {
        let _ = std::fs::remove_file(&staging);
        // Direct write took the fast path: confirm it landed as intended
        // before reporting success, same as the sudo path below.
        if network_preset::load(path) == preset {
            return Ok(vpn_protection_summary(&preset));
        }
        return Err("the network preset write did not verify; no change was applied.".to_string());
    }
    // Root-owned preset: fixed `mkdir -p` + `cp --preserve=mode` through the
    // shared sudo/askpass gate (fail closed when no admin prompt is
    // possible; never spawn `sudo -A` into a guaranteed cryptic failure).
    // Argv is fully fixed (both paths are computed, never user text). The
    // staging file is opened to the documented destination mode (0o644,
    // matching the direct-write path) after the round-trip check, so
    // `--preserve=mode` carries deterministic permissions instead of
    // whatever umask-dependent mode a bare `cp` would apply.
    if std::fs::set_permissions(&staging, std::fs::Permissions::from_mode(0o644)).is_err() {
        let _ = std::fs::remove_file(&staging);
        return Err("could not stage network preset: permission setup failed".to_string());
    }
    let mut mkdir = std::process::Command::new("sudo");
    mkdir
        .arg("-A")
        .arg("mkdir")
        .arg("-p")
        .arg(
            path.parent()
                .map(|parent| parent.as_os_str())
                .unwrap_or_default(),
        )
        .stdin(std::process::Stdio::null())
        .stdout(std::process::Stdio::piped())
        .stderr(std::process::Stdio::piped());
    let mut copy = std::process::Command::new("sudo");
    copy.arg("-A")
        .arg("cp")
        .arg("--preserve=mode")
        .arg(&staging)
        .arg(path)
        .stdin(std::process::Stdio::null())
        .stdout(std::process::Stdio::piped())
        .stderr(std::process::Stdio::piped());
    if prepare_sudo_command(&mut mkdir)
        .and(prepare_sudo_command(&mut copy))
        .is_err()
    {
        let _ = std::fs::remove_file(&staging);
        return Err(
            "saving VPN protection needs an admin password; the preset was not changed."
                .to_string(),
        );
    }
    let bound = std::time::Duration::from_secs(60);
    let mkdir_ok = kyth_shared::system::process::run_bounded_command(mkdir, bound)
        .map(|output| output.status.success())
        .unwrap_or(false);
    let copy_ok = mkdir_ok
        && kyth_shared::system::process::run_bounded_command(copy, bound)
            .map(|output| output.status.success())
            .unwrap_or(false);
    let _ = std::fs::remove_file(&staging);
    if !copy_ok {
        return Err(
            "saving VPN protection needs an admin password; the preset was not changed."
                .to_string(),
        );
    }
    // Read-back: the privileged copy must decode to exactly the preset the
    // Hub validated, or the system is left half-configured with a success
    // report. Fail closed on any mismatch.
    if network_preset::load(path) == preset {
        Ok(vpn_protection_summary(&preset))
    } else {
        Err("the network preset copy did not verify; the preset may not have changed.".to_string())
    }
}

fn vpn_protection_summary(preset: &network_preset::NetworkPreset) -> String {
    format!(
        "VPN protection: fail-closed {}, exclusive DNS {}.",
        if preset.vpn_fail_closed { "on" } else { "off" },
        if preset.vpn_dns_exclusive {
            "on"
        } else {
            "off"
        },
    )
}

#[tauri::command]
pub(crate) fn set_vpn_protection(
    vpn_fail_closed: bool,
    vpn_dns_exclusive: bool,
) -> Result<String, String> {
    set_vpn_protection_at(&preset_path(), vpn_fail_closed, vpn_dns_exclusive)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn saml_cookie_claim_debounces_second_callback() {
        let job = format!(
            "vpn-test-{}",
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap_or_default()
                .as_nanos()
        );
        assert!(claim_saml_cookie(&job));
        assert!(!claim_saml_cookie(&job));
        saml_consumed().lock().unwrap().remove(&job);
    }

    fn test_runtime(state: &str) -> VpnRuntime {
        VpnRuntime {
            status: Mutex::new((state.into(), "test".into())),
            child: Mutex::new(None),
            stopped: AtomicBool::new(false),
            generation: AtomicU64::new(0),
            gateway: "https://vpn.example".into(),
            protocol: "gp".into(),
            os_emulation: "win".into(),
            username: String::new(),
            interface: Mutex::new("portal".into()),
        }
    }

    fn runtime_state(runtime: &VpnRuntime) -> (String, String) {
        runtime.status.lock().unwrap().clone()
    }

    #[test]
    fn lockdown_target_is_none_without_opt_in() {
        let off = network_preset::NetworkPreset::default();
        assert!(!off.vpn_fail_closed);
        assert!(vpn_lockdown_target(&off, true).is_none());
        assert!(vpn_lockdown_target(&off, false).is_none());
    }

    #[test]
    fn lockdown_target_blocks_on_drop_and_restores_preset_zone() {
        let on = network_preset::NetworkPreset {
            vpn_fail_closed: true,
            firewall_zone: "work".into(),
            ..network_preset::NetworkPreset::default()
        };
        assert_eq!(vpn_lockdown_target(&on, true).as_deref(), Some("block"));
        assert_eq!(vpn_lockdown_target(&on, false).as_deref(), Some("work"));
    }

    #[test]
    fn lockdown_without_opt_in_never_touches_status_or_sudo() {
        let dir = tempfile::tempdir().unwrap();
        let preset_file = dir.path().join("network.toml");
        // Absent file loads defaults (opt-out): the no-op path must not
        // spawn sudo and must leave the caller's status alone.
        let runtime = test_runtime("failed");
        assert!(set_vpn_lockdown_at(&runtime, true, &preset_file));
        assert!(set_vpn_lockdown_at(&runtime, false, &preset_file));
        assert_eq!(runtime_state(&runtime).0, "failed");
    }

    #[test]
    fn lockdown_engage_without_opt_in_still_reaches_a_terminal_state() {
        // An engage that turns out to be opted out (preset flipped between
        // the drop check and the lockdown load) must not leave a stale
        // `connecting` the frontend polls for 300 intervals.
        let dir = tempfile::tempdir().unwrap();
        let preset_file = dir.path().join("network.toml");
        let runtime = test_runtime("connecting");
        assert!(set_vpn_lockdown_at(&runtime, true, &preset_file));
        let (state, _) = runtime_state(&runtime);
        assert_eq!(state, "failed");
        assert!(
            VPN_TERMINAL_STATES.contains(&state.as_str()),
            "{state} must be terminal or the frontend polls past it"
        );
        // Release stays a pure no-op: the caller owns `connected`.
        let release = test_runtime("connected");
        assert!(set_vpn_lockdown_at(&release, false, &preset_file));
        assert_eq!(runtime_state(&release).0, "connected");
    }

    #[test]
    fn staging_is_exclusive_create_and_unpredictable() {
        use std::os::unix::fs::PermissionsExt;
        let first = stage_network_preset("dns = \"off\"\n").expect("stage");
        let second = stage_network_preset("dns = \"off\"\n").expect("stage");
        assert_ne!(first, second);
        // O_EXCL: re-creating the same path must fail, never truncate.
        assert!(
            std::fs::OpenOptions::new()
                .write(true)
                .create_new(true)
                .mode(0o600)
                .open(&first)
                .is_err(),
            "staging must be exclusive-create"
        );
        assert_eq!(
            first.metadata().unwrap().permissions().mode() & 0o777,
            0o600
        );
        let _ = std::fs::remove_file(&first);
        let _ = std::fs::remove_file(&second);
    }

    #[test]
    fn every_backend_terminal_state_is_advertised() {
        // The frontend stops polling only on advertised states. If a new
        // terminal state is set anywhere in this module but missing here,
        // the Hub polls a finished job 300 times.
        for state in [
            "connected",
            "failed",
            "disconnected",
            "complete",
            "failed_lockdown",
            "failed_lockdown_open",
            "connected_firewall_open",
            "complete_firewall_open",
        ] {
            assert!(
                VPN_TERMINAL_STATES.contains(&state),
                "{state} is terminal in the backend but unknown to the frontend"
            );
        }
    }

    #[test]
    fn protection_toggle_flips_flags_and_preserves_the_rest() {
        let dir = tempfile::tempdir().unwrap();
        let preset_file = dir.path().join("network.toml");
        std::fs::write(
            &preset_file,
            "dns = \"cloudflare\"\ndoh = false\nfirewall_zone = \"work\"\ndns_strict = true\n",
        )
        .unwrap();
        let summary = set_vpn_protection_at(&preset_file, true, true).expect("toggle on");
        assert!(summary.contains("fail-closed on"));
        assert!(summary.contains("exclusive DNS on"));
        let status = vpn_protection_status_at(&preset_file);
        assert!(status.vpn_fail_closed);
        assert!(status.vpn_dns_exclusive);
        assert_eq!(status.firewall_zone, "work");
        // The pre-existing DNS choices survive the flag flip.
        let reloaded = network_preset::load(&preset_file);
        assert_eq!(reloaded.dns, "cloudflare");
        assert!(!reloaded.doh);
        assert!(reloaded.dns_strict);
        let summary = set_vpn_protection_at(&preset_file, false, false).expect("toggle off");
        assert!(summary.contains("fail-closed off"));
        let status = vpn_protection_status_at(&preset_file);
        assert!(!status.vpn_fail_closed);
        assert!(!status.vpn_dns_exclusive);
        assert_eq!(network_preset::load(&preset_file).dns, "cloudflare");
    }
}
