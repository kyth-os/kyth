const S = { disk: null, install_mode: 'wipe', target_partition: null,
  resize_partition: null,
  resize_gib: 64,
  free_region_start: 0, free_region_end: 0,
  hostname: 'kyth', timezone: 'UTC', username: '', password: '', kernel: 'fedora', isLive: true };
let SESSION_TOKEN = 'SESSION_TOKEN_PLACEHOLDER';
const STEPS = ['welcome','disk','kernel','config','review','install'];
const esc = s => String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');

function apiFetch(url, opts={}) {
  const o = {...opts, credentials:'same-origin'};
  const h = new Headers(o.headers || {});
  if (SESSION_TOKEN) h.set('X-Kyth-Session-Token', SESSION_TOKEN);
  o.headers = h;
  return fetch(url, o);
}

// ── Navigation ────────────────────────────────────────────────────────────────
function goto(name) {
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  document.getElementById('page-' + name).classList.add('active');
  document.querySelectorAll('.step').forEach(el => {
    const si = STEPS.indexOf(el.dataset.step), ai = STEPS.indexOf(name);
    el.classList.toggle('done',   si < ai);
    el.classList.toggle('active', si === ai);
    // ai may be -1 for non-step pages (error, done) — never pass '' to remove()
    if (si < ai)  el.classList.remove('active');
    if (si === ai) el.classList.remove('done');
  });
  if (name === 'disk')    loadDisks();
  if (name === 'kernel')  initKernel();
  if (name === 'config')  initConfig();
  if (name === 'review')  buildReview();
}

// ── Disk ──────────────────────────────────────────────────────────────────────
let _disks = [];
function loadDisks(attempt) {
  attempt = attempt || 0;
  document.getElementById('disk-grid').innerHTML = '<div class="status-box status-info">Scanning for disks…</div>';
  document.getElementById('disk-next').disabled  = true;
  document.getElementById('disk-warn').style.display = 'none';
  document.getElementById('mode-section').style.display = 'none';
  document.getElementById('partition-section').style.display = 'none';
  S.disk = null; S.install_mode = 'wipe'; S.target_partition = null;
  apiFetch('/api/disks').then(r=>r.json()).then(disks => {
    _disks = disks;
    const grid = document.getElementById('disk-grid');
    if (!disks.length) {
      if (attempt < 4) {
        setTimeout(() => loadDisks(attempt + 1), 1500);
      } else {
        grid.innerHTML = '<div class="status-box status-err">No disks found. Check that a disk is attached and click Refresh.</div>';
      }
      return;
    }
    grid.innerHTML = disks.map((d, i) => `
      <div class="disk-card" id="dcard-${i}" onclick="selectDisk(${i})">
        <div class="disk-icon">${d.rota ? '💿' : '💾'}</div>
        <div class="disk-info">
          <div class="disk-name">${esc(d.name)}</div>
          <div class="disk-detail">${esc(d.model)}${d.tran ? ' · '+esc(d.tran.toUpperCase()) : ''}${d.usb ? ' · USB storage' : ''}${d.current ? ' · current system disk' : ''}</div>
        </div>
        <div class="disk-size">${esc(d.size)}</div>
      </div>`).join('');
  }).catch(() => {
    document.getElementById('disk-grid').innerHTML = '<div class="status-box status-err">Failed to load disk list.</div>';
  });
}

