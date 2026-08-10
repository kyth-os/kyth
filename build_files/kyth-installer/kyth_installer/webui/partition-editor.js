/* global document, S, el, apiFetch, postJSON, fmtBytes, loadPartitions, renderDiskLayouts */
// Manual partitioning: the toolbar + dialogs for the disk step's "Manual
// Partitioning" mode, plus the shared overlay-modal machinery every dialog
// here (and a couple of other steps) builds on.

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
      S.manualCommitted ? null : el('button', {
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

function removePendingOp(index) {
  postJSON('/api/disk/pending/remove', { disk: S.disk.name, index }).then(j => {
    if (j.ok) {
      loadPendingOps();
      loadPartitions();
      renderDiskLayouts();
    } else {
      showOverlay('Error', el('div', { class: 'validation-errors', text: j.message || 'Could not remove operation' }), null);
    }
  });
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
          // Leave 1 MiB for alignment plus 1 MiB for the automatic GPT
          // BIOS-boot partition created by the backend.
          const reserve = 2 * 1024 * 1024;
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
    const start = parseInt(document.getElementById('dlg-start').value, 10);
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

function _updateResizeSliderBounds() {
  const parts = S.partitions || [];
  const partName = document.getElementById('dlg-resize-part').value;
  const part = parts.find(p => p.name === partName);
  if (!part) return;
  const currentGiB = Math.floor(part.size_bytes / 1024**3);
  const maxNewGiB = Math.max(1, currentGiB - 1);
  const slider = document.getElementById('dlg-resize-slider');
  slider.max = maxNewGiB;
  slider.min = 1;
  const defaultVal = Math.min(maxNewGiB, Math.max(1, Math.floor(currentGiB / 2)));
  slider.value = defaultVal;
  _onResizeSliderMove(defaultVal, currentGiB);
}

// Called from index.html-equivalent inline oninput handler built via el() below.
function _onResizeSliderMove(newGiB, currentGiB) {
  document.getElementById('dlg-resize-new-label').textContent = `New size: ${newGiB} GiB`;
  document.getElementById('dlg-resize-freed-label').textContent = `Freed: ${currentGiB - newGiB} GiB`;
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
    el('select', {
      id: 'dlg-resize-part',
      onchange: _updateResizeSliderBounds,
    }, ...selectable.map(p => el('option', { value: p.name, text: `${p.name} (${p.size})` }))),
    el('div', { class: 'field-label', text: 'New Size' }),
    el('div', { class: 'slider-labels' },
      el('span', { id: 'dlg-resize-new-label', text: 'New size: -- GiB' }),
      el('span', { id: 'dlg-resize-freed-label', text: 'Freed: -- GiB' })),
    el('input', {
      type: 'range', id: 'dlg-resize-slider', class: 'slider-input', min: 1, max: 100, value: 32,
      oninput: (e) => {
        const partName = document.getElementById('dlg-resize-part').value;
        const p = parts.find(pt => pt.name === partName);
        _onResizeSliderMove(parseInt(e.target.value, 10), Math.floor((p ? p.size_bytes : 0) / 1024**3));
      },
    }),
    el('div', { class: 'slider-subtext', text: 'Drag the slider to choose the partition’s new (shrunk) size.' }),
    el('div', { style: 'color:var(--amber);font-size:12px;margin-top:8px;',
      text: '⚠ Only shrinking is supported. The partition will be shrunk from its end.' }),
  );
  showOverlay('Resize Partition', content, () => {
    const part = document.getElementById('dlg-resize-part').value;
    const newSizeGiB = parseInt(document.getElementById('dlg-resize-slider').value, 10);
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
  _updateResizeSliderBounds();
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

// These handlers are referenced by inline event attributes in index.html.
void [
  showNewTableDialog, showCreateDialog, showDeleteDialog,
  showResizeDialog, showFormatDialog, showMountDialog, commitPartitions,
  rollbackPartitions,
];
