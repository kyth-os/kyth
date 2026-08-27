// Placeholder data shaped like what the real backend will return once this
// is wired up (see PerformancePage._on_sessions_loaded and GuardianPage in
// the current Qt Hub for the real data these mirror). Nothing here is
// fabricated as "real" — this is a prototype fixture, swapped for a fetch
// to /api/dashboard once the Python side exists.

export interface StatTile {
  label: string;
  value: string;
  delta?: string;
  deltaTone?: "ok" | "warn" | "error";
}

export const statTiles: StatTile[] = [
  { label: "Guardian", value: "Healthy", delta: "0 issues", deltaTone: "ok" },
  { label: "Update Channel", value: "Testing", delta: "up to date", deltaTone: "ok" },
  { label: "Storage Free", value: "412 GB", delta: "-8 GB this week", deltaTone: "warn" },
  { label: "GPU", value: "RX 7900 XTX", delta: "Mesa-git", deltaTone: "ok" },
];

export const performanceSeries = [
  { day: "Mon", fps: 118 },
  { day: "Tue", fps: 132 },
  { day: "Wed", fps: 121 },
  { day: "Thu", fps: 144 },
  { day: "Fri", fps: 139 },
  { day: "Sat", fps: 156 },
  { day: "Sun", fps: 149 },
];

export const sessionSeries = [
  { day: "Mon", sessions: 2 },
  { day: "Tue", sessions: 1 },
  { day: "Wed", sessions: 3 },
  { day: "Thu", sessions: 2 },
  { day: "Fri", sessions: 4 },
  { day: "Sat", sessions: 5 },
  { day: "Sun", sessions: 3 },
];

export interface GuardianEvent {
  title: string;
  detail: string;
  status: "ok" | "warn" | "error";
  when: string;
}

export const guardianHistory: GuardianEvent[] = [
  { title: "Flatpak permissions repaired", detail: "org.mozilla.firefox", status: "ok", when: "2h ago" },
  { title: "Bluetooth audio reconnect", detail: "LDAC codec fallback", status: "warn", when: "1d ago" },
  { title: "Rollback available", detail: "Previous deployment kept", status: "ok", when: "3d ago" },
  { title: "NTFS Steam library detected", detail: "Move suggested", status: "warn", when: "4d ago" },
];
