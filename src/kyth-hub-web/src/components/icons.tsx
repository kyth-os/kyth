// Small inline line-icon set — no icon package dependency for a five-item
// nav. Swap for @tabler/icons-react or similar if the icon count grows.
import type { SVGProps } from "react";

const base = (props: SVGProps<SVGSVGElement>) => ({
  width: 18,
  height: 18,
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.8,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
  ...props,
});

export const IconHome = (p: SVGProps<SVGSVGElement>) => (
  <svg {...base(p)}>
    <path d="M3 11.5 12 4l9 7.5" />
    <path d="M5 10v9a1 1 0 0 0 1 1h4v-6h4v6h4a1 1 0 0 0 1-1v-9" />
  </svg>
);

export const IconPlay = (p: SVGProps<SVGSVGElement>) => (
  <svg {...base(p)}>
    <path d="M7 4.5v15l13-7.5-13-7.5Z" />
  </svg>
);

export const IconGrid = (p: SVGProps<SVGSVGElement>) => (
  <svg {...base(p)}>
    <rect x="3.5" y="3.5" width="7" height="7" rx="1.5" />
    <rect x="13.5" y="3.5" width="7" height="7" rx="1.5" />
    <rect x="3.5" y="13.5" width="7" height="7" rx="1.5" />
    <rect x="13.5" y="13.5" width="7" height="7" rx="1.5" />
  </svg>
);

export const IconMonitor = (p: SVGProps<SVGSVGElement>) => (
  <svg {...base(p)}>
    <rect x="3" y="4" width="18" height="12" rx="1.5" />
    <path d="M9 20h6M12 16v4" />
  </svg>
);

export const IconTransfer = (p: SVGProps<SVGSVGElement>) => (
  <svg {...base(p)}>
    <path d="M4 8h13M17 8l-3-3M17 8l-3 3" />
    <path d="M20 16H7M7 16l3 3M7 16l3-3" />
  </svg>
);

export const IconSearch = (p: SVGProps<SVGSVGElement>) => (
  <svg {...base(p)}>
    <circle cx="11" cy="11" r="6.5" />
    <path d="m20 20-3.5-3.5" />
  </svg>
);

export const IconBell = (p: SVGProps<SVGSVGElement>) => (
  <svg {...base(p)}>
    <path d="M6 9a6 6 0 0 1 12 0c0 5 2 6 2 6H4s2-1 2-6Z" />
    <path d="M10 20a2 2 0 0 0 4 0" />
  </svg>
);

export const IconShield = (p: SVGProps<SVGSVGElement>) => (
  <svg {...base(p)}>
    <path d="M12 3.5 5 6v6c0 4.5 3 7.5 7 8.5 4-1 7-4 7-8.5V6l-7-2.5Z" />
    <path d="m9 12 2 2 4-4" />
  </svg>
);

export const IconRefresh = (p: SVGProps<SVGSVGElement>) => (
  <svg {...base(p)}>
    <path d="M4 12a8 8 0 0 1 14-5.3M20 12a8 8 0 0 1-14 5.3" />
    <path d="M18 3v4h-4M6 21v-4h4" />
  </svg>
);

export const IconDatabase = (p: SVGProps<SVGSVGElement>) => (
  <svg {...base(p)}>
    <ellipse cx="12" cy="5.5" rx="7.5" ry="3" />
    <path d="M4.5 5.5V12c0 1.66 3.36 3 7.5 3s7.5-1.34 7.5-3V5.5" />
    <path d="M4.5 12v6.5c0 1.66 3.36 3 7.5 3s7.5-1.34 7.5-3V12" />
  </svg>
);

export const IconChip = (p: SVGProps<SVGSVGElement>) => (
  <svg {...base(p)}>
    <rect x="7" y="7" width="10" height="10" rx="1.5" />
    <path d="M9 3.5v3M15 3.5v3M9 17.5v3M15 17.5v3M3.5 9h3M3.5 15h3M17.5 9h3M17.5 15h3" />
  </svg>
);

export const IconGamepad = (p: SVGProps<SVGSVGElement>) => (
  <svg {...base(p)}>
    <path d="M6.5 8.5h11a4 4 0 0 1 4 4.4l-.6 4.3a2.3 2.3 0 0 1-4.1 1.1L15 16.5H9l-1.8 1.8a2.3 2.3 0 0 1-4.1-1.1l-.6-4.3a4 4 0 0 1 4-4.4Z" />
    <path d="M8 11v3M6.5 12.5h3" />
    <circle cx="16" cy="11.5" r="0.9" fill="currentColor" stroke="none" />
    <circle cx="18" cy="13.5" r="0.9" fill="currentColor" stroke="none" />
  </svg>
);

export const IconCloud = (p: SVGProps<SVGSVGElement>) => (
  <svg {...base(p)}>
    <path d="M7 18h10a3.5 3.5 0 0 0 .5-6.96 5 5 0 0 0-9.62-1.8A4 4 0 0 0 7 18Z" />
  </svg>
);

export const IconLock = (p: SVGProps<SVGSVGElement>) => (
  <svg {...base(p)}>
    <rect x="5.5" y="10.5" width="13" height="9" rx="1.8" />
    <path d="M8.5 10.5V7.5a3.5 3.5 0 0 1 7 0v3" />
  </svg>
);

export const IconWrench = (p: SVGProps<SVGSVGElement>) => (
  <svg {...base(p)}>
    <path d="M14.5 6.5a3.8 3.8 0 0 0-5 4.2L4.5 15.7a1.7 1.7 0 0 0 2.4 2.4l5-5a3.8 3.8 0 0 0 4.2-5l-2.3 2.3-2-2 2.7-1.9Z" />
  </svg>
);
