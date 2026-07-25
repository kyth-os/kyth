/* global document, fetch, Headers, setTimeout, setInterval, clearInterval, Intl, EventSource, navigator */
const S = globalThis.KythInstallerState;
let SESSION_TOKEN = 'SESSION_TOKEN_PLACEHOLDER';
const STEPS = ['welcome','disk','kernel','config','review','install'];
// Build DOM nodes directly instead of assembling HTML strings — keeps
// backend-provided values (disk models, labels, …) out of markup entirely.
function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === null || v === undefined || v === false) continue;
    if (k === 'class') node.className = v;
    else if (k === 'text') node.textContent = v;
    else if (k === 'dataset') Object.assign(node.dataset, v);
    else if (k === 'style') node.style.cssText = v;
    else if (k.startsWith('on') && typeof v === 'function') node.addEventListener(k.slice(2), v);
    else node.setAttribute(k, v);
  }
  for (const c of children.flat()) {
    if (c !== null && c !== undefined) node.append(c.nodeType ? c : String(c));
  }
  return node;
}

function apiFetch(url, opts={}) {
  if (typeof url !== 'string' || !url.startsWith('/api/')) {
    throw new TypeError('API requests must use a same-origin /api/ route');
  }
  const o = {...opts, credentials:'same-origin'};
  const h = new Headers(o.headers || {});
  if (SESSION_TOKEN) h.set('X-Kyth-Session-Token', SESSION_TOKEN);
  o.headers = h;
  return fetch(url, o); // nosemgrep -- url is constrained to a same-origin API route above
}

function postRequest(url, body) {
  return apiFetch(url, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(body),
  });
}

function postJSON(url, body) {
  return postRequest(url, body).then(r => r.json());
}

