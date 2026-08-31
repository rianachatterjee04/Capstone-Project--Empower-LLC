"use client";
/**
 * Foundry People design system primitives.
 *
 * Single import surface for the calm enterprise layout. Each primitive does
 * one thing, takes a className override, and never injects color decisions
 * the parent didn't ask for.
 */
import React from "react";
import clsx from "clsx";
import Link from "next/link";

// ---------------------------------------------------------------------------
// Surface — the canonical card/panel
// ---------------------------------------------------------------------------
type SurfaceProps = React.HTMLAttributes<HTMLDivElement> & {
  as?: "div" | "section" | "article" | "aside";
  inset?: boolean;        // bg-canvas instead of bg-surface
  hairline?: boolean;     // border or no
  pad?: "none" | "sm" | "md" | "lg";
  radius?: "md" | "lg" | "xl" | "2xl";
};
export function Surface({
  as: Tag = "div",
  inset = false,
  hairline = true,
  pad = "md",
  radius = "lg",
  className,
  ...props
}: SurfaceProps) {
  const padCls = pad === "none" ? "" : pad === "sm" ? "p-4" : pad === "lg" ? "p-7" : "p-5";
  const radiusCls = `rounded-${radius}`;
  return (
    <Tag
      className={clsx(
        inset ? "bg-canvas" : "bg-surface",
        hairline && "border border-line",
        padCls,
        radiusCls,
        className,
      )}
      {...props}
    />
  );
}

// ---------------------------------------------------------------------------
// Stack — vertical / horizontal gap utility
// ---------------------------------------------------------------------------
type StackProps = React.HTMLAttributes<HTMLDivElement> & {
  gap?: 1 | 2 | 3 | 4 | 5 | 6 | 8 | 10 | 12;
  row?: boolean;
  align?: "start" | "center" | "end" | "stretch";
  justify?: "start" | "center" | "end" | "between";
  wrap?: boolean;
};
export function Stack({
  gap = 4,
  row = false,
  align = "stretch",
  justify = "start",
  wrap = false,
  className,
  ...props
}: StackProps) {
  return (
    <div
      className={clsx(
        row ? "flex" : "flex flex-col",
        row && "flex-row",
        `gap-${gap}`,
        `items-${align}`,
        `justify-${justify}`,
        wrap && "flex-wrap",
        className,
      )}
      {...props}
    />
  );
}

// ---------------------------------------------------------------------------
// PageHeader — eyebrow + title + subtitle + slot for actions
// ---------------------------------------------------------------------------
type PageHeaderProps = {
  eyebrow?: string;
  title: React.ReactNode;
  subtitle?: React.ReactNode;
  actions?: React.ReactNode;
  className?: string;
};
export function PageHeader({ eyebrow, title, subtitle, actions, className }: PageHeaderProps) {
  return (
    <header className={clsx("flex flex-wrap items-end justify-between gap-4", className)}>
      <div>
        {eyebrow && <div className="fp-eyebrow mb-1">{eyebrow}</div>}
        <h1 className="text-2xl font-semibold tracking-tight text-ink">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-muted max-w-2xl">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </header>
  );
}

