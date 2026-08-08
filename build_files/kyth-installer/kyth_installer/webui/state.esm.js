/* Kyth Installer state — typed ES-module store (Phase 6).

   Original `state.js` exposed `globalThis.KythInstallerState` as a mutable
   singleton. This module keeps that global for backwards compatibility
   (existing pages import via side-effect) while also exporting a typed
   factory and helpers for future `app.js` migration.

   No behavior change: shape and defaults are identical to the global.
*/

export const DEFAULT_STATE = Object.freeze({
  disk: null,
  install_mode: 'wipe',
  target_partition: null,
  resize_partition: null,
  resize_gib: 64,
  free_region_start: 0,
  free_region_end: 0,
  hostname: 'kyth',
  timezone: 'UTC',
  locale: 'en_US.UTF-8',
  keymap: 'us',
  username: '',
  password: '',
  kernel: 'fedora',
  isLive: true,
  disks: [],
  partitions: [],
  freeRegions: [],
  minGuidedGiB: 32,
  replaceAllowed: true,
  pendingOps: [],
  supportedFilesystems: [],
  manualCommitted: false,
  startTime: 0,
  elapsedTimer: null,
  source: null,
});

/** Create a fresh mutable installer state (shallow copy of defaults). */
export function createState(overrides = {}) {
  return { ...DEFAULT_STATE, ...overrides };
}

/** Reset a state object in-place to defaults. */
export function resetState(state, overrides = {}) {
  Object.keys(state).forEach((k) => delete state[k]);
  Object.assign(state, createState(overrides));
  return state;
}

/* Keep legacy global for code that loads state.js via <script> without import */
if (typeof globalThis !== 'undefined' && !globalThis.KythInstallerState) {
  globalThis.KythInstallerState = createState();
} else if (typeof globalThis !== 'undefined') {
  // Ensure any missing keys from an older global are backfilled
  for (const [k, v] of Object.entries(DEFAULT_STATE)) {
    if (!(k in globalThis.KythInstallerState)) {
      globalThis.KythInstallerState[k] = Array.isArray(v) ? [...v] : v;
    }
  }
}