// ── Navigation ────────────────────────────────────────────────────────────────
function goto(name) {
  document.querySelectorAll('.page').forEach(p => { p.classList.remove('active'); });
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
function loadDisks(attempt) {
  attempt = attempt || 0;
  document.getElementById('disk-grid').innerHTML = '<div class="status-box status-info">Scanning for disks…</div>';
  document.getElementById('disk-next').disabled  = true;
  document.getElementById('disk-warn').style.display = 'none';
  document.getElementById('mode-section').style.display = 'none';
  document.getElementById('partition-section').style.display = 'none';
  document.getElementById('visual-layout-section').style.display = 'none';
  S.disk = null; S.install_mode = 'wipe'; S.target_partition = null;
  S.resize_partition = null; S.free_region_start = 0; S.free_region_end = 0;
  apiFetch('/api/disks').then(r=>r.json()).then(disks => {
    S.disks = disks;
    const grid = document.getElementById('disk-grid');
    if (!disks.length) {
      if (attempt < 4) {
        setTimeout(() => loadDisks(attempt + 1), 1500);
      } else {
        grid.innerHTML = '<div class="status-box status-err">No disks found. Check that a disk is attached and click Refresh.</div>';
      }
      return;
    }
    grid.replaceChildren(...disks.map((d, i) =>
      el('div', { class: 'disk-card', id: `dcard-${i}`, onclick: () => selectDisk(i) },
        el('div', { class: 'disk-icon', text: d.rota ? '💿' : '💾' }),
        el('div', { class: 'disk-info' },
          el('div', { class: 'disk-name', text: d.name }),
          el('div', { class: 'disk-detail',
            text: `${d.model}${d.tran ? ' · ' + d.tran.toUpperCase() : ''}${d.usb ? ' · USB storage' : ''}${d.current ? ' · current system disk' : ''}` })),
        el('div', { class: 'disk-size', text: d.size }))));
  }).catch(() => {
    document.getElementById('disk-grid').innerHTML = '<div class="status-box status-err">Failed to load disk list.</div>';
  });
}

function selectDisk(idx) {
  document.querySelectorAll('.disk-card').forEach(c => { c.classList.remove('selected'); });
  document.getElementById('dcard-' + idx).classList.add('selected');
  // eslint-disable-next-line -- idx is a local array index, not user input
  S.disk = S.disks[idx];
  S.install_mode = 'wipe'; S.target_partition = null;
  S.resize_partition = null; S.free_region_start = 0; S.free_region_end = 0;
  document.querySelectorAll('.mode-card').forEach(c => { c.classList.remove('selected'); });
  document.getElementById('mcard-wipe').classList.add('selected');
  
  const warn = document.getElementById('disk-warn');
  warn.style.display = 'block';
  warn.textContent = S.disk.current
    ? (S.isLive
        ? '⚠ This appears to be the disk currently running this session. Reinstalling will replace it.'
        : '⚠ This is the running system disk. To reinstall this disk, boot from the KythOS live ISO.')
    : S.disk.usb
        ? '⚠ This is a USB storage device. Make sure you have the right disk selected.'
        : '⚠ Proceeding will write KythOS to the selected disk. Back up any important files first.';
  
  loadPartitions();
}

function selectMode(id) {
  S.install_mode = id; 
  S.target_partition = null;
  S.resize_partition = null; 
  S.free_region_start = 0; 
  S.free_region_end = 0;
  
  document.querySelectorAll('.mode-card').forEach(c => { c.classList.remove('selected'); });
  const card = document.getElementById('mcard-' + id);
  if (card) card.classList.add('selected');
  
  // Toggle control visibility
  document.getElementById('shrink-controls').style.display = id === 'resize_ntfs' ? 'block' : 'none';
  document.getElementById('replace-controls').style.display = id === 'alongside' ? 'block' : 'none';
  document.getElementById('free-space-controls').style.display = id === 'free_space' ? 'block' : 'none';
  document.getElementById('manual-controls').style.display = id === 'manual' ? 'block' : 'none';
  
  if (id === 'manual') {
    showManualControls();
  }
  
  // Auto-select defaults
  if (id === 'resize_ntfs') {
    const defaultNtfs = S.partitions.find(p => ['ntfs', 'ntfs3'].includes(p.fstype) && p.size_bytes >= 96 * 1024**3);
    if (defaultNtfs) selectResizePartitionByName(defaultNtfs.name);
  } else if (id === 'alongside') {
    const defaultReplace = S.partitions.find(p => !p.efi && !p.current && p.size_bytes >= 32 * 1024**3);
    if (defaultReplace) selectPartitionByName(defaultReplace.name);
  } else if (id === 'free_space') {
    const defaultFree = S.freeRegions.find(r => r.size_bytes >= 32 * 1024**3);
    if (defaultFree) selectFreeRegionByStart(defaultFree.start_bytes);
  }
  
  renderDiskLayouts();
  updateDiskNext();
}


function loadPartitions() {
  if (!S.disk) return;
  
  document.getElementById('mode-section').style.display = 'none';
  document.getElementById('partition-section').style.display = 'none';
  document.getElementById('visual-layout-section').style.display = 'none';
  
  Promise.all([
    apiFetch('/api/partitions?disk=' + encodeURIComponent(S.disk.name)).then(r=>r.json()),
    apiFetch('/api/free-space?disk=' + encodeURIComponent(S.disk.name)).then(r=>r.json()),
  ]).then(([parts, regions])=>{
    S.partitions = parts;
    S.freeRegions = regions;
    
    const hasEfi = parts.some(p => p.efi);
    const hasBiosBoot = parts.some(p => (p.parttype || '').toLowerCase() === '21686148-6449-6e6f-744e-656564454649');
    const needsBiosBoot = (S.disk.partition_table || '').toLowerCase() === 'gpt' && !hasBiosBoot;
    S.minGuidedGiB = needsBiosBoot ? 33 : 32;
    S.replaceAllowed = !needsBiosBoot;
    document.getElementById('efi-info').style.display = hasEfi ? 'none' : 'block';
    if (!hasEfi) {
      document.getElementById('efi-info').innerHTML = '<strong>No EFI System Partition found on this disk.</strong> KythOS installation requires an EFI partition. The Erase Disk mode will automatically create one, but Alongside, Replace, and Free Space modes require an existing EFI partition to configure boot files.';
    }
    
    // Enable/Disable mode cards based on candidates
    const hasNtfsCandidate = parts.some(p => ['ntfs', 'ntfs3'].includes(p.fstype) && p.size_bytes >= (64 + S.minGuidedGiB) * 1024**3);
    const hasFreeCandidate = regions.some(r => r.size_bytes >= S.minGuidedGiB * 1024**3);
    const hasReplaceCandidate = S.replaceAllowed && parts.some(p => !p.efi && !p.current && !p.in_use && p.size_bytes >= 32 * 1024**3);
    
    const mResize = document.getElementById('mcard-resize_ntfs');
    mResize.style.opacity = hasNtfsCandidate ? '1' : '0.4';
    mResize.style.pointerEvents = hasNtfsCandidate ? 'auto' : 'none';
    mResize.querySelector('.mode-desc').textContent = hasNtfsCandidate 
      ? 'Shrink an existing Windows/NTFS partition to make room for KythOS.'
      : 'Shrink Alongside (Unavailable: no NTFS partition >= 96 GiB found)';

    const mFree = document.getElementById('mcard-free_space');
    mFree.style.opacity = hasFreeCandidate ? '1' : '0.4';
    mFree.style.pointerEvents = hasFreeCandidate ? 'auto' : 'none';
    mFree.querySelector('.mode-desc').textContent = hasFreeCandidate
      ? 'Install KythOS into unallocated free space on the disk.'
      : 'Use Free Space (Unavailable: no free space >= 32 GiB found)';

    const mReplace = document.getElementById('mcard-alongside');
    mReplace.style.opacity = hasReplaceCandidate ? '1' : '0.4';
    mReplace.style.pointerEvents = hasReplaceCandidate ? 'auto' : 'none';
    mReplace.querySelector('.mode-desc').textContent = hasReplaceCandidate
      ? 'Overwrite an existing partition with KythOS.'
      : 'Replace a Partition (Unavailable: no partitions >= 32 GiB found)';

    // Manual mode always available (always needs user interaction)
    
    document.getElementById('mode-section').style.display = '';
    document.getElementById('partition-section').style.display = '';
    
    populateReplacementList();
    populateFreeSpaceList();
    
    // Select default mode
    selectMode('wipe');
  });
}

function getDiskBlocks(parts, diskSize) {
  const sortedParts = [...parts].sort((a, b) => a.start_bytes - b.start_bytes);
  const blocks = [];
  let cursor = 0;
  
  for (const p of sortedParts) {
    if (p.start_bytes > cursor) {
      blocks.push({
        type: 'free',
        start_bytes: cursor,
        size_bytes: p.start_bytes - cursor,
        name: 'Unallocated',
        fstype: ''
      });
    }
    blocks.push({
      type: 'part',
      start_bytes: p.start_bytes,
      size_bytes: p.size_bytes,
      name: p.name,
      fstype: p.fstype,
      label: p.label,
      efi: p.efi,
      current: p.current,
      ref: p
    });
    cursor = p.start_bytes + p.size_bytes;
  }
  
  if (cursor < diskSize) {
    blocks.push({
      type: 'free',
      start_bytes: cursor,
      size_bytes: diskSize - cursor,
      name: 'Unallocated',
      fstype: ''
    });
  }
  
  return blocks;
}

function blockToNode(block, isProposed = false) {
  let label = block.name ? block.name.replace('/dev/', '') : (block.type === 'free' ? 'Free' : 'KythOS');
  let typeStr = block.fstype ? block.fstype.toUpperCase() : (block.type === 'free' ? 'FREE' : '');
  if (block.efi) typeStr = 'EFI';
  if (block.isKythos) {
    label = 'KythOS';
    typeStr = 'BTRFS';
  }
  
  const sizeStr = fmtBytes(block.size_bytes);
  let klass = 'disk-part';
  
  if (block.isKythos) {
    klass += ' part-kythos';
  } else if (block.type === 'free') {
    klass += ' part-free';
  } else if (block.efi) {
    klass += ' part-efi';
  } else if (['ntfs', 'ntfs3'].includes(block.fstype)) {
    klass += ' part-ntfs';
  } else if (block.fstype === 'btrfs') {
    klass += ' part-btrfs';
  } else if (block.fstype === 'ext4') {
    klass += ' part-ext4';
  } else {
    klass += ' part-other';
  }
  
  let onclick = null;
  if (!isProposed) {
    if (S.install_mode === 'alongside' && S.replaceAllowed && block.type === 'part' && !block.efi && !block.current && !block.ref.in_use && block.size_bytes >= 32 * 1024**3) {
      klass += ' clickable';
      if (S.target_partition === block.name) klass += ' selected-target';
      onclick = () => selectPartitionByName(block.name);
    } else if (S.install_mode === 'resize_ntfs' && block.type === 'part' && ['ntfs', 'ntfs3'].includes(block.fstype) && block.size_bytes >= 96 * 1024**3) {
      klass += ' clickable';
      if (S.resize_partition === block.name) klass += ' selected-target';
      onclick = () => selectResizePartitionByName(block.name);
    } else if (S.install_mode === 'free_space' && block.type === 'free' && block.size_bytes >= S.minGuidedGiB * 1024**3) {
      klass += ' clickable';
      if (S.free_region_start === block.start_bytes) klass += ' selected-target';
      onclick = () => selectFreeRegionByStart(block.start_bytes);
    }
  } else {
    if (block.isKythos) {
      klass += ' selected-target';
    }
  }

  const isSmall = block.size_bytes < (S.disk.size_bytes * 0.08);
  const content = isSmall
    ? [el('span', { class: 'part-name-lbl', title: `${label} ${sizeStr}`, text: label })]
    : [el('span', { class: 'part-name-lbl', text: label }),
       el('span', { class: 'part-size-lbl', text: `${typeStr} · ${sizeStr}` })];

  return el('div', {
    class: klass,
    style: `flex-grow: ${block.size_bytes}; min-width: 45px;`,
    title: `${label} (${typeStr}) - ${sizeStr}`,
    onclick,
  }, content);
}

function renderDiskLayouts() {
  if (!S.disk) return;
  document.getElementById('visual-layout-section').style.display = 'block';
  
  const diskSize = S.disk.size_bytes;
  const blocks = getDiskBlocks(S.partitions, diskSize);
  
  // Render Current Layout
  const currentBar = document.getElementById('current-layout-bar');
  currentBar.replaceChildren(...blocks.map(b => blockToNode(b, false)));
  
  // Render Proposed Layout
  const proposedBar = document.getElementById('proposed-layout-bar');
  const proposedBlocks = [];
  
  if (S.install_mode === 'manual') {
    // For manual mode, reflect pending operations in the proposed layout
    const pendingCreates = S.pendingOps.filter(o => o.kind === 'create');
    const pendingDeletes = S.pendingOps.filter(o => o.kind === 'delete');
    const pendingResizes = S.pendingOps.filter(o => o.kind === 'resize');
    const deletedNames = new Set(pendingDeletes.map(o => o.params.partition));
    const resizedSizes = {};
    pendingResizes.forEach(o => { resizedSizes[o.params.partition] = o.params.new_size_bytes; });
    
    for (const b of blocks) {
      if (b.type === 'free') {
        // Check if any pending creates start here
        const createHere = pendingCreates.find(o => Number(o.params.start_bytes) === b.start_bytes);
        if (createHere) {
          proposedBlocks.push({
            type: 'part',
            size_bytes: Number(createHere.params.size_bytes),
            name: createHere.params.label || 'New',
            fstype: createHere.params.fs_type || 'btrfs',
            isKythos: createHere.params.mountpoint === '/',
          });
          // Remaining free space after the new partition
          const remaining = b.size_bytes - Number(createHere.params.size_bytes);
          if (remaining > 1024 * 1024) {
            proposedBlocks.push({ type: 'free', size_bytes: remaining, name: 'Free', fstype: '' });
          }
        } else {
          proposedBlocks.push(b);
        }
      } else if (deletedNames.has(b.name)) {
        // Mark as free space (will be gone after commit)
        proposedBlocks.push({ type: 'free', size_bytes: b.size_bytes, name: 'Free', fstype: '' });
      } else if (resizedSizes[b.name] !== undefined) {
        const newSize = resizedSizes[b.name];
        proposedBlocks.push({ type: 'part', size_bytes: newSize, name: b.name, fstype: b.fstype, efi: b.efi });
        const freed = b.size_bytes - newSize;
        if (freed > 1024 * 1024) {
          proposedBlocks.push({ type: 'free', size_bytes: freed, name: 'Freed Space', fstype: '' });
        }
      } else {
        proposedBlocks.push(b);
      }
    }
  } else if (S.install_mode === 'wipe') {
    // 512MB EFI + remaining Btrfs
    const efiSize = 512 * 1024 * 1024;
    proposedBlocks.push({
      type: 'part',
      size_bytes: efiSize,
      name: 'boot/efi',
      fstype: 'fat32',
      efi: true
    });
    proposedBlocks.push({
      type: 'part',
      size_bytes: diskSize - efiSize,
      name: 'KythOS',
      fstype: 'btrfs',
      isKythos: true
    });
  } else {
    for (const b of blocks) {
      if (S.install_mode === 'resize_ntfs' && b.name === S.resize_partition) {
        const shrinkBytes = S.resize_gib * 1024 * 1024 * 1024;
        proposedBlocks.push({
          type: 'part',
          size_bytes: b.size_bytes - shrinkBytes,
          name: b.name,
          fstype: b.fstype
        });
        proposedBlocks.push({
          type: 'part',
          size_bytes: shrinkBytes,
          name: 'KythOS',
          fstype: 'btrfs',
          isKythos: true
        });
      } else if (S.install_mode === 'alongside' && b.name === S.target_partition) {
        proposedBlocks.push({
          type: 'part',
          size_bytes: b.size_bytes,
          name: 'KythOS',
          fstype: 'btrfs',
          isKythos: true
        });
      } else if (S.install_mode === 'free_space' && b.type === 'free' && b.start_bytes === S.free_region_start) {
        proposedBlocks.push({
          type: 'part',
          size_bytes: b.size_bytes,
          name: 'KythOS',
          fstype: 'btrfs',
          isKythos: true
        });
      } else {
        proposedBlocks.push(b);
      }
    }
  }
  
  proposedBar.replaceChildren(...proposedBlocks.map(b => blockToNode(b, true)));
}

function selectPartitionByName(name) {
  S.target_partition = name;
  const pIdx = S.partitions.findIndex(p => p.name === name);
  if (pIdx >= 0) {
    const cards = document.querySelectorAll('#replace-list .part-selector-card');
    cards.forEach(c => { c.classList.toggle('selected', c.dataset.name === name); });
  }
  renderDiskLayouts();
  updateDiskNext();
}

function selectResizePartitionByName(name) {
  S.resize_partition = name;
  const p = S.partitions.find(part => part.name === name);
  if (p) {
    const maxShrinkGib = Math.floor((p.size_bytes - 64 * 1024**3) / 1024**3);
    const slider = document.getElementById('shrink-slider');
    slider.max = maxShrinkGib;
    slider.min = S.minGuidedGiB;
    const defaultVal = Math.min(maxShrinkGib, Math.max(S.minGuidedGiB, Math.floor(p.size_bytes / 2 / 1024**3)));
    slider.value = defaultVal;
    S.resize_gib = defaultVal;
    
    document.getElementById('shrink-label-old').textContent = `${p.name.replace('/dev/', '')} (shrunk): ${Math.floor(p.size_bytes / 1024**3) - S.resize_gib} GiB`;
    document.getElementById('shrink-label-new').textContent = `KythOS: ${S.resize_gib} GiB`;
  }
  renderDiskLayouts();
  updateDiskNext();
}

function selectFreeRegionByStart(start) {
  const r = S.freeRegions.find(region => region.start_bytes === start);
  if (r) {
    S.free_region_start = r.start_bytes;
    S.free_region_end = r.end_bytes;
    const cards = document.querySelectorAll('#free-space-list .part-selector-card');
    cards.forEach(c => { c.classList.toggle('selected', parseInt(c.dataset.start) === start); });
  }
  renderDiskLayouts();
  updateDiskNext();
}

function populateReplacementList() {
  const container = document.getElementById('replace-list');
  const replaceable = S.replaceAllowed
    ? S.partitions.filter(p => !p.efi && !p.current && !p.in_use && p.size_bytes >= 32 * 1024**3)
    : [];
  if (!replaceable.length) {
    container.innerHTML = '<div style="color:var(--muted);font-size:12px;padding:8px 0;">No partitions available to replace.</div>';
    return;
  }
  container.replaceChildren(...replaceable.map(p => {
    const isSelected = S.target_partition === p.name;
    const desc = `${p.fstype || 'unknown'} partition ${p.label ? ' · ' + p.label : ''}`;
    return el('div', {
      class: `part-selector-card${isSelected ? ' selected' : ''}`,
      dataset: { name: p.name },
      onclick: () => selectPartitionByName(p.name),
    },
      el('div', { class: 'part-meta-info' },
        el('span', { class: 'part-meta-name', text: p.name }),
        el('span', { class: 'part-meta-desc', text: desc })),
      el('span', { class: 'part-meta-size', text: p.size }));
  }));
}

function populateFreeSpaceList() {
  const container = document.getElementById('free-space-list');
  const freeGaps = S.freeRegions.filter(r => r.size_bytes >= S.minGuidedGiB * 1024**3);
  if (!freeGaps.length) {
    container.innerHTML = '<div style="color:var(--muted);font-size:12px;padding:8px 0;">No free space gaps available.</div>';
    return;
  }
  container.replaceChildren(...freeGaps.map(r => {
    const isSelected = S.free_region_start === r.start_bytes;
    return el('div', {
      class: `part-selector-card${isSelected ? ' selected' : ''}`,
      dataset: { start: r.start_bytes },
      onclick: () => selectFreeRegionByStart(r.start_bytes),
    },
      el('div', { class: 'part-meta-info' },
        el('span', { class: 'part-meta-name', text: 'Unallocated Space' }),
        el('span', { class: 'part-meta-desc', text: `At byte offset ${r.start_bytes}` })),
      el('span', { class: 'part-meta-size', text: r.size }));
  }));
}

// Called from index.html's inline onclick/oninput handlers, not referenced within this file.
// eslint-disable-next-line no-unused-vars
function onSliderMove(val) {
  S.resize_gib = parseInt(val, 10);
  const p = S.partitions.find(part => part.name === S.resize_partition);
  if (p) {
    document.getElementById('shrink-label-old').textContent = `${p.name.replace('/dev/', '')} (shrunk): ${Math.floor(p.size_bytes / 1024**3) - S.resize_gib} GiB`;
    document.getElementById('shrink-label-new').textContent = `KythOS: ${S.resize_gib} GiB`;
  }
  renderDiskLayouts();
  updateDiskNext();
}

function updateDiskNext() {
  let ok = !!S.disk;
  if (ok && S.install_mode === 'wipe' && S.disk.current && !S.isLive) ok = false;
  if (S.install_mode === 'alongside') ok = ok && !!S.target_partition;
  if (S.install_mode === 'resize_ntfs') ok = ok && !!S.resize_partition && Number(S.resize_gib || 0) >= S.minGuidedGiB;
  if (S.install_mode === 'free_space') ok = ok && Number(S.free_region_end || 0) > Number(S.free_region_start || 0);
  if (S.install_mode === 'manual') ok = ok && S.manualCommitted;
  const btn = document.getElementById('disk-next');
  if (btn) btn.disabled = !ok;
}


// ── Manual Partitioning ───────────────────────────────────────────────────

function showManualControls() {
  document.getElementById('manual-controls').style.display = 'block';
  document.getElementById('visual-layout-section').style.display = 'block';
  S.manualCommitted = false;
  S.pendingOps = [];
  loadFilesystems();
  loadPendingOps();
  updateManualButtons();
}

function loadFilesystems() {
  apiFetch('/api/disk/filesystems')
    .then(r => r.json())
    .then(fs => { S.supportedFilesystems = fs; })
    .catch(() => { S.supportedFilesystems = [
      {id:'btrfs',name:'Btrfs',root_ok:true,efi_ok:false},
      {id:'ext4',name:'ext4',root_ok:false,efi_ok:false},
      {id:'xfs',name:'XFS',root_ok:false,efi_ok:false},
      {id:'fat32',name:'FAT32',root_ok:false,efi_ok:true},
      {id:'linux-swap',name:'Swap',root_ok:false,efi_ok:false},
    ]; });
}

function loadPendingOps() {
  apiFetch('/api/disk/pending')
    .then(r => r.json())
    .then(ops => {
      S.pendingOps = ops;
      renderPendingOps();
      updateManualButtons();
    })
    .catch(() => {});
}

function renderPendingOps() {
  const list = document.getElementById('pending-list');
  const count = document.getElementById('pending-count');
  if (count) count.textContent = S.pendingOps.length;
  if (!S.pendingOps.length) {
    list.innerHTML = '<div style="color:var(--muted2);font-size:12px;padding:12px 0;">No pending partition operations. Use the toolbar above to modify the partition layout.</div>';
    return;
  }
  list.replaceChildren(...S.pendingOps.map((op, i) => {
    const desc = describeOp(op);
    return el('div', { class: 'pending-item' },
      el('span', { style: 'flex:1;font-size:13px;', text: desc }),
      el('button', {
        class: 'undo-btn',
        text: '✕',
        title: 'Remove this operation',
        onclick: () => removePendingOp(i),
      }));
  }));
}

function describeOp(op) {
  const p = op.params || {};
  switch (op.kind) {
    case 'new_table':    return `📋 New partition table: ${(p.table_type || 'gpt').toUpperCase()}`;
    case 'create':       return `➕ Add ${fmtBytes(p.size_bytes || 0)} ${p.fs_type || ''} partition${p.mountpoint ? ' at ' + p.mountpoint : ''}`;
    case 'delete':       return `🗑  Remove ${p.partition || 'partition'}`;
    case 'resize':       return `↔  Resize ${p.partition || ''} to ${fmtBytes(p.new_size_bytes || 0)}`;
    case 'format':       return `🔧 Format ${p.partition || ''} as ${p.fs_type || ''}`;
    case 'set_mountpoint': return `📂 Mount ${p.partition || ''} at ${p.mountpoint || '(none)'}`;
    default:             return `${op.kind}: ${JSON.stringify(p)}`;
  }
}

function removePendingOp() {
  // Remove from local state and force a re-fetch from server
  // The server may not support individual removal, so we reload
  showOverlay('Removing operation...', '', null);
  // For now, just reload the pending ops from the server
  loadPendingOps();
}

function updateManualButtons() {
  const hasRoot = S.pendingOps.some(op =>
    op.kind === 'set_mountpoint' && op.params.mountpoint === '/'
  ) || S.pendingOps.some(op =>
    op.kind === 'create' && op.params.mountpoint === '/'
  );
  const hasOps = S.pendingOps.length > 0;
  const commitBtn = document.getElementById('btn-commit');
  if (commitBtn) commitBtn.disabled = !hasOps || !hasRoot || S.manualCommitted;
  const rollbackBtn = document.getElementById('btn-rollback');
  if (rollbackBtn) rollbackBtn.disabled = !hasOps || S.manualCommitted;
}

function showNewTableDialog() {
  const content = el('div', {},
    el('div', { class: 'modal-title', text: 'New Partition Table' }),
    el('div', { style: 'color:var(--muted);font-size:13px;margin-bottom:16px;',
      text: 'This will erase the current partition table and all data on the disk.' }),
    el('div', { class: 'field-label', text: 'Partition Table Type' }),
    el('select', { id: 'dlg-table-type' },
      el('option', { value: 'gpt', text: 'GPT (recommended for UEFI)' }),
      el('option', { value: 'msdos', text: 'MBR / DOS (legacy BIOS)' }),
    ),
  );
  showOverlay('New Partition Table', content, () => {
    const tableType = document.getElementById('dlg-table-type').value;
    postJSON('/api/disk/new-table', { disk: S.disk.name, table_type: tableType }).then(j => {
      if (j.ok) {
        S.pendingOps = [];
        if (S.freeRegions) {
          // After new table, the whole disk is free space
          const diskSize = S.disk.size_bytes;
          const reserve = 1024 * 1024;
          S.freeRegions = [{
            start_bytes: reserve,
            end_bytes: diskSize - reserve,
            size_bytes: diskSize - 2 * reserve,
            size: fmtBytes(diskSize - 2 * reserve),
          }];
        }
        loadPendingOps();
        renderDiskLayouts();
        hideOverlay();
      } else {
        showOverlay('Error', el('div', { class: 'validation-errors', text: j.message || 'Failed to create table' }), null);
      }
    });
  });
}

function showCreateDialog() {
  const diskSize = S.disk ? S.disk.size_bytes : 0;
  const sectors = 1048576; // 1 MiB
  const defaultSize = Math.min(50 * 1024**3, Math.floor(diskSize * 0.3));
  const mountOpts = [
    el('option', { value: '', text: '(none)' }),
    el('option', { value: '/', text: '/ - Root (Btrfs required)' }),
    el('option', { value: '/home', text: '/home' }),
    el('option', { value: '/boot', text: '/boot' }),
    el('option', { value: '/boot/efi', text: '/boot/efi (FAT32 required)' }),
    el('option', { value: 'swap', text: 'swap' }),
  ];

  // Populate free space regions for start offset picker
  const freeRegions = S.freeRegions || [];
  const startOpts = freeRegions.length
    ? freeRegions.map(r => el('option', { value: r.start_bytes, text: `At ${r.start_bytes} (${r.size})` }))
    : [el('option', { value: sectors, text: `After 1 MiB gap (${fmtBytes(diskSize - 2*sectors)})` })];

  const content = el('div', {},
    el('div', { class: 'modal-title', text: 'Create Partition' }),
    el('div', { class: 'field-label', text: 'Free Space Region' }),
    el('select', { id: 'dlg-start' }, ...startOpts),
    el('div', { class: 'field-label', text: 'Size (GiB)' }),
    el('input', { type: 'number', id: 'dlg-size', value: Math.floor(defaultSize / 1024**3), min: 1, max: Math.floor(diskSize / 1024**3) }),
    el('div', { class: 'field-label', text: 'Filesystem Type' }),
    el('select', { id: 'dlg-fs' },
      ...(S.supportedFilesystems.length
        ? S.supportedFilesystems.map(f => el('option', { value: f.id, text: f.name }))
        : [el('option', { value: 'btrfs', text: 'Btrfs' }),
           el('option', { value: 'ext4', text: 'ext4' }),
           el('option', { value: 'xfs', text: 'XFS' }),
           el('option', { value: 'fat32', text: 'FAT32' }),
           el('option', { value: 'linux-swap', text: 'Swap' })])),
    el('div', { class: 'field-label', text: 'Mount Point' }),
    el('select', { id: 'dlg-mount' }, ...mountOpts),
    el('div', { class: 'field-label', text: 'Label (optional)' }),
    el('input', { type: 'text', id: 'dlg-label', placeholder: 'e.g. Data' }),
  );
  showOverlay('Create Partition', content, () => {
    const start = parseInt(document.getElementById('dlg-start').value);
    const sizeGiB = parseFloat(document.getElementById('dlg-size').value);
    const fsType = document.getElementById('dlg-fs').value;
    const mountpoint = document.getElementById('dlg-mount').value;
    const label = document.getElementById('dlg-label').value.trim();
    const sizeBytes = Math.floor(sizeGiB * 1024**3);
    postJSON('/api/disk/create', {
      disk: S.disk.name,
      start_bytes: start,
      size_bytes: sizeBytes,
      fs_type: fsType,
      label: label,
      mountpoint: mountpoint,
    }).then(j => {
      if (j.ok) {
        // The mountpoint is already part of the /api/disk/create request body
        // above and stored on the create op server-side — no follow-up
        // set-mountpoint call is needed (and none is possible yet: the
        // partition doesn't have a device name until commit() actually runs
        // parted, so a call here could only ever target a placeholder name).
        loadPendingOps();
        loadPartitions();
        renderDiskLayouts();
        hideOverlay();
      } else {
        const msgs = j.errors ? j.errors.join('\n') : (j.message || 'Create failed');
        showOverlay('Error', el('div', { class: 'validation-errors', text: msgs }), null);
      }
    });
  });
}

function showDeleteDialog() {
  const parts = S.partitions || [];
  const selectable = parts.filter(p => !p.current && !p.in_use && !p.efi);
  if (!selectable.length) {
    showOverlay('No Removable Partitions',
      el('div', { style: 'color:var(--muted);', text: 'No partitions available to delete.' }), null);
    return;
  }
  const content = el('div', {},
    el('div', { class: 'modal-title', text: 'Delete Partition' }),
    el('div', { class: 'field-label', text: 'Select Partition' }),
    el('select', { id: 'dlg-del-part' },
      ...selectable.map(p => el('option', { value: p.name, text: `${p.name} (${p.size})` }))),
    el('div', { style: 'color:var(--red);font-size:13px;margin-top:12px;',
      text: '⚠ This will erase all data on the selected partition.' }),
  );
  showOverlay('Delete Partition', content, () => {
    const part = document.getElementById('dlg-del-part').value;
    postJSON('/api/disk/delete', { disk: S.disk.name, partition: part }).then(j => {
      if (j.ok) {
        loadPendingOps();
        loadPartitions();
        renderDiskLayouts();
        hideOverlay();
      }
    });
  });
}

function showResizeDialog() {
  const parts = S.partitions || [];
  const selectable = parts.filter(p => !p.current && !p.in_use && !p.efi && p.size_bytes >= 40 * 1024**3);
  if (!selectable.length) {
    showOverlay('No Resizable Partitions',
      el('div', { style: 'color:var(--muted);', text: 'No partitions available to resize (need >= 40 GiB).' }), null);
    return;
  }
  const content = el('div', {},
    el('div', { class: 'modal-title', text: 'Resize Partition (Shrink)' }),
    el('div', { class: 'field-label', text: 'Select Partition' }),
    el('select', { id: 'dlg-resize-part' },
      ...selectable.map(p => el('option', { value: p.name, text: `${p.name} (${p.size})` }))),
    el('div', { class: 'field-label', text: 'New Size (GiB)' }),
    el('input', { type: 'number', id: 'dlg-resize-size', value: 32, min: 32, max: 100 }),
    el('div', { style: 'color:var(--amber);font-size:12px;margin-top:8px;',
      text: '⚠ Only shrinking is supported. The partition will be shrunk from its end.' }),
  );
  showOverlay('Resize Partition', content, () => {
    const part = document.getElementById('dlg-resize-part').value;
    const newSizeGiB = parseFloat(document.getElementById('dlg-resize-size').value);
    const newSizeBytes = Math.floor(newSizeGiB * 1024**3);
    postJSON('/api/disk/resize', { disk: S.disk.name, partition: part, new_size_bytes: newSizeBytes }).then(j => {
      if (j.ok) {
        loadPendingOps();
        loadPartitions();
        renderDiskLayouts();
        hideOverlay();
      }
    });
  });
}

function showFormatDialog() {
  const parts = S.partitions || [];
  const selectable = parts.filter(p => !p.current && !p.in_use);
  if (!selectable.length) {
    showOverlay('No Formattable Partitions',
      el('div', { style: 'color:var(--muted);', text: 'No partitions available to format.' }), null);
    return;
  }
  const content = el('div', {},
    el('div', { class: 'modal-title', text: 'Format Partition' }),
    el('div', { class: 'field-label', text: 'Select Partition' }),
    el('select', { id: 'dlg-fmt-part' },
      ...selectable.map(p => el('option', { value: p.name, text: `${p.name} (${p.size}) - ${p.fstype || 'unknown'}` }))),
    el('div', { class: 'field-label', text: 'Filesystem' }),
    el('select', { id: 'dlg-fmt-fs' },
      ...(S.supportedFilesystems.length
        ? S.supportedFilesystems.map(f => el('option', { value: f.id, text: f.name }))
        : [el('option', { value: 'btrfs', text: 'Btrfs' }),
           el('option', { value: 'ext4', text: 'ext4' })])),
    el('div', { class: 'field-label', text: 'Label (optional)' }),
    el('input', { type: 'text', id: 'dlg-fmt-label', placeholder: 'e.g. Data' }),
    el('div', { style: 'color:var(--red);font-size:13px;margin-top:12px;',
      text: '⚠ This will erase all data on the selected partition.' }),
  );
  showOverlay('Format Partition', content, () => {
    const part = document.getElementById('dlg-fmt-part').value;
    const fsType = document.getElementById('dlg-fmt-fs').value;
    const label = document.getElementById('dlg-fmt-label').value.trim();
    postJSON('/api/disk/format', { disk: S.disk.name, partition: part, fs_type: fsType, label: label }).then(j => {
      if (j.ok) {
        loadPendingOps();
        loadPartitions();
        renderDiskLayouts();
        hideOverlay();
      } else {
        showOverlay('Error', el('div', { class: 'validation-errors', text: j.message || 'Format failed' }), null);
      }
    });
  });
}

function showMountDialog() {
  const parts = S.partitions || [];
  const content = el('div', {},
    el('div', { class: 'modal-title', text: 'Set Mount Point' }),
    el('div', { class: 'field-label', text: 'Select Partition' }),
    el('select', { id: 'dlg-mount-part' },
      ...parts.map(p => el('option', { value: p.name, text: `${p.name} (${p.size})` }))),
    el('div', { class: 'field-label', text: 'Mount Point' }),
    el('select', { id: 'dlg-mount-point' },
      el('option', { value: '', text: '(none)' }),
      el('option', { value: '/', text: '/ - Root' }),
      el('option', { value: '/home', text: '/home' }),
      el('option', { value: '/boot', text: '/boot' }),
      el('option', { value: '/var', text: '/var' }),
      el('option', { value: '/opt', text: '/opt' }),
      el('option', { value: '/srv', text: '/srv' }),
      el('option', { value: '/usr/local', text: '/usr/local' }),
      el('option', { value: 'swap', text: '[swap]' }),
    ),
    el('div', { class: 'field-label', text: 'Or type custom path' }),
    el('input', { type: 'text', id: 'dlg-mount-custom', placeholder: 'e.g. /data' }),
  );
  showOverlay('Set Mount Point', content, () => {
    const part = document.getElementById('dlg-mount-part').value;
    let mountpoint = document.getElementById('dlg-mount-point').value;
    const custom = document.getElementById('dlg-mount-custom').value.trim();
    if (custom) mountpoint = custom;
    postJSON('/api/disk/set-mountpoint', { disk: S.disk.name, partition: part, mountpoint }).then(j => {
      if (j.ok) {
        loadPendingOps();
        renderDiskLayouts();
        hideOverlay();
      } else {
        showOverlay('Error', el('div', { class: 'validation-errors', text: j.message || 'Failed' }), null);
      }
    });
  });
}

function commitPartitions() {
  const btn = document.getElementById('btn-commit');
  if (btn) btn.disabled = true;
  showOverlay('Applying Changes',
    el('div', { style: 'color:var(--muted);', text: 'Writing partition changes to disk...' }), null);

  postJSON('/api/disk/commit', { disk: S.disk.name }).then(j => {
    hideOverlay();
    if (j.ok) {
      S.manualCommitted = true;
      S.pendingOps = [];
      renderPendingOps();
      updateManualButtons();
      // Reload the partition list to reflect the changes
      loadPartitions();
      // Show success
      showOverlay('Changes Applied',
        el('div', { style: 'color:var(--green);font-size:14px;',
          text: `Partition changes written successfully. Root partition: ${j.root_partition || 'set'}` }),
        null, 'OK');
    } else {
      const msgs = j.errors ? j.errors.join('\n') : (j.message || 'Commit failed');
      showOverlay('Error', el('div', { class: 'validation-errors', text: msgs }), null);
      if (btn) btn.disabled = false;
    }
  }).catch(() => {
    hideOverlay();
    showOverlay('Error', el('div', { class: 'validation-errors', text: 'Failed to commit partition changes.' }), null);
    if (btn) btn.disabled = false;
  });
}

function rollbackPartitions() {
  showOverlay('Undo All Changes',
    el('div', { style: 'color:var(--muted);', text: 'Restoring previous partition table...' }), null);
  postJSON('/api/disk/rollback', { disk: S.disk.name }).then(j => {
    hideOverlay();
    if (j.ok) {
      S.manualCommitted = false;
      S.pendingOps = [];
      renderPendingOps();
      updateManualButtons();
      loadPartitions();
      renderDiskLayouts();
      showOverlay('Undo Complete',
        el('div', { style: 'color:var(--green);font-size:14px;',
          text: 'Partition table restored to previous state.' }),
        null, 'OK');
    } else {
      showOverlay('Error', el('div', { class: 'validation-errors', text: j.message || 'Rollback failed' }), null);
    }
  });
}

// ── Overlay Modal ─────────────────────────────────────────────────────────
function showOverlay(title, body, onConfirm, confirmLabel) {
  const overlay = document.getElementById('modal-overlay');
  const content = document.getElementById('modal-content');
  if (!overlay || !content) return;
  const actions = el('div', { class: 'modal-actions' });
  if (onConfirm) {
    const okBtn = el('button', {
      class: 'primary',
      text: confirmLabel || 'Apply',
      onclick: () => onConfirm(),
    });
    actions.appendChild(okBtn);
  }
  const cancelBtn = el('button', {
    text: confirmLabel ? 'Cancel' : 'Close',
    onclick: () => hideOverlay(),
  });
  actions.appendChild(cancelBtn);
  content.replaceChildren(
    typeof title === 'string' ? el('div', { class: 'modal-title', text: title }) : title,
    body,
    actions,
  );
  overlay.style.display = '';
}

function hideOverlay() {
  const overlay = document.getElementById('modal-overlay');
  if (overlay) overlay.style.display = 'none';
}


// ── Kernel ────────────────────────────────────────────────────────────────────
const KERNELS = [
  { id: 'fedora', icon: '🐧', name: 'KythOS Standard',
    desc: 'Standard KythOS kernel · Works with Secure Boot out of the box',
    badge: 'Default' },
  { id: 'cachy',  icon: '⚡', name: 'KythOS Performance',
    desc: 'BORE scheduler · sched-ext · BBRv3 · NTSYNC · Optimized for gaming & low-latency workloads',
    note: 'Secure Boot: the installer stages the KythOS signing key and you confirm enrollment on first boot' },
];

function initKernel() {
  const grid = document.getElementById('kernel-grid');
  if (grid.children.length) return;
  grid.replaceChildren(...KERNELS.map(k => {
    const selected = k.id === S.kernel;
    return el('div', {
      class: `kernel-card${selected ? ' selected' : ''}`,
      id: `kcard-${k.id}`,
      role: 'button',
      tabindex: '0',
      'aria-pressed': selected ? 'true' : 'false',
      onclick: () => selectKernel(k.id),
      onkeydown: (event) => {
        if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); selectKernel(k.id); }
      },
    },
      el('div', { class: 'kernel-icon', text: k.icon }),
      el('div', { class: 'kernel-body' },
        el('div', { class: 'kernel-name' },
          k.name,
          k.badge ? ' ' : null,
          k.badge ? el('span', { class: 'kernel-badge', text: k.badge }) : null),
        el('div', { class: 'kernel-desc', text: k.desc }),
        k.note ? el('div', { class: 'kernel-note', text: `⚠ ${k.note}` }) : null));
  }));
}

