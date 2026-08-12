/* global document, setTimeout, S, el, apiFetch, fmtBytes, svgIcon, showManualControls */
/* exported loadDisks */
// Disk step: disk picker, install-mode cards, and the visual current/proposed
// disk-layout bars. Manual partitioning's toolbar+dialogs live in their own
// file (partition-editor.js) — this one covers the disk step's other four
// modes (wipe / keep-windows / alongside / free-space) plus the shared
// layout-bar rendering both manual and non-manual modes draw from.

// eslint-disable-next-line no-unused-vars -- called from nav.js, install-flow.js, index.html
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
        el('div', { class: 'disk-icon' }, svgIcon(d.rota ? 'disk-hdd' : 'disk-ssd')),
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
    const defaultNtfs = S.partitions.find(p => p.ntfs_resize_candidate && p.size_bytes >= (64 + S.minGuidedGiB) * 1024**3);
    if (defaultNtfs) selectResizePartitionByName(defaultNtfs.name);
  } else if (id === 'alongside') {
    const defaultReplace = S.partitions.find(p => p.alongside_candidate);
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
    const hasNtfsCandidate = parts.some(p => p.ntfs_resize_candidate && p.size_bytes >= (64 + S.minGuidedGiB) * 1024**3);
    const hasFreeCandidate = regions.some(r => r.size_bytes >= S.minGuidedGiB * 1024**3);
    const hasReplaceCandidate = S.replaceAllowed && parts.some(p => p.alongside_candidate);

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
    // One-click Windows suggestion banner
    if (hasNtfsCandidate) {
      const best = parts.filter(p=>p.ntfs_resize_candidate).sort((a,b)=>b.size_bytes-a.size_bytes)[0];
      const banner = document.getElementById('windows-suggest-banner') || (function(){
        const b=document.createElement('div'); b.id='windows-suggest-banner'; b.className='status-box status-ok';
        b.style.margin='14px 0';
        document.getElementById('partition-section').prepend(b); return b;
      })();
      banner.textContent = `🪟 Windows found on ${best.name} (${fmtBytes(best.size_bytes)}). Keep Windows will shrink it by ~32 GiB — files preserved, validated before write.`;
      banner.style.display='block';
    }
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
    if (S.install_mode === 'alongside' && S.replaceAllowed && block.type === 'part' && block.ref.alongside_candidate) {
      klass += ' clickable';
      if (S.target_partition === block.name) klass += ' selected-target';
      onclick = () => selectPartitionByName(block.name);
    } else if (S.install_mode === 'resize_ntfs' && block.type === 'part' && block.ref.ntfs_resize_candidate && block.size_bytes >= (64 + S.minGuidedGiB) * 1024**3) {
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
    cards.forEach(c => { c.classList.toggle('selected', parseInt(c.dataset.start, 10) === start); });
  }
  renderDiskLayouts();
  updateDiskNext();
}

function populateReplacementList() {
  const container = document.getElementById('replace-list');
  const replaceable = S.replaceAllowed
    ? S.partitions.filter(p => p.alongside_candidate)
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

// Called from index.html's inline oninput handler on the shrink slider, not
// referenced within this file.
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

void [onSliderMove];