function selectDisk(idx) {
  document.querySelectorAll('.disk-card').forEach(c => c.classList.remove('selected'));
  document.getElementById('dcard-' + idx).classList.add('selected');
  S.disk = _disks[idx];
  S.install_mode = 'wipe'; S.target_partition = null;
  S.resize_partition = null; S.free_region_start = 0; S.free_region_end = 0;
  document.querySelectorAll('.mode-card').forEach(c => c.classList.remove('selected'));
  document.getElementById('mcard-wipe').classList.add('selected');
  document.getElementById('partition-section').style.display = 'none';
  document.getElementById('mode-section').style.display = '';
  const warn = document.getElementById('disk-warn');
  warn.style.display = 'block';
  warn.textContent = S.disk.current
    ? (S.isLive
        ? '⚠ This appears to be the disk currently running this session. Reinstalling will replace it.'
        : '⚠ This is the running system disk. To reinstall this disk, boot from the KythOS live ISO.')
    : S.disk.usb
        ? '⚠ This is a USB storage device. Make sure you have the right disk selected.'
        : '⚠ All data on this disk will be permanently destroyed (Erase mode) or a partition will be erased (Alongside mode).';
  updateDiskNext();
}

function selectMode(id) {
  S.install_mode = id; S.target_partition = null;
  S.resize_partition = null; S.free_region_start = 0; S.free_region_end = 0;
  document.querySelectorAll('.mode-card').forEach(c => c.classList.remove('selected'));
  document.getElementById('mcard-' + id).classList.add('selected');
  const ps = document.getElementById('partition-section');
  ps.style.display = id === 'alongside' ? '' : 'none';
  if (id === 'alongside') loadPartitions();
  updateDiskNext();
}

let _partitions = [];
let _freeRegions = [];
function loadPartitions() {
  if (!S.disk) return;
  document.getElementById('part-grid').innerHTML = '<div class="status-box status-info">Loading partitions...</div>';
  document.getElementById('part-warn').style.display = 'none';
  document.getElementById('efi-info').style.display = 'none';
  Promise.all([
    apiFetch('/api/partitions?disk=' + encodeURIComponent(S.disk.name)).then(r=>r.json()),
    apiFetch('/api/free-space?disk=' + encodeURIComponent(S.disk.name)).then(r=>r.json()),
  ]).then(([parts, regions])=>{
    _partitions = parts;
    _freeRegions = regions;
    const box = document.getElementById('part-grid');
    if (!parts.length && !regions.length) {
      box.innerHTML = '<div class="warn-box">No partitions were found on this disk.</div>';
      updateDiskNext();
      return;
    }
    const hasEfi = parts.some(p => p.efi);
    document.getElementById('efi-info').style.display = hasEfi ? 'none' : 'block';
    const partCards = parts.map((p,i)=>{
      const fs = (p.fstype || '').toLowerCase();
      const isBtrfs = fs === 'btrfs' && !p.efi && !p.current;
      const isNtfs = (fs === 'ntfs' || fs === 'ntfs3') && !p.efi && !p.current;
      const selectedBtrfs = S.install_mode === 'alongside' && S.target_partition === p.name;
      const selectedNtfs = S.install_mode === 'resize_ntfs' && S.resize_partition === p.name;
      const badge = p.efi ? ' <span class="badge warn">EFI</span>' : (p.current ? ' <span class="badge warn">Mounted</span>' : '');
      let action = '';
      let klass = selectedBtrfs || selectedNtfs ? ' selected' : '';
      if (isBtrfs) {
        action = `<button class="secondary" type="button" onclick="selectPartition(${i})">Use partition</button>`;
      } else if (isNtfs) {
        const val = selectedNtfs ? S.resize_gib : 64;
        action = `<div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;justify-content:flex-end">
          <input id="resize-size-${i}" type="number" min="32" step="1" value="${val}" oninput="setResizeSize(${i}, this.value)" style="width:92px">
          <span style="font-size:12px;color:var(--muted)">GiB</span>
          <button class="secondary" type="button" onclick="selectResizePartition(${i})">Shrink NTFS</button>
        </div>`;
      } else {
        klass += ' locked';
        action = '<span style="font-size:12px;color:var(--muted)">Not eligible</span>';
      }
      return `<div class="part-card${klass}">
        <div class="part-info">
          <div class="part-name">${esc(p.name)}${badge}</div>
          <div class="part-meta">${esc(p.size)} · ${esc(p.fstype || 'unknown')}${p.label ? ' · ' + esc(p.label) : ''}</div>
        </div>
        ${action}
      </div>`;
    }).join('');
    const freeCards = regions.map((r,i)=>{
      const selected = S.install_mode === 'free_space' && S.free_region_start === r.start_bytes && S.free_region_end === r.end_bytes;
      return `<div class="part-card${selected ? ' selected' : ''}">
        <div class="part-info">
          <div class="part-name">Unallocated space <span class="badge">free</span></div>
          <div class="part-meta">${esc(r.size)} available</div>
        </div>
        <button class="secondary" type="button" onclick="selectFreeRegion(${i})">Use free space</button>
      </div>`;
    }).join('');
    box.innerHTML = partCards + freeCards;
    updateDiskNext();
  });
}

