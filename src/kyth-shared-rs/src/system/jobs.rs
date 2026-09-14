//! Bounded background-job store shared by every Hub command domain.
//!
//! Each domain previously kept its own `OnceLock<Mutex<HashMap<String,
//! (String, String)>>>` that only ever grew: every install, sync, Guardian
//! check, and update left one entry for the life of the process. This type
//! replaces all of them with one bounded contract:
//!
//! - at most [`MAX_JOBS`] entries; inserting beyond the cap evicts the
//!   oldest terminal entry first (oldest running entry only if every entry
//!   is still running, which means the caller has a bigger problem);
//! - terminal entries older than [`TERMINAL_TTL`] are pruned on access;
//! - every running entry carries a cancellation flag. Workers that run a
//!   child process poll it via
//!   [`crate::system::process::run_bounded_command_cancel`], so cancelling
//!   actually kills the process. Workers that only do socket I/O (the
//!   privileged helper) cannot be killed mid-request: cancelling them marks
//!   the job `cancelled` and their late `finish` becomes a no-op so the UI
//!   never resurrects a job the user dismissed.
//!
//! A `finish` for a cancelled job is always a no-op, and `cancel` for a
//! terminal or unknown job returns `false`.

use std::collections::{HashMap, VecDeque};
use std::sync::atomic::AtomicBool;
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

/// Upper bound on entries per store. A desktop Hub process rarely has more
/// than a handful of live jobs; 256 leaves wide headroom while keeping a
/// pathological frontend poll loop from growing memory without bound.
pub const MAX_JOBS: usize = 256;

/// Terminal entries older than this are pruned on the next store access, so
/// `job_status` polls from yesterday never accumulate.
pub const TERMINAL_TTL: Duration = Duration::from_secs(3600);

pub const STATE_RUNNING: &str = "running";
pub const STATE_COMPLETE: &str = "complete";
pub const STATE_FAILED: &str = "failed";
pub const STATE_CANCELLED: &str = "cancelled";
pub const STATE_UNKNOWN: &str = "unknown";

fn is_terminal(state: &str) -> bool {
    matches!(state, "complete" | "failed" | "cancelled")
}

struct Entry {
    state: String,
    detail: String,
    cancel: Arc<AtomicBool>,
    finished_at: Option<Instant>,
}

struct Inner {
    entries: HashMap<String, Entry>,
    /// Insertion order for oldest-first eviction. Lazily cleaned: ids that
    /// were already pruned are skipped when evicting.
    order: VecDeque<String>,
}

pub struct JobStore {
    inner: Mutex<Inner>,
}

impl Default for JobStore {
    fn default() -> Self {
        Self {
            inner: Mutex::new(Inner {
                entries: HashMap::new(),
                order: VecDeque::new(),
            }),
        }
    }
}

