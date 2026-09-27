/* global document, S, apiFetch, postRequest, postJSON, showError, goto, EventSource, appendLog, setProgress, showStats, onDone, setInterval */
// Install step (kicks off the backend install + streams its progress),
// the Rescue page, and page-load init — loads last so every step file
// above it (nav/disk/partition-editor/kernel/config/review) has already
// registered the functions goto()/loadDisks()/initKernel()/... call into.

// Called from index.html's inline onclick handler, not referenced within this file.
// eslint-disable-next-line no-unused-vars
function startInstall() {
  const btn = document.getElementById('install-now');
  if (btn.disabled) return;
  btn.disabled = true;
  btn.textContent = 'Starting…';

  postRequest('/api/start', {
    disk: S.disk.name, hostname: S.hostname,
    timezone: S.timezone, username: S.username, password: S.password,
    locale: S.locale, keymap: S.keymap,
    kernel: S.kernel,
    install_mode:      S.install_mode,
    target_partition:  S.target_partition || '',
    resize_partition:  S.resize_partition || '',
    resize_gib:        S.resize_gib || 0,
    free_region_start: S.free_region_start || 0,
    free_region_end:   S.free_region_end || 0,
    confirm_backup:    document.getElementById('confirm-backup').checked,
    confirm_erase:     document.getElementById('confirm-erase').checked,
    confirm_current:   document.getElementById('confirm-current').checked,
  }).then(r => {
    if (!r.ok) {
      btn.disabled = false;
      btn.textContent = 'Install Now';
      return r.json()
        .then(j => showError(j.message || ('Install request failed (status ' + r.status + ')')))
        .catch(() => r.text().then(t => showError('Failed to start install: ' + t))
          .catch(() => showError('Install request failed (status ' + r.status + ')')));
    }
    goto('install');
    S.password = '';
    document.getElementById('inp-password').value = '';
    document.getElementById('inp-password2').value = '';
    S.startTime = Date.now();
    S.elapsedTimer = setInterval(() => {
      const s = Math.floor((Date.now() - S.startTime) / 1000);
      const m = Math.floor(s / 60), sec = s % 60;
      document.getElementById('install-elapsed').textContent =
        m > 0 ? `${m}m ${sec}s` : `${sec}s`;
    }, 1000);
    listenSSE();
  }).catch(e => {
    btn.disabled = false;
    btn.textContent = 'Install Now';
    showError('The installer could not talk to its local backend: ' + e);
  });
}

function listenSSE() {
  const src = new EventSource('/api/stream');
  src.onmessage = e => {
    const ev = JSON.parse(e.data);
    if (ev.type === 'log')      appendLog(ev.text);
    else if (ev.type === 'progress') setProgress(ev.value);
    else if (ev.type === 'stats')    showStats(ev);
    else if (ev.type === 'done') { src.close(); onDone(ev.mok_state); }
    else if (ev.type === 'error'){ src.close(); showError(ev.message); }
  };
  src.onerror = () => {
    document.getElementById('install-phase').textContent = 'Reconnecting to installer…';
    // EventSource reconnects automatically and sends Last-Event-ID, so the
    // backend resumes at the next transaction event without duplicating logs.
  };
}

// ── Rescue ──────────────────────────────────────────────────────────────────────
function loadRescue() {
  const st = document.getElementById('rescue-status');
  st.textContent = 'Probing…';
  st.className = 'status-box status-info';
    apiFetch('/api/rescue/probe').then(r=>r.json()).then(d => {
    document.getElementById('rescue-log').textContent = d.log_tail || '(no log)';
    document.getElementById('rescue-verify').textContent = d.sgdisk_verify || '(no output)';
    document.getElementById('rescue-efi').textContent = d.efibootmgr || '(unavailable)';
    document.getElementById('rescue-bootc').textContent = d.bootc_status || '(unavailable)';
    document.getElementById('rescue-tx').textContent = JSON.stringify(d.transaction || {}, null, 2);
    const guide = d.rescue_guidance || {};
    if (guide.message) {
      const bootc = d.bootc_status_summary;
      const extra = (bootc && (bootc.booted || bootc.staged))
        ? ` Booted: ${bootc.booted||'—'} → Staged: ${bootc.staged||'—'}`
        : '';
      st.textContent = guide.message + extra;
      st.className = 'status-box ' + (guide.bootable ? 'status-ok' : (guide.severity === 'failed' ? 'status-err' : 'status-warn'));
    } else if (d.bootc_status_summary) {
      const s = d.bootc_status_summary;
      if (s.booted || s.staged) st.textContent = `Booted: ${s.booted||'—'} → Staged: ${s.staged||'—'}`;
      else { st.textContent = 'Probe complete — read-only checks finished.'; }
      st.className = 'status-box status-ok';
    } else { st.textContent = 'Probe complete — read-only checks finished.'; st.className = 'status-box status-ok'; }
  }).catch(e => {
    st.textContent = 'Probe failed: ' + e;
    st.className = 'status-box status-err';
  });
}
function copyRescueToUsb() {
  const st = document.getElementById('rescue-status');
  st.textContent = 'Copying logs to USB…';
  st.className = 'status-box status-info';
  postJSON('/api/rescue/logs-to-usb', {}).then(r=>r.json()).then(d => {
    if (d.ok) {
      st.textContent = 'Copied ' + (d.copied||[]).join(', ') + ' to ' + d.dest;
      st.className = 'status-box status-ok';
    } else {
      st.textContent = d.message || 'Copy failed';
      st.className = 'status-box status-err';
    }
  }).catch(e => {
    st.textContent = 'Copy failed: ' + e;
    st.className = 'status-box status-err';
  });
}

// These handlers are referenced by inline event attributes in index.html.
void [startInstall, loadRescue, copyRescueToUsb];

// ── Init ──────────────────────────────────────────────────────────────────────
apiFetch('/api/config').then(r=>r.json()).then(cfg => {
  S._sourceImage = cfg.source_image;
  S.source = cfg.source || null;
  S.isLive = cfg.is_live !== false;
  const welcome = document.getElementById('welcome-source');
  const confidence = document.getElementById('source-confidence');
  const confidenceText = document.getElementById('source-confidence-text');
  if (S.source && S.source.available && S.source.kind === 'embedded') {
    welcome.textContent = 'The standard KythOS image is verified and included on this ISO, so it installs offline.';
    confidenceText.textContent = 'Embedded release digest verified before disk changes';
  } else if (S.source && !S.source.available) {
    welcome.textContent = 'The embedded installation image failed validation. Installation will remain blocked.';
    welcome.style.color = 'var(--red)';
    confidence.classList.remove('ok');
    confidence.classList.add('warn');
    confidenceText.textContent = S.source.message || 'Image validation failed';
  } else {
    welcome.textContent = 'This installation source requires a network connection.';
    welcome.style.color = 'var(--amber)';
    confidenceText.textContent = 'Registry reachability checked before disk changes';
  }
});
goto('welcome');