function setResizeSize(idx, value) {
  const p = _partitions[idx];
  if (!p) return;
  const n = Math.max(0, parseInt(value || '0', 10));
  if (S.resize_partition === p.name) S.resize_gib = n;
  updateDiskNext();
}


function selectPartition(idx) {
  const p = _partitions[idx];
  if (!p || p.efi || p.current || (p.fstype || '').toLowerCase() !== 'btrfs') return;
  S.install_mode = 'alongside';
  S.target_partition = p.name;
  S.resize_partition = null;
  S.free_region_start = 0; S.free_region_end = 0;
  document.getElementById('part-warn').style.display = 'none';
  loadPartitions();
  updateDiskNext();
}

function selectResizePartition(idx) {
  const p = _partitions[idx];
  const fs = (p && p.fstype || '').toLowerCase();
  if (!p || p.efi || p.current || (fs !== 'ntfs' && fs !== 'ntfs3')) return;
  const input = document.getElementById(`resize-size-${idx}`);
  S.install_mode = 'resize_ntfs';
  S.target_partition = null;
  S.resize_partition = p.name;
  S.resize_gib = Math.max(32, parseInt((input && input.value) || S.resize_gib || 64, 10));
  S.free_region_start = 0; S.free_region_end = 0;
  const warn = document.getElementById('part-warn');
  warn.textContent = 'The installer will shrink this NTFS partition, create a new Btrfs partition in the freed space, and install KythOS there. Back up important Windows files first.';
  warn.style.display = 'block';
  loadPartitions();
  updateDiskNext();
}

function selectFreeRegion(idx) {
  const r = _freeRegions[idx];
  if (!r) return;
  S.install_mode = 'free_space';
  S.target_partition = null;
  S.resize_partition = null;
  S.free_region_start = r.start_bytes;
  S.free_region_end = r.end_bytes;
  const warn = document.getElementById('part-warn');
  warn.textContent = `The installer will create a new ${esc(r.size)} Btrfs partition in this unallocated space and install KythOS there.`;
  warn.style.display = 'block';
  loadPartitions();
  updateDiskNext();
}


function updateDiskNext() {
  let ok = !!S.disk;
  if (S.install_mode === 'alongside') ok = ok && !!S.target_partition;
  if (S.install_mode === 'resize_ntfs') ok = ok && !!S.resize_partition && Number(S.resize_gib || 0) >= 32;
  if (S.install_mode === 'free_space') ok = ok && Number(S.free_region_end || 0) > Number(S.free_region_start || 0);
  const btn = document.getElementById('disk-next');
  if (btn) btn.disabled = !ok;
}


// ── Kernel ────────────────────────────────────────────────────────────────────
const KERNELS = [
  { id: 'fedora', icon: '🐧', name: 'KythOS Standard',
    desc: 'Standard KythOS kernel &middot; Works with Secure Boot out of the box',
    badge: 'Default' },
  { id: 'cachy',  icon: '⚡', name: 'KythOS Performance',
    desc: 'BORE scheduler &middot; sched-ext &middot; BBRv3 &middot; NTSYNC &middot; Optimized for gaming &amp; low-latency workloads',
    note: 'Secure Boot: the installer stages the KythOS signing key and you confirm enrollment on first boot' },
];

