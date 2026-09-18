use std::collections::{HashMap, HashSet};
use std::fs;
use std::io::{BufRead, BufReader, Write};
use std::os::unix::process::CommandExt;
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::{mpsc, Arc, Mutex, OnceLock};
use std::thread;

use tauri::{AppHandle, Emitter, Manager, WebviewUrl, WebviewWindowBuilder};
use url::Url;

use crate::InstallStatus;

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
        // clear it, keep only the minimal desktop set (DISPLAY/Wayland,
        // HOME, PATH, …) via the shared sanitizer, then set the askpass
        // helper explicitly. No `-E` passthrough anywhere in this path.
        let inherited = std::env::vars().collect::<std::collections::BTreeMap<_, _>>();
        let desktop = kyth_shared::commands::environment_for(
            kyth_shared::commands::EnvironmentPolicy::Desktop,
            &inherited,
        );
        child_command.env_clear().envs(desktop);
        // Own process group so a later disconnect kills forked openconnect
        // grandchildren too, not just the sudo wrapper.
        child_command.process_group(0);
        if std::path::Path::new("/usr/bin/ksshaskpass").exists() {
            child_command.env("SUDO_ASKPASS", "/usr/bin/ksshaskpass");
        } else {
            // sudo -A with no askpass helper fails without ever prompting;
            // fail here with a clear message instead of a cryptic
            // openconnect error downstream.
            status(
                &runtime,
                "failed",
                "VPN cannot prompt for administrator access: the askpass helper is missing.",
            );
            return;
        }
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
            let text = text
                .char_indices()
                .nth(8 * 1024 * 1024)
                .map_or_else(|| text.into_owned(), |(index, _)| text[..index].to_string());
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
                        .filter(|guard| {
                            matches!(guard.0.as_str(), "failed" | "disconnected" | "complete")
                        })
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
    Ok("VPN disconnected.".into())
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
}
