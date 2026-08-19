/* global document */
/* Small inline icon set for installer wizard cards.
   Built from plain SVG primitives (not emoji glyphs) so the mode/kernel/disk
   badges don't depend on whatever emoji font happens to be installed in the
   live-ISO Chromium kiosk, and so selected/hover states can recolor the icon
   via currentColor the same way the rest of the card already recolors on
   selection — an emoji glyph can't pick up either. */

const ICON_SHAPES = {
  'mode-wipe': [
    { tag: 'circle', attrs: { cx: 12, cy: 12, r: 8 } },
    { tag: 'line', attrs: { x1: 7, y1: 7, x2: 17, y2: 17 } },
    { tag: 'line', attrs: { x1: 17, y1: 7, x2: 7, y2: 17 } },
  ],
  'mode-windows': [
    { tag: 'rect', attrs: { x: 3, y: 5, width: 7, height: 14, rx: 1.5 } },
    { tag: 'rect', attrs: { x: 14, y: 5, width: 7, height: 14, rx: 1.5 } },
  ],
  'mode-alongside': [
    { tag: 'rect', attrs: { x: 3, y: 5, width: 18, height: 14, rx: 1.5 } },
    { tag: 'rect', attrs: { x: 13, y: 5, width: 8, height: 14, rx: 1.5, fill: 'currentColor', 'fill-opacity': '0.22', stroke: 'none' } },
  ],
  'mode-free-space': [
    { tag: 'rect', attrs: { x: 3, y: 5, width: 18, height: 14, rx: 1.5, 'stroke-dasharray': '3 3' } },
    { tag: 'line', attrs: { x1: 12, y1: 9, x2: 12, y2: 15 } },
    { tag: 'line', attrs: { x1: 9, y1: 12, x2: 15, y2: 12 } },
  ],
  'mode-manual': [
    { tag: 'line', attrs: { x1: 5, y1: 7, x2: 19, y2: 7 } },
    { tag: 'circle', attrs: { cx: 9, cy: 7, r: 1.8, fill: 'currentColor' } },
    { tag: 'line', attrs: { x1: 5, y1: 12, x2: 19, y2: 12 } },
    { tag: 'circle', attrs: { cx: 15, cy: 12, r: 1.8, fill: 'currentColor' } },
    { tag: 'line', attrs: { x1: 5, y1: 17, x2: 19, y2: 17 } },
    { tag: 'circle', attrs: { cx: 11, cy: 17, r: 1.8, fill: 'currentColor' } },
  ],
  'kernel-standard': [
    { tag: 'circle', attrs: { cx: 12, cy: 12, r: 8.5 } },
    { tag: 'polyline', attrs: { points: '8.2 12 10.8 14.6 15.8 9.2' } },
  ],
  'kernel-performance': [
    { tag: 'polygon', attrs: { points: '13 2 3 14 12 14 11 22 21 10 12 10 13 2' } },
  ],
  'disk-hdd': [
    { tag: 'rect', attrs: { x: 3, y: 8, width: 18, height: 8, rx: 1.5 } },
    { tag: 'circle', attrs: { cx: 8, cy: 12, r: 1.6, fill: 'currentColor' } },
    { tag: 'line', attrs: { x1: 12, y1: 12, x2: 18, y2: 12 } },
  ],
  'disk-ssd': [
    { tag: 'rect', attrs: { x: 4, y: 6, width: 16, height: 12, rx: 1.5 } },
    { tag: 'line', attrs: { x1: 8, y1: 10, x2: 8, y2: 14 } },
    { tag: 'line', attrs: { x1: 12, y1: 10, x2: 12, y2: 14 } },
    { tag: 'line', attrs: { x1: 16, y1: 10, x2: 16, y2: 14 } },
  ],
};

const SVG_NS = 'http://www.w3.org/2000/svg';

function svgIcon(name) {
  const svg = document.createElementNS(SVG_NS, 'svg');
  svg.setAttribute('viewBox', '0 0 24 24');
  svg.setAttribute('width', '22');
  svg.setAttribute('height', '22');
  svg.setAttribute('fill', 'none');
  svg.setAttribute('stroke', 'currentColor');
  svg.setAttribute('stroke-width', '1.6');
  svg.setAttribute('stroke-linecap', 'round');
  svg.setAttribute('stroke-linejoin', 'round');
  svg.setAttribute('aria-hidden', 'true');
  for (const { tag, attrs } of ICON_SHAPES[name] || []) {
    const node = document.createElementNS(SVG_NS, tag);
    for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, String(v));
    svg.appendChild(node);
  }
  return svg;
}

// Swap the 5 static mode-card glyphs (index.html) for SVG icons. Runs once
// at script load — this file loads after the DOM it targets (script tags
// sit at the end of body), so the elements already exist.
function mountStaticIcons() {
  const slots = {
    'micon-wipe': 'mode-wipe',
    'micon-resize_ntfs': 'mode-windows',
    'micon-alongside': 'mode-alongside',
    'micon-free_space': 'mode-free-space',
    'micon-manual': 'mode-manual',
  };
  for (const [id, icon] of Object.entries(slots)) {
    const el = document.getElementById(id);
    if (el) el.appendChild(svgIcon(icon));
  }
}
mountStaticIcons();

// Used from disk.js and kernel.js when building cards dynamically.
void [svgIcon];