// ---------------------------------------------------------------------------
// SectionTitle — for section-level headers within a page
// ---------------------------------------------------------------------------
type SectionTitleProps = {
  eyebrow?: string;
  title: React.ReactNode;
  description?: React.ReactNode;
  trailing?: React.ReactNode;
};
export function SectionTitle({ eyebrow, title, description, trailing }: SectionTitleProps) {
  return (
    <div className="flex items-end justify-between gap-3">
      <div>
        {eyebrow && <div className="fp-eyebrow mb-1">{eyebrow}</div>}
        <div className="text-md font-semibold text-ink">{title}</div>
        {description && <div className="text-xs text-muted mt-0.5">{description}</div>}
      </div>
      {trailing && <div className="flex items-center gap-2 text-xs">{trailing}</div>}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Pill / StatusPill / Tag
// ---------------------------------------------------------------------------
type Tone = "neutral" | "success" | "warn" | "danger" | "info" | "accent";
const PILL_CLASSES: Record<Tone, string> = {
  neutral: "bg-sunken text-body border-line",
  success: "bg-success-bg text-success-fg border-success-line",
  warn:    "bg-warn-bg text-warn-fg border-warn-line",
  danger:  "bg-danger-bg text-danger-fg border-danger-line",
  info:    "bg-info-bg text-info-fg border-info-line",
  accent:  "bg-accent-soft text-accent-softFg border-line",
};
export function Pill({
  children,
  tone = "neutral",
  className,
}: {
  children: React.ReactNode;
  tone?: Tone;
  className?: string;
}) {
  return (
    <span
      className={clsx(
        "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-medium",
        PILL_CLASSES[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}

export function StatusPill({
  value,
  tone,
}: {
  value: string;
  tone?: Tone;
}) {
  const auto: Tone =
    tone ??
    (["high", "urgent", "alert", "critical", "rejected", "blocked"].includes(value.toLowerCase())
      ? "danger"
      : ["medium", "watch", "pending", "warn"].includes(value.toLowerCase())
      ? "warn"
      : ["ok", "low", "approved", "hired", "active", "ready"].includes(value.toLowerCase())
      ? "success"
      : "neutral");
  return <Pill tone={auto}>{value}</Pill>;
}

// ---------------------------------------------------------------------------
// MetricStat — replaces giant KPI cards. One line, two lines max.
// ---------------------------------------------------------------------------
export function MetricStat({
  label,
  value,
  hint,
  tone = "neutral",
  href,
}: {
  label: string;
  value: React.ReactNode;
  hint?: string;
  tone?: Tone;
  href?: string;
}) {
  const toneRing: Record<Tone, string> = {
    neutral: "",
    success: "ring-1 ring-success-line",
    warn: "ring-1 ring-warn-line",
    danger: "ring-1 ring-danger-line",
    info: "ring-1 ring-info-line",
    accent: "ring-1 ring-line",
  };
  const inner = (
    <div className={clsx("bg-surface border border-line rounded-lg p-4", toneRing[tone])}>
      <div className="fp-eyebrow">{label}</div>
      <div className="mt-1 text-2xl font-semibold tracking-tight text-ink">{value}</div>
      {hint && <div className="mt-0.5 text-xs text-muted">{hint}</div>}
    </div>
  );
  return href ? <Link href={href} className="block hover:opacity-90 transition-opacity duration-150 ease-calm">{inner}</Link> : inner;
}

// ---------------------------------------------------------------------------
// KeyValue — definition row
// ---------------------------------------------------------------------------
export function KeyValue({ label, value, mono = false }: { label: string; value: React.ReactNode; mono?: boolean }) {
  return (
    <div className="flex items-baseline gap-3 py-1.5 border-b border-rule last:border-0">
      <div className="w-32 shrink-0 text-xs text-muted">{label}</div>
      <div className={clsx("text-sm text-ink", mono && "font-mono")}>{value}</div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Toolbar — slim row, used above tables/lists
// ---------------------------------------------------------------------------
export function Toolbar({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <div className={clsx("flex flex-wrap items-center gap-2", className)}>
      {children}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Divider
// ---------------------------------------------------------------------------
export function Divider({ className }: { className?: string }) {
  return <div className={clsx("h-px w-full bg-line", className)} />;
}

// ---------------------------------------------------------------------------
// EmptyState
// ---------------------------------------------------------------------------
export function EmptyState({
  title,
  description,
  action,
}: {
  title: string;
  description?: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 py-10 px-6 text-center">
      <div className="text-sm font-semibold text-ink">{title}</div>
      {description && <div className="text-xs text-muted max-w-sm">{description}</div>}
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}

// ---------------------------------------------------------------------------
// IconButton / Action — small calm buttons used in toolbars
// ---------------------------------------------------------------------------
type ActionProps = React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "ghost" | "subtle";
  size?: "sm" | "md";
};
export function Action({
  variant = "subtle",
  size = "md",
  className,
  type = "button",
  ...props
}: ActionProps) {
  const sizing = size === "sm" ? "h-7 px-2.5 text-xs" : "h-9 px-3 text-sm";
  const styles =
    variant === "primary"
      ? "bg-accent text-accent-fg hover:opacity-90"
      : variant === "ghost"
      ? "bg-transparent text-ink hover:bg-sunken"
      : "bg-surface text-ink border border-line hover:bg-sunken";
  return (
    <button
      type={type}
      className={clsx(
        "inline-flex items-center justify-center gap-1.5 rounded-md font-medium transition-colors duration-150 ease-calm",
        sizing,
        styles,
        className,
      )}
      {...props}
    />
  );
}

export function LinkAction({
  href,
  children,
  variant = "subtle",
  size = "md",
  className,
}: {
  href: string;
  children: React.ReactNode;
  variant?: "primary" | "ghost" | "subtle";
  size?: "sm" | "md";
  className?: string;
}) {
  const sizing = size === "sm" ? "h-7 px-2.5 text-xs" : "h-9 px-3 text-sm";
  const styles =
    variant === "primary"
      ? "bg-accent text-accent-fg hover:opacity-90"
      : variant === "ghost"
      ? "bg-transparent text-ink hover:bg-sunken"
      : "bg-surface text-ink border border-line hover:bg-sunken";
  return (
    <Link
      href={href}
      className={clsx(
        "inline-flex items-center justify-center gap-1.5 rounded-md font-medium transition-colors duration-150 ease-calm",
        sizing,
        styles,
        className,
      )}
    >
      {children}
    </Link>
  );
}

// ---------------------------------------------------------------------------
// Avatar — initials only (no AI generated faces)
// ---------------------------------------------------------------------------
export function Avatar({ name, size = 32 }: { name: string; size?: number }) {
  const initials = name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase())
    .join("");
  return (
    <span
      aria-hidden
      className="inline-flex items-center justify-center rounded-full bg-sunken text-[11px] font-semibold text-body shrink-0"
      style={{ width: size, height: size }}
    >
      {initials}
    </span>
  );
}

// ---------------------------------------------------------------------------
// InlineKbd — keyboard chip used in the command palette trigger
// ---------------------------------------------------------------------------
export function Kbd({ children }: { children: React.ReactNode }) {
  return (
    <kbd className="inline-flex items-center gap-0.5 rounded-md border border-line bg-surface px-1.5 py-0.5 font-mono text-[10px] text-muted">
      {children}
    </kbd>
  );
}
