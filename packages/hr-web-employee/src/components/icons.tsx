/**
 * Tiny in-house icon set.
 *
 * Hand-tuned 1.5px strokes, currentColor, 18-22px viewBox. No icon library
 * dependency — keeps bundle small and visual language consistent.
 */
import React from "react";

type IconProps = { size?: number; className?: string };

const base = (size: number) => ({
  width: size,
  height: size,
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.6,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
});

export const IconHome = ({ size = 18, className }: IconProps) => (
  <svg {...base(size)} className={className} aria-hidden>
    <path d="M3.5 11 12 4l8.5 7" />
    <path d="M5 10.5V20h14V10.5" />
  </svg>
);

export const IconPeople = ({ size = 18, className }: IconProps) => (
  <svg {...base(size)} className={className} aria-hidden>
    <circle cx="9" cy="9" r="3.2" />
    <path d="M3.5 19c0-2.8 2.5-5 5.5-5s5.5 2.2 5.5 5" />
    <circle cx="17" cy="10" r="2.4" />
    <path d="M20.5 18.2c0-1.9-1.6-3.4-3.5-3.4" />
  </svg>
);

export const IconHiring = ({ size = 18, className }: IconProps) => (
  <svg {...base(size)} className={className} aria-hidden>
    <rect x="3.5" y="7" width="17" height="13" rx="2.2" />
    <path d="M9 7V5.5C9 4.7 9.7 4 10.5 4h3c.8 0 1.5.7 1.5 1.5V7" />
    <path d="M3.5 12h17" />
  </svg>
);

export const IconPerformance = ({ size = 18, className }: IconProps) => (
  <svg {...base(size)} className={className} aria-hidden>
    <path d="M4 19V5" />
    <path d="M4 19h16" />
    <path d="M7.5 15v-3" />
    <path d="M12 15V8" />
    <path d="M16.5 15v-5" />
  </svg>
);

export const IconCompliance = ({ size = 18, className }: IconProps) => (
  <svg {...base(size)} className={className} aria-hidden>
    <path d="M12 3l8 3v5c0 5-3.5 8.5-8 10-4.5-1.5-8-5-8-10V6l8-3z" />
    <path d="M9 12l2 2 4-4" />
  </svg>
);

export const IconAIOps = ({ size = 18, className }: IconProps) => (
  <svg {...base(size)} className={className} aria-hidden>
    <path d="M12 3v3" />
    <path d="M12 18v3" />
    <path d="M3 12h3" />
    <path d="M18 12h3" />
    <circle cx="12" cy="12" r="4" />
  </svg>
);

export const IconAnalytics = ({ size = 18, className }: IconProps) => (
  <svg {...base(size)} className={className} aria-hidden>
    <path d="M5 19V9" />
    <path d="M12 19V5" />
    <path d="M19 19v-7" />
  </svg>
);

export const IconPayroll = ({ size = 18, className }: IconProps) => (
  <svg {...base(size)} className={className} aria-hidden>
    <rect x="3" y="6" width="18" height="12" rx="2" />
    <circle cx="12" cy="12" r="2.4" />
    <path d="M7 12h.01M17 12h.01" />
  </svg>
);

export const IconBenefits = ({ size = 18, className }: IconProps) => (
  <svg {...base(size)} className={className} aria-hidden>
    <path d="M12 21s-7-4.5-7-10a4 4 0 017-2.6A4 4 0 0119 11c0 5.5-7 10-7 10z" />
  </svg>
);

// Utility icons used by the shell
export const IconSearch = ({ size = 16, className }: IconProps) => (
  <svg {...base(size)} className={className} aria-hidden>
    <circle cx="11" cy="11" r="6" />
    <path d="m20 20-3.5-3.5" />
  </svg>
);

export const IconSparkle = ({ size = 16, className }: IconProps) => (
  <svg {...base(size)} className={className} aria-hidden>
    <path d="M12 4v3M12 17v3M4 12h3M17 12h3" />
    <path d="M7 7l1.5 1.5M15.5 15.5L17 17M7 17l1.5-1.5M15.5 8.5L17 7" />
  </svg>
);

export const IconInbox = ({ size = 16, className }: IconProps) => (
  <svg {...base(size)} className={className} aria-hidden>
    <path d="M4 13l2.5-7h11L20 13" />
    <path d="M4 13h5l1 2h4l1-2h5v6H4z" />
  </svg>
);

export const IconChevronRight = ({ size = 14, className }: IconProps) => (
  <svg {...base(size)} className={className} aria-hidden>
    <path d="m9 6 6 6-6 6" />
  </svg>
);

export const IconArrowUpRight = ({ size = 14, className }: IconProps) => (
  <svg {...base(size)} className={className} aria-hidden>
    <path d="M7 17 17 7" />
    <path d="M9 7h8v8" />
  </svg>
);

export const IconClose = ({ size = 16, className }: IconProps) => (
  <svg {...base(size)} className={className} aria-hidden>
    <path d="m6 6 12 12M18 6 6 18" />
  </svg>
);

export const IconCircle = ({ size = 8, className }: IconProps) => (
  <svg {...base(size)} className={className} aria-hidden>
    <circle cx="12" cy="12" r="6" />
  </svg>
);

export const IconCheck = ({ size = 14, className }: IconProps) => (
  <svg {...base(size)} className={className} aria-hidden>
    <path d="m5 12 4 4 10-10" />
  </svg>
);

export const IconLogout = ({ size = 16, className }: IconProps) => (
  <svg {...base(size)} className={className} aria-hidden>
    <path d="M9 4H5a1 1 0 0 0-1 1v14a1 1 0 0 0 1 1h4" />
    <path d="M14 17 19 12 14 7" />
    <path d="M19 12H9" />
  </svg>
);
