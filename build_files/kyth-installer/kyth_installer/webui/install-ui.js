/* global document, navigator, clearInterval, S, apiFetch, goto */
function setProgress(pct) {
  document.getElementById('progress-fill').style.width = pct + '%';
  document.getElementById('install-pct').textContent = pct + '%';
  const fill = document.getElementById('progress-fill');
  fill.parentElement.setAttribute('aria-valuenow', String(pct));
  if (pct >= 100) fill.classList.remove('pulsing');
  const imagePhase = S.kernel === 'fedora' && S.source && S.source.kind === 'embedded'
    ? 'Writing verified offline image…' : 'Downloading OS image…';
  const phases = {5:imagePhase,90:'Configuring…',95:'Creating user…',99:'Running final checks…'};
  for (const [phase, label] of Object.entries(phases).reverse()) {
    if (pct >= parseInt(phase)) {
      document.getElementById('install-phase').textContent = label;
      break;
    }
  }
}

function toggleAccessibility(feature) {
  document.body.classList.toggle(feature);
  const button = document.getElementById('toggle-' + feature);
  button.setAttribute('aria-pressed', document.body.classList.contains(feature) ? 'true' : 'false');
}

function fmtBytes(value) {
  if (value < 1024) return value + ' B';
  if (value < 1024**2) return (value/1024).toFixed(1) + ' KB';
  if (value < 1024**3) return (value/1024**2).toFixed(1) + ' MB';
  return (value/1024**3).toFixed(2) + ' GB';
}

function fmtEta(seconds) {
  if (seconds < 60) return seconds + 's';
  return Math.floor(seconds/60) + 'm ' + (seconds%60) + 's';
}

function showStats(stats) {
  const downloaded = fmtBytes(stats.downloaded);
  const total = fmtBytes(stats.total);
  const speed = fmtBytes(stats.speed) + '/s';
  const eta = stats.eta_sec > 0 ? fmtEta(stats.eta_sec) : '';
  document.getElementById('stats-row').textContent =
    `${downloaded} / ${total}  ·  ${speed}${eta ? '  ·  ETA ' + eta : ''}`;
}

function appendLog(text) {
  const wrap = document.getElementById('log-wrap');
  const line = document.createElement('div');
  if (text.startsWith('$ ')) line.className = 'log-cmd';
  else if (text.startsWith('──')) line.className = 'log-sep';
  line.textContent = text;
  wrap.appendChild(line);
  wrap.scrollTop = wrap.scrollHeight;
}

async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text || '');
  } catch (error) {
    const area = document.createElement('textarea');
    area.value = text || '';
    document.body.appendChild(area);
    area.select();
    document.execCommand('copy');
    document.body.removeChild(area);
  }
}

function copyVisibleLog() {
  copyText(document.getElementById('log-wrap').innerText || '');
}

function copyFullLog() {
  apiFetch('/api/log').then(response => response.text()).then(copyText).catch(copyVisibleLog);
}

function copyInstallReport() {
  apiFetch('/api/report')
    .then(response => response.json())
    .then(report => copyText(JSON.stringify(report, null, 2)))
    .catch(() => copyText('{"status":"report unavailable"}'));
}

function toggleLog() {
  const wrap = document.getElementById('log-wrap');
  const arrow = document.getElementById('log-arrow');
  const toggle = document.getElementById('log-toggle');
  const label = document.getElementById('log-toggle-label');
  const open = wrap.classList.toggle('open');
  arrow.classList.toggle('open', open);
  wrap.setAttribute('aria-hidden', String(!open));
  toggle.setAttribute('aria-expanded', String(open));
  label.textContent = open ? 'Hide install log' : 'Show install log';
}

function onDone(mokState) {
  clearInterval(S.elapsedTimer);
  if (mokState === 'staged' || mokState === 'pending') {
    document.getElementById('done-sb-notice').style.display = '';
  }
  const partial = ['alongside', 'resize_ntfs', 'free_space', 'manual'].includes(S.install_mode);
  if (partial) document.getElementById('done-boot-notice').style.display = '';
  goto('done');
}

function showError(message) {
  clearInterval(S.elapsedTimer);
  document.getElementById('err-msg').textContent = message;
  goto('error');
}

function backFromError() {
  goto(S.password ? 'review' : 'config');
}

function reboot() {
  document.body.innerHTML = '<div id="main" style="display:flex;align-items:center;justify-content:center"><div class="card" style="text-align:center;padding:48px 40px"><div class="done-title">Restarting</div><p class="hero-body">Remove the installation media when your computer begins to restart.</p></div></div>';
  apiFetch('/api/reboot', {method:'POST'}).catch(()=>{});
}

// Inline handlers in index.html are part of the installer UI's public surface.
void [toggleAccessibility, copyFullLog, copyInstallReport, toggleLog, backFromError, reboot];

// setProgress, showStats, appendLog, onDone, showError are called from install-flow.js.
void [setProgress, showStats, appendLog, onDone, showError];