impl JobStore {
    fn lock(&self) -> std::sync::MutexGuard<'_, Inner> {
        self.inner
            .lock()
            .unwrap_or_else(|poison| poison.into_inner())
    }

    fn prune_locked(inner: &mut Inner, now: Instant) {
        inner.entries.retain(|_, entry| {
            !matches!(entry.finished_at, Some(finished) if now.duration_since(finished) > TERMINAL_TTL)
        });
        // The eviction queue must not outlive its entries: without this,
        // steady churn of short jobs grows `order` without bound even while
        // `entries` stays capped.
        inner.order.retain(|id| inner.entries.contains_key(id));
    }

    fn evict_locked(inner: &mut Inner) {
        while inner.entries.len() >= MAX_JOBS {
            let victim = inner
                .order
                .iter()
                .find(|id| {
                    inner
                        .entries
                        .get(*id)
                        .is_some_and(|entry| is_terminal(&entry.state))
                })
                .cloned()
                .or_else(|| inner.order.front().cloned());
            let Some(victim) = victim else {
                break;
            };
            inner.order.retain(|id| id != &victim);
            inner.entries.remove(&victim);
        }
    }

    /// Register a job as running and return its cancellation flag, which the
    /// worker thread must hand to the cancellable runner (or hold, for
    /// socket-I/O workers that can only be marked cancelled).
    pub fn start(&self, id: &str, detail: String) -> Arc<AtomicBool> {
        let cancel = Arc::new(AtomicBool::new(false));
        let mut inner = self.lock();
        Self::prune_locked(&mut inner, Instant::now());
        Self::evict_locked(&mut inner);
        inner.order.push_back(id.to_string());
        inner.entries.insert(
            id.to_string(),
            Entry {
                state: STATE_RUNNING.into(),
                detail,
                cancel: cancel.clone(),
                finished_at: None,
            },
        );
        cancel
    }

    /// Fetch the cancellation flag for a running job, if it is still tracked.
    pub fn cancel_flag(&self, id: &str) -> Option<Arc<AtomicBool>> {
        self.lock()
            .entries
            .get(id)
            .map(|entry| entry.cancel.clone())
    }

    /// Record a terminal state. Never overwrites `cancelled`: a worker that
    /// was killed late must not resurrect its job. Unknown ids are ignored.
    pub fn finish(&self, id: &str, state: &str, detail: String) {
        let mut inner = self.lock();
        if let Some(entry) = inner.entries.get_mut(id) {
            if entry.state == STATE_CANCELLED {
                return;
            }
            entry.state = state.into();
            entry.detail = detail;
            entry.finished_at = Some(Instant::now());
        }
    }

    /// Cancel a running job: signals its worker (killing a child process
    /// within one poll tick) and marks it `cancelled`. Returns `false` for
    /// terminal or unknown jobs.
    pub fn cancel(&self, id: &str) -> bool {
        use std::sync::atomic::Ordering::Relaxed;
        let mut inner = self.lock();
        let Some(entry) = inner.entries.get_mut(id) else {
            return false;
        };
        if entry.state != STATE_RUNNING {
            return false;
        }
        entry.cancel.store(true, Relaxed);
        entry.state = STATE_CANCELLED.into();
        entry.detail = "Cancelled.".into();
        entry.finished_at = Some(Instant::now());
        true
    }

    /// Current `(state, detail)`, or `None` for unknown/expired jobs so each
    /// command keeps its own "not found" message.
    pub fn status(&self, id: &str) -> Option<(String, String)> {
        let mut inner = self.lock();
        Self::prune_locked(&mut inner, Instant::now());
        inner
            .entries
            .get(id)
            .map(|entry| (entry.state.clone(), entry.detail.clone()))
    }

    /// Number of tracked entries. Test and diagnostics aid.
    pub fn len(&self) -> usize {
        self.lock().entries.len()
    }

    pub fn is_empty(&self) -> bool {
        self.lock().entries.is_empty()
    }

    /// Prune terminal entries as of `now`. Test hook; production callers
    /// prune implicitly through [`JobStore::start`] and [`JobStore::status`].
    pub fn prune_at(&self, now: Instant) {
        Self::prune_locked(&mut self.lock(), now);
    }

    /// Length of the eviction queue. Test-only: must stay proportional to
    /// the live entry count even under churn (see `prune_locked`).
    #[cfg(test)]
    fn order_len(&self) -> usize {
        self.lock().order.len()
    }
}

/// Named timeout tiers for Hub-spawned work, so a future reader can tell a
/// deliberate 3600s install bound from a copy-pasted magic number. Every
/// Hub-spawned child process must use one of these; the only intentional
/// exception is the 10s synchronous permission-repair one-shot in the
/// gaming commands, which is documented at its call site.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum JobTimeoutClass {
    /// Synchronous unit probes (systemctl is-enabled/is-active and similar).
    Probe,
    /// Scheduler/preset one-shot applies (scx switch and similar).
    SchedulerApply,
    /// Uninstalls and container removals: no downloads, just teardown.
    QuickRemove,
    /// Channel switch, staged apply, explicit rollback: mutating but
    /// download-free.
    UpdateMutating,
    /// Container export scans and similar read-heavy inspections.
    ContainerScan,
    /// Flatpak tool installs (gaming + security grids).
    ToolInstall,
    /// Quick `just` recipe actions from the Hub actions page. Recipe fixes
    /// can legitimately pull images; keep under the privileged socket's own
    /// 910s bound.
    HubAction,
    /// Kali image pulls and Outlook archive conversions: large local work
    /// that is neither a recipe nor an OS update.
    ExtendedWork,
    /// Full image download + stage, and rclone cloud syncs: sustained
    /// network transfers. The watcher case must stay longer than its
    /// systemd TimeoutStartSec (2400s).
    LongTransfer,
}