function initKernel() {
  const grid = document.getElementById('kernel-grid');
  if (grid.children.length) return;
  grid.innerHTML = KERNELS.map(k => `
    <div class="kernel-card${k.id === S.kernel ? ' selected' : ''}" id="kcard-${k.id}" role="button" tabindex="0" aria-pressed="${k.id === S.kernel ? 'true' : 'false'}" onclick="selectKernel('${k.id}')" onkeydown="if(event.key === 'Enter' || event.key === ' '){event.preventDefault();selectKernel('${k.id}')}">
      <div class="kernel-icon">${k.icon}</div>
      <div class="kernel-body">
        <div class="kernel-name">${k.name}${k.badge ? ` <span class="kernel-badge">${k.badge}</span>` : ''}</div>
        <div class="kernel-desc">${k.desc}</div>
        ${k.note ? `<div class="kernel-note">⚠ ${k.note}</div>` : ''}
      </div>
    </div>`).join('');
}

function selectKernel(id) {
  S.kernel = id;
  document.querySelectorAll('.kernel-card').forEach(c => c.classList.remove('selected'));
  document.querySelectorAll('.kernel-card').forEach(c => c.setAttribute('aria-pressed', 'false'));
  const card = document.getElementById('kcard-' + id);
  if (card) {
    card.classList.add('selected');
    card.setAttribute('aria-pressed', 'true');
  }
}

