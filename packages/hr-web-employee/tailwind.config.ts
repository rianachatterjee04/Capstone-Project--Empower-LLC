import type { Config } from "tailwindcss";

// Mirror of the employer design tokens so the two portals share a language.
export default {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        canvas: "#F7F6F2",
        surface: "#FFFFFF",
        sunken: "#F1EFE9",
        line: "rgba(15,15,18,0.07)",
        rule: "rgba(15,15,18,0.04)",
        ink: "#13141A",
        body: "#33343B",
        muted: "#6F7079",
        faint: "#9B9CA3",
        accent: { DEFAULT: "#1F1F25", fg: "#FFFFFF", soft: "#E9E8E2", softFg: "#1F1F25" },
        success: { bg: "#EAF1EA", fg: "#2F5D3A", line: "#CFE0D1" },
        warn:    { bg: "#F5EDD8", fg: "#7A5A1B", line: "#E5D4A1" },
        danger:  { bg: "#F4E3E1", fg: "#8B2B25", line: "#E5BFBB" },
        info:    { bg: "#E8EAEF", fg: "#34384B", line: "#CFD3DD" },
      },
      borderRadius: { xs: "6px", sm: "8px", md: "10px", lg: "14px", xl: "18px", "2xl": "22px" },
      boxShadow: {
        soft: "0 1px 2px rgba(15,15,18,0.04), 0 0 0 1px rgba(15,15,18,0.04)",
        lift: "0 6px 24px -10px rgba(15,15,18,0.16), 0 0 0 1px rgba(15,15,18,0.06)",
      },
      fontFamily: {
        sans: ["Arial", "Helvetica", "sans-serif"],
        display: ["Arial", "Helvetica", "sans-serif"],
        body: ["Arial", "Helvetica", "sans-serif"],
        serif: ["ui-serif", "Georgia", "serif"],
        mono: ["ui-monospace", "Menlo", "monospace"],
      },
      fontSize: {
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
      letterSpacing: { eyebrow: "0.08em" },
      transitionTimingFunction: { calm: "cubic-bezier(0.2, 0.7, 0.2, 1)" },
    },
  },
  plugins: [],
} satisfies Config;
