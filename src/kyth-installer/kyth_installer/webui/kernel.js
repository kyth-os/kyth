/* global document, S, el, svgIcon */
/* exported initKernel */
// Kernel step: KythOS Standard vs. KythOS Performance (CachyOS) picker.

const KERNELS = [
  { id: 'fedora', icon: 'kernel-standard', name: 'KythOS Standard',
    desc: 'Standard KythOS kernel · Works with Secure Boot out of the box',
    badge: 'Default' },
  { id: 'cachy',  icon: 'kernel-performance', name: 'KythOS Performance',
    desc: 'BORE scheduler · sched-ext · BBRv3 · NTSYNC · Optimized for gaming & low-latency workloads',
    note: 'Requires network during installation; Secure Boot enrollment is staged for first boot' },
];

// eslint-disable-next-line no-unused-vars -- called from nav.js's step router
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
      el('div', { class: 'kernel-icon' }, svgIcon(k.icon)),
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