// ── Config ────────────────────────────────────────────────────────────────────
function initConfig() {
  const sel = document.getElementById('sel-tz');
  if (sel.options.length === 0) {
    apiFetch('/api/timezones').then(r=>r.json()).then(tzs => {
      const local = Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
      (tzs.length ? tzs : ['UTC']).forEach(tz => {
        const opt = document.createElement('option');
        opt.value = tz; opt.textContent = tz;
        if (tz === local) opt.selected = true;
        sel.appendChild(opt);
      });
    }).catch(() => {
      const opt = document.createElement('option');
      opt.value = 'UTC'; opt.textContent = 'UTC';
      opt.selected = true;
      sel.appendChild(opt);
    });
  }
}
function saveConfig() {
  const hostname = document.getElementById('inp-hostname').value.trim();
  const username = document.getElementById('inp-username').value.trim();
  const pw1      = document.getElementById('inp-password').value;
  const pw2      = document.getElementById('inp-password2').value;
  const errEl    = document.getElementById('user-error');
  errEl.textContent = '';

  if (!/^[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?$/.test(hostname)) {
    errEl.textContent = 'Hostname must contain only letters, digits, and hyphens.'; return;
  }
  if (!/^[a-z_][a-z0-9_-]{0,30}$/.test(username)) {
    errEl.textContent = 'Username must start with a letter, use only lowercase letters/digits/hyphens.'; return;
  }
  if (pw1.length < 1) { errEl.textContent = 'Password is required.'; return; }
  if (pw1 !== pw2)    { errEl.textContent = 'Passwords do not match.'; return; }

  S.hostname = hostname;
  S.timezone = document.getElementById('sel-tz').value;
  S.username = username;
  S.password = pw1;
  goto('review');
}

// ── Review ────────────────────────────────────────────────────────────────────
function buildReview() {
  const kernelLabels = { fedora: 'KythOS Standard', cachy: 'KythOS Performance' };
  const modeLabels   = { wipe: 'Erase Full Disk', alongside: 'Install Alongside', resize_ntfs: 'Shrink NTFS & Install', free_space: 'Use Free Space' };
  const targetImage = (() => {
    const base = S._sourceImage || '';
    if (!base || S.kernel === 'fedora') return base || '—';
    const colon = base.lastIndexOf(':');
    if (colon < 0) return base + '-cachy';
    let tag = base.slice(colon + 1);
    if (tag.endsWith('-cachy')) { tag = tag.slice(0, -'-cachy'.length); }
    return base.slice(0, colon + 1) + tag + '-cachy';
  })();
  const rows = [
    ['Disk',          S.disk ? `${S.disk.name}  (${S.disk.size})` : '—'],
    ['Model',         S.disk ? S.disk.model : '—'],
    ['Install Mode',  modeLabels[S.install_mode] || S.install_mode],
    ...(S.install_mode === 'resize_ntfs' ? [['Shrink NTFS', `${S.resize_partition} by ${S.resize_gib} GiB`]] : []),
    ...(S.install_mode === 'free_space' ? [['Free Space Region', (_freeRegions.find(r => r.start_bytes === S.free_region_start && r.end_bytes === S.free_region_end) || {}).size || '—']] : []),
  ];
  if (S.install_mode === 'alongside' && S.target_partition) {
    rows.push(['Target Partition', S.target_partition]);
    if (S.target_partition.fstype) rows.push(['Partition FS', S.target_partition.fstype]);
  }
  rows.push(
    ['Hostname', S.hostname],
    ['Timezone', S.timezone],
    ['Username', S.username],
    ['Password', '••••••••'],
    ['Kernel',   kernelLabels[S.kernel] || S.kernel],
    ['Image',    targetImage],
  );
  document.getElementById('review-table').innerHTML =
    rows.map(([k,v]) => `<tr><td>${k}</td><td>${esc(v)}</td></tr>`).join('');
  document.getElementById('confirm-backup').checked = false;
  document.getElementById('confirm-erase').checked = false;
  document.getElementById('confirm-current').checked = false;

  const isAlongside    = S.install_mode === 'alongside';
  const isCurrentNonLive = !isAlongside && S.disk && S.disk.current && !S.isLive;
  const isCurrentLive    = !isAlongside && S.disk && S.disk.current && S.isLive;

  document.getElementById('confirm-current-wrap').style.display = isCurrentLive ? 'flex' : 'none';
  document.getElementById('live-iso-required').style.display    = isCurrentNonLive ? 'block' : 'none';

  const partName = isAlongside && S.target_partition ? S.target_partition.name : '';
  const isFreeSpace = S.install_mode === 'free_space';
  document.getElementById('review-wipe').textContent = isCurrentNonLive
    ? '⚠ This is the running system disk — see notice below.'
    : isAlongside
        ? `⚠ Partition ${partName || '?'} will be erased and replaced with KythOS.`
        : isFreeSpace
            ? '⚠ A new partition will be created in the unallocated space and used for KythOS. Existing partitions are left untouched.'
            : (S.disk && S.disk.current
                ? '⚠ Reinstall target: this appears to be the disk currently running KythOS. The selected disk will be erased and replaced.'
                : '⚠ Everything on the selected disk will be permanently erased.');

  document.getElementById('confirm-erase-label').textContent = isAlongside
    ? `I understand partition ${partName || '?'} will be erased and replaced with KythOS.`
    : isFreeSpace
        ? 'I understand KythOS will be installed into the selected unallocated space.'
        : 'I understand KythOS will erase the selected disk and install a fresh system.';

  updateInstallReady();
}

function updateInstallReady() {
  const isAlongside = S.install_mode === 'alongside';
  if (!isAlongside && S.disk && S.disk.current && !S.isLive) {
    document.getElementById('install-now').disabled = true;
    return;
  }
  const backup    = document.getElementById('confirm-backup').checked;
  const erase     = document.getElementById('confirm-erase').checked;
  const currentOk = isAlongside || !(S.disk && S.disk.current) || document.getElementById('confirm-current').checked;
  document.getElementById('install-now').disabled = !(backup && erase && currentOk);
}

// ── Install ───────────────────────────────────────────────────────────────────
let _startTime = 0;
let _elapsedTimer = null;

function startInstall() {
  const btn = document.getElementById('install-now');
  if (btn.disabled) return;
  btn.disabled = true;
  btn.textContent = 'Starting…';

  apiFetch('/api/start', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
      disk: S.disk.name, hostname: S.hostname,
      timezone: S.timezone, username: S.username, password: S.password,
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
    }),
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
    _startTime = Date.now();
    _elapsedTimer = setInterval(() => {
      const s = Math.floor((Date.now() - _startTime) / 1000);
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
  src.onerror = () => { src.close(); showError('Lost connection to installer backend.'); };
}

function setProgress(pct) {
  document.getElementById('progress-fill').style.width = pct + '%';
  document.getElementById('install-pct').textContent   = pct + '%';
  const fill = document.getElementById('progress-fill');
  if (pct >= 100) fill.classList.remove('pulsing');
  const phases = {5:'Pulling OS image…',90:'Configuring…',95:'Creating user…',99:'Finalizing…'};
  for (const [p, label] of Object.entries(phases).reverse()) {
    if (pct >= parseInt(p)) { document.getElementById('install-phase').textContent = label; break; }
  }
}

function showStats(s) {
  const dl   = fmtBytes(s.downloaded), tot = fmtBytes(s.total);
  const spd  = fmtBytes(s.speed) + '/s';
  const eta  = s.eta_sec > 0 ? fmtEta(s.eta_sec) : '';
  document.getElementById('stats-row').textContent = `${dl} / ${tot}  ·  ${spd}${eta ? '  ·  ETA ' + eta : ''}`;
}

function fmtBytes(n) {
  if (n < 1024) return n + ' B';
  if (n < 1024**2) return (n/1024).toFixed(1) + ' KB';
  if (n < 1024**3) return (n/1024**2).toFixed(1) + ' MB';
  return (n/1024**3).toFixed(2) + ' GB';
}
function fmtEta(s) {
  if (s < 60) return s + 's';
  return Math.floor(s/60) + 'm ' + (s%60) + 's';
}

function appendLog(text) {
  const wrap = document.getElementById('log-wrap');
  const line = document.createElement('div');
  if (text.startsWith('$ '))       line.className = 'log-cmd';
  else if (text.startsWith('──')) line.className = 'log-sep';
  line.textContent = text;
  wrap.appendChild(line);
  wrap.scrollTop = wrap.scrollHeight;
}

async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text || '');
  } catch (e) {
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
  apiFetch('/api/log')
    .then(r => r.text())
    .then(t => copyText(t))
    .catch(() => copyVisibleLog());
}

function toggleLog() {
  const wrap  = document.getElementById('log-wrap');
  const arrow = document.getElementById('log-arrow');
  const open  = wrap.classList.toggle('open');
  arrow.classList.toggle('open', open);
}

function onDone(mokState) {
  clearInterval(_elapsedTimer);
  if (mokState === 'staged' || mokState === 'pending') {
    document.getElementById('done-sb-notice').style.display = '';
  }
  goto('done');
}

function showError(msg) {
  clearInterval(_elapsedTimer);
  document.getElementById('err-msg').textContent = msg;
  goto('error');
}

function reboot() {
  document.body.innerHTML = '<div id="main" style="display:flex;align-items:center;justify-content:center"><div class="card" style="text-align:center;padding:48px 40px"><div class="done-title">Restarting</div><p class="hero-body">Remove the installation media when your computer begins to restart.</p></div></div>';
  apiFetch('/api/reboot', {method:'POST'}).catch(()=>{});
}

// ── Init ──────────────────────────────────────────────────────────────────────
apiFetch('/api/config').then(r=>r.json()).then(cfg => {
  S._sourceImage = cfg.source_image;
  S.isLive = cfg.is_live !== false;
});
goto('welcome');