pub fn timeout_for(class: JobTimeoutClass) -> Duration {
    match class {
        JobTimeoutClass::Probe => Duration::from_secs(5),
        JobTimeoutClass::SchedulerApply => Duration::from_secs(30),
        JobTimeoutClass::QuickRemove => Duration::from_secs(120),
        JobTimeoutClass::UpdateMutating => Duration::from_secs(300),
        JobTimeoutClass::ContainerScan => Duration::from_secs(300),
        JobTimeoutClass::ToolInstall => Duration::from_secs(600),
        JobTimeoutClass::HubAction => Duration::from_secs(900),
        JobTimeoutClass::ExtendedWork => Duration::from_secs(1800),
        JobTimeoutClass::LongTransfer => Duration::from_secs(3600),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn store_with_running(store: &JobStore, id: &str) -> Arc<AtomicBool> {
        store.start(id, format!("{id} running"))
    }

    #[test]
    fn finish_never_overwrites_cancelled() {
        let store = JobStore::default();
        store_with_running(&store, "job-1");
        assert!(store.cancel("job-1"));
        store.finish("job-1", STATE_COMPLETE, "late".into());
        assert_eq!(
            store.status("job-1"),
            Some((STATE_CANCELLED.into(), "Cancelled.".into()))
        );
    }

    #[test]
    fn cancel_terminal_or_unknown_is_false() {
        let store = JobStore::default();
        assert!(!store.cancel("missing"));
        store_with_running(&store, "job-1");
        store.finish("job-1", STATE_FAILED, "bad".into());
        assert!(!store.cancel("job-1"));
        assert_eq!(
            store.status("job-1").map(|(state, _)| state),
            Some(STATE_FAILED.into())
        );
    }

    #[test]
    fn cap_evicts_oldest_terminal_first() {
        let store = JobStore::default();
        for index in 0..MAX_JOBS {
            let id = format!("old-{index}");
            store_with_running(&store, &id);
            store.finish(&id, STATE_COMPLETE, "done".into());
        }
        assert_eq!(store.len(), MAX_JOBS);
        store_with_running(&store, "new-running");
        store.finish("new-running", STATE_COMPLETE, "done".into());
        assert_eq!(store.len(), MAX_JOBS);
        assert!(store.status("old-0").is_none());
        assert!(store.status("new-running").is_some());
    }

    #[test]
    fn cap_prefers_running_victims_last() {
        let store = JobStore::default();
        store_with_running(&store, "keep-running");
        for index in 0..MAX_JOBS {
            let id = format!("old-{index}");
            store_with_running(&store, &id);
            store.finish(&id, STATE_COMPLETE, "done".into());
        }
        // Full of terminal entries plus one running job: inserting evicts
        // terminal entries, never the running one, until none remain.
        assert!(store.status("keep-running").is_some());
    }

    #[test]
    fn prune_reaps_the_eviction_queue_under_churn() {
        let store = JobStore::default();
        for index in 0..(MAX_JOBS * 2) {
            let id = format!("churn-{index}");
            store_with_running(&store, &id);
            store.finish(&id, STATE_COMPLETE, "done".into());
        }
        let future = Instant::now() + TERMINAL_TTL + Duration::from_secs(1);
        store.prune_at(future);
        assert_eq!(store.len(), 0);
        assert_eq!(store.order_len(), 0);
    }

    #[test]
    fn ttl_prunes_terminal_but_keeps_running() {
        let store = JobStore::default();
        store_with_running(&store, "old-done");
        store.finish("old-done", STATE_COMPLETE, "done".into());
        store_with_running(&store, "still-running");
        let future = Instant::now() + TERMINAL_TTL + Duration::from_secs(1);
        store.prune_at(future);
        assert!(store.status("old-done").is_none());
        assert!(store.status("still-running").is_some());
    }

    #[test]
    fn timeout_tiers_are_ordered_and_bounded() {
        use JobTimeoutClass::*;
        let ordered = [
            Probe,
            SchedulerApply,
            QuickRemove,
            UpdateMutating,
            ContainerScan,
            ToolInstall,
            HubAction,
            ExtendedWork,
            LongTransfer,
        ];
        let durations: Vec<Duration> = ordered.iter().map(|class| timeout_for(*class)).collect();
        for pair in durations.windows(2) {
            assert!(pair[0] <= pair[1], "timeout tiers must be non-decreasing");
        }
        assert_eq!(timeout_for(Probe), Duration::from_secs(5));
        assert_eq!(timeout_for(SchedulerApply), Duration::from_secs(30));
        assert_eq!(timeout_for(LongTransfer), Duration::from_secs(3600));
        // Hub recipe actions must stay under the privileged daemon's own
        // 910s socket bound.
        assert!(timeout_for(HubAction) < Duration::from_secs(910));
    }
}
