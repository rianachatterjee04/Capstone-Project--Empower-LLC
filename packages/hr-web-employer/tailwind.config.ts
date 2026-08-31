import type { Config } from "tailwindcss";

// Foundry People design tokens
// Calm enterprise minimalism — warm-neutral palette, restrained accent,
// generous spacing, premium typography. Avoid gradients-as-theme.
export default {
  darkMode: "class",
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // AuditWise light palette. CSS variables defined in globals.css;
        // fallbacks below mirror the AuditWise tokens.
        canvas: "var(--fp-canvas, #F8FAFC)",        // page background
        surface: "var(--fp-surface, #FFFFFF)",      // card surface
        sunken: "var(--fp-sunken, #F1F5F9)",        // muted / inset / hover row
        line: "var(--fp-line, #E2E8F0)",            // borders
        rule: "var(--fp-rule, #EEF2F6)",            // faint hairline
        lineStrong: "#CBD5E1",                       // strong border

        // Foreground scale (slate)
        ink: "var(--fp-ink, #0F172A)",            // primary text
        body: "var(--fp-body, #475569)",          // secondary text
        muted: "var(--fp-muted, #64748B)",        // muted text
        faint: "var(--fp-faint, #94A3B8)",        // helper

        // Brand accent — teal; secondary accent — sky
        accent: {
          DEFAULT: "var(--fp-accent, #0F766E)",
          fg: "var(--fp-accent-fg, #FFFFFF)",
          hover: "#115E59",
          soft: "var(--fp-accent-soft, #CCFBF1)",
          softFg: "var(--fp-accent-soft-fg, #115E59)",
          sky: "#0EA5E9",
        },

        // Semantic — AuditWise status colors
        success: { DEFAULT: "#16A34A", bg: "#DCFCE7", fg: "#166534", line: "#BBF7D0" },
        warn:    { DEFAULT: "#D97706", bg: "#FEF3C7", fg: "#92400E", line: "#FDE68A" },
        danger:  { DEFAULT: "#DC2626", bg: "#FEE2E2", fg: "#991B1B", line: "#FECACA" },
        info:    { DEFAULT: "#0EA5E9", bg: "#E0F2FE", fg: "#075985", line: "#BAE6FD" },
      },
      borderRadius: {
        xs: "6px",
        sm: "8px",
        md: "10px",
        lg: "14px",
        xl: "18px",
        "2xl": "22px",
      },
      boxShadow: {
        // single-layer subtle elevation (slate-tinted)
        soft: "0 1px 2px rgba(15,23,42,0.04), 0 0 0 1px rgba(15,23,42,0.05)",
        lift: "0 6px 24px -10px rgba(15,23,42,0.16), 0 0 0 1px rgba(15,23,42,0.06)",
        rim:  "inset 0 0 0 1px rgba(15,23,42,0.06)",
      },
      fontFamily: {
        sans: ["Arial", "Helvetica", "sans-serif"],
        serif: ["Arial", "Helvetica", "sans-serif"],
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
      fontSize: {
        // tighter, more deliberate scale
        "2xs": ["10.5px", { lineHeight: "14px", letterSpacing: "0.04em" }],
        xs: ["12px", { lineHeight: "16px" }],
        sm: ["13px", { lineHeight: "18px" }],
        base: ["14.5px", { lineHeight: "21px" }],
        md: ["15.5px", { lineHeight: "23px" }],
        lg: ["18px", { lineHeight: "26px" }],
        xl: ["22px", { lineHeight: "30px", letterSpacing: "-0.005em" }],
        "2xl": ["28px", { lineHeight: "34px", letterSpacing: "-0.01em" }],
        "3xl": ["36px", { lineHeight: "42px", letterSpacing: "-0.015em" }],
      },
      letterSpacing: {
        eyebrow: "0.08em",
      },
      transitionTimingFunction: {
        calm: "cubic-bezier(0.2, 0.7, 0.2, 1)",
      },
      transitionDuration: {
        150: "150ms",
        200: "200ms",
      },
      spacing: {
        "18": "4.5rem",
      },
    },
  },
  plugins: [],
} satisfies Config;