function selectKernel(id) {
  S.kernel = id;
  document.querySelectorAll('.kernel-card').forEach(c => { c.classList.remove('selected'); });
  document.querySelectorAll('.kernel-card').forEach(c => { c.setAttribute('aria-pressed', 'false'); });
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
// Called from index.html's inline onclick/oninput handlers, not referenced within this file.
// eslint-disable-next-line no-unused-vars
function saveConfig() {
  const hostname = document.getElementById('inp-hostname').value.trim();
  const username = document.getElementById('inp-username').value.trim();
  const pw1      = document.getElementById('inp-password').value;
  const pw2      = document.getElementById('inp-password2').value;
  const errEl    = document.getElementById('user-error');
  errEl.textContent = '';

  // eslint-disable-next-line -- bounded, linear-time expression, safe from ReDoS
  if (!/^[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?$/.test(hostname)) { // nosemgrep -- bounded, linear-time expression
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
  const modeLabels   = { wipe: 'Erase Full Disk', alongside: 'Install Alongside', resize_ntfs: 'Shrink NTFS & Install', free_space: 'Use Free Space', manual: 'Manual Partitioning' };
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
    ...(S.install_mode === 'free_space' ? [['Free Space Region', (S.freeRegions.find(r => r.start_bytes === S.free_region_start && r.end_bytes === S.free_region_end) || {}).size || '—']] : []),
  ];
  if (S.install_mode === 'manual') {
    rows.push(['Partition Layout', 'Manual — see partition table']);
    const manualMounts = S.pendingOps.filter(o => o.kind === 'set_mountpoint' && o.params.mountpoint);
    for (const m of manualMounts.slice(0, 5)) {
      rows.push([`  ${m.params.partition || ''}`, m.params.mountpoint || '']);
    }
  }
  if (S.install_mode === 'alongside' && S.target_partition) {
    rows.push(['Target Partition', S.target_partition]);
    const targetPart = S.partitions.find(p => p.name === S.target_partition);
    if (targetPart && targetPart.fstype) rows.push(['Partition FS', targetPart.fstype]);
  }
  rows.push(
    ['Hostname', S.hostname],
    ['Timezone', S.timezone],
    ['Username', S.username],
    ['Password', '••••••••'],
    ['Kernel',   kernelLabels[S.kernel] || S.kernel],
    ['Image',    targetImage],
  );
  document.getElementById('review-table').replaceChildren(
    ...rows.map(([k, v]) => el('tr', {}, el('td', { text: k }), el('td', { text: String(v) }))));
  document.getElementById('confirm-backup').checked = false;
  document.getElementById('confirm-erase').checked = false;
  document.getElementById('confirm-current').checked = false;

  const isAlongside  = S.install_mode === 'alongside';
  const isResizeNtfs = S.install_mode === 'resize_ntfs';
  const isFreeSpace  = S.install_mode === 'free_space';
  const isManual     = S.install_mode === 'manual';
  const isPartial    = isAlongside || isResizeNtfs || isFreeSpace || isManual;

  const isCurrentNonLive = !isPartial && S.disk && S.disk.current && !S.isLive;
  const isCurrentLive    = !isPartial && S.disk && S.disk.current && S.isLive;

  document.getElementById('confirm-current-wrap').style.display = isCurrentLive ? 'flex' : 'none';
  document.getElementById('live-iso-required').style.display    = isCurrentNonLive ? 'block' : 'none';

  const partName = isAlongside && S.target_partition ? S.target_partition : '';
  document.getElementById('review-wipe').textContent = isCurrentNonLive
    ? '⚠ This is the running system disk — see notice below.'
    : isAlongside
        ? `⚠ Partition ${partName || '?'} will be erased and replaced with KythOS.`
        : isResizeNtfs
            ? `⚠ ${S.resize_partition || 'The selected NTFS partition'} will be shrunk by ${S.resize_gib} GiB. Windows and its files are preserved, but back up anything important first.`
            : isFreeSpace
                ? '⚠ A new partition will be created in the unallocated space and used for KythOS. Existing partitions are left untouched.'
                : (S.disk && S.disk.current
                    ? '⚠ Reinstall target: this appears to be the disk currently running KythOS. The selected disk will be erased and replaced.'
                    : '⚠ Everything on the selected disk will be permanently erased.');

  document.getElementById('confirm-erase-label').textContent = isAlongside
    ? `I understand partition ${partName || '?'} will be erased and replaced with KythOS.`
    : isResizeNtfs
        ? `I understand ${S.resize_partition || 'the selected NTFS partition'} will be shrunk by ${S.resize_gib} GiB to make room for KythOS.`
        : isFreeSpace
            ? 'I understand KythOS will be installed into the selected unallocated space.'
            : 'I understand KythOS will erase the selected disk and install a fresh system.';

  updateInstallReady();
}

function updateInstallReady() {
  const isPartial = S.install_mode === 'alongside' || S.install_mode === 'resize_ntfs' || S.install_mode === 'free_space' || S.install_mode === 'manual';
  if (!isPartial && S.disk && S.disk.current && !S.isLive) {
    document.getElementById('install-now').disabled = true;
    return;
  }
  const backup    = document.getElementById('confirm-backup').checked;
  const erase     = document.getElementById('confirm-erase').checked;
  const currentOk = isPartial || !(S.disk && S.disk.current) || document.getElementById('confirm-current').checked;
  document.getElementById('install-now').disabled = !(backup && erase && currentOk);
}

// ── Install ───────────────────────────────────────────────────────────────────

// Called from index.html's inline onclick/oninput handlers, not referenced within this file.
// eslint-disable-next-line no-unused-vars
function startInstall() {
  const btn = document.getElementById('install-now');
  if (btn.disabled) return;
  btn.disabled = true;
  btn.textContent = 'Starting…';

  postRequest('/api/start', {
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

// Called from index.html's inline onclick/oninput handlers, not referenced within this file.
// eslint-disable-next-line no-unused-vars
function copyFullLog() {
  apiFetch('/api/log')
    .then(r => r.text())
    .then(t => copyText(t))
    .catch(() => copyVisibleLog());
}

// Called from index.html's inline onclick/oninput handlers, not referenced within this file.
// eslint-disable-next-line no-unused-vars
function toggleLog() {
  const wrap  = document.getElementById('log-wrap');
  const arrow = document.getElementById('log-arrow');
  const toggle = document.getElementById('log-toggle');
  const label = document.getElementById('log-toggle-label');
  const open  = wrap.classList.toggle('open');
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
  const isPartial = S.install_mode === 'alongside' || S.install_mode === 'resize_ntfs' || S.install_mode === 'free_space' || S.install_mode === 'manual';
  if (isPartial) {
    document.getElementById('done-boot-notice').style.display = '';
  }
  goto('done');
}

function showError(msg) {
  clearInterval(S.elapsedTimer);
  document.getElementById('err-msg').textContent = msg;
  goto('error');
}

// Called from index.html's inline onclick/oninput handlers, not referenced within this file.
// eslint-disable-next-line no-unused-vars
function backFromError() {
  // S.password is wiped once an install starts, so a retry straight from the
  // review page would POST an empty password. Route through Configure to make
  // the user re-enter it whenever it is gone.
  goto(S.password ? 'review' : 'config');
}

// Called from index.html's inline onclick/oninput handlers, not referenced within this file.
// eslint-disable-next-line no-unused-vars
function reboot() {
  document.body.innerHTML = '<div id="main" style="display:flex;align-items:center;justify-content:center"><div class="card" style="text-align:center;padding:48px 40px"><div class="done-title">Restarting</div><p class="hero-body">Remove the installation media when your computer begins to restart.</p></div></div>';
  apiFetch('/api/reboot', {method:'POST'}).catch(()=>{});
}

// These handlers are referenced by inline event attributes in index.html.
// Keeping an explicit reference list lets standalone JS analyzers see the
// cross-file usage without changing the browser-facing API.
void [
  onSliderMove, showNewTableDialog, showCreateDialog, showDeleteDialog,
  showResizeDialog, showFormatDialog, showMountDialog, commitPartitions,
  rollbackPartitions, saveConfig, startInstall, copyFullLog, toggleLog,
  backFromError, reboot,
];

// ── Init ──────────────────────────────────────────────────────────────────────
apiFetch('/api/config').then(r=>r.json()).then(cfg => {
  S._sourceImage = cfg.source_image;
  S.isLive = cfg.is_live !== false;
});
goto('welcome');
