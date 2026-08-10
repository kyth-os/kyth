/* global document, S, el */
// Review step: summary table + the backup/erase/current-disk confirmations
// that gate the Install Now button.

function buildReview() {
  const kernelLabels = { fedora: 'KythOS Standard', cachy: 'KythOS Performance' };
  const modeLabels   = { wipe: 'Erase Full Disk', alongside: 'Install Alongside', resize_ntfs: 'Shrink NTFS & Install', free_space: 'Use Free Space', manual: 'Manual Partitioning' };
  const targetImage = (() => {
    if (S.kernel === 'fedora' && S.source && S.source.target_ref) return S.source.target_ref;
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
    ['Locale', S.locale],
    ['Keyboard', S.keymap],
    ['Username', S.username],
    ['Password', '••••••••'],
    ['Kernel',   kernelLabels[S.kernel] || S.kernel],
    ['Source',   S.kernel === 'fedora' && S.source && S.source.kind === 'embedded' ? 'Verified offline image' : 'Network registry'],
    ...(S.kernel === 'fedora' && S.source && S.source.digest ? [['Image Digest', S.source.digest]] : []),
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
