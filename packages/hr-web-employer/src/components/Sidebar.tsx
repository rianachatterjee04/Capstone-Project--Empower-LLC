"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import clsx from "clsx";

import { getUserContext, signOut, type AppRole } from "@/lib/auth";
import { NAV } from "./nav-config";
import { Avatar } from "./ds";
import { IconClose, IconLogout } from "./icons";
import { useShellState } from "./ShellState";

// Where the unified Fintra launchpad / module switcher lives (Accounting,
// AuditWise, HR). Lets a user leave the HR app and return to the others.
const FINTRA_APP_URL = process.env.NEXT_PUBLIC_FINTRA_APP_URL || (process.env.NODE_ENV === "production" ? "https://finance.fintrahub.com" : "http://localhost:3000");
// The single Fintra marketing site / front door. The logo links here.
const FINTRA_SITE_URL = process.env.NEXT_PUBLIC_SITE_URL || (process.env.NODE_ENV === "production" ? "https://fintrahub.com" : "http://localhost:5173");

/**
 * Slim primary sidebar.
 *
 * - 8 destinations max, each with an icon and label.
 * - The active section is highlighted with a subtle inset background; no
 *   gradients, no glow.
 * - Sub-navigation for the active section appears as a calm second column
 *   so the user always knows where they are within a workflow.
 */
export function Sidebar() {
  const [role, setRole] = useState<AppRole>("employee");
  const [email, setEmail] = useState<string | null>(null);
  const pathname = usePathname() ?? "/app";
  const { mobileNavOpen, closeMobileNav } = useShellState();

  useEffect(() => {
    getUserContext().then((ctx) => {
      setRole(ctx.role);
      setEmail(ctx.email);
    });
  }, []);

  // Close mobile nav on every route change
  useEffect(() => {
    closeMobileNav();
  }, [pathname, closeMobileNav]);

  const sections = useMemo(() => NAV.filter((s) => s.roles.includes(role)), [role]);

  const active = useMemo(() => {
    // Pick the section whose href is the longest prefix of the current path.
    let best = sections[0];
    let bestLen = -1;
    for (const s of sections) {
      const matches =
        pathname === s.href || pathname.startsWith(s.href + "/") ||
        (s.children ?? []).some((c) => pathname === c.href || pathname.startsWith(c.href + "/"));
      if (matches && s.href.length > bestLen) {
        best = s;
        bestLen = s.href.length;
      }
    }
    return best;
  }, [pathname, sections]);

  return (
    <>
    {mobileNavOpen && (
      <div
        className="lg:hidden fixed inset-0 z-30 bg-ink/20"
        onClick={closeMobileNav}
        aria-hidden
      />
    )}
    <aside
      className={[
        "flex",
        // Desktop: always visible as flex row.
        "lg:relative lg:translate-x-0 lg:opacity-100",
        // Mobile: fixed slide-in drawer.
        "fixed inset-y-0 left-0 z-40 transition-transform duration-200 ease-calm",
        mobileNavOpen ? "translate-x-0" : "-translate-x-full lg:translate-x-0",
      ].join(" ")}
    >
      {/* Primary rail: icon + readable label per destination */}
      <div className="w-[88px] border-r border-line bg-canvas flex flex-col items-center py-3 gap-1 sticky top-0 h-screen overflow-y-auto">
        {/* Back to Fintra / app switcher */}
        <a
          href={FINTRA_SITE_URL}
          className="group mb-1 mt-0.5 flex w-full flex-col items-center gap-0.5"
          title="Fintra home"
        >
          <span className="text-sm font-semibold text-ink group-hover:opacity-90">Fintra</span>
        </a>
        <div className="my-1 h-px w-8 bg-line" />

        <nav className="flex w-full flex-col items-center gap-0.5 px-1">
          {sections.map((s) => {
            const isActive = active?.id === s.id;
            const Icon = s.icon;
            return (
              <Link
                key={s.id}
                href={s.href}
                className={clsx(
                  "group flex w-full flex-col items-center gap-1 rounded-lg py-1.5 text-muted",
                  "transition-colors duration-150 ease-calm",
                  isActive ? "bg-accent text-accent-fg" : "hover:bg-sunken hover:text-ink",
                )}
                aria-current={isActive ? "page" : undefined}
                title={s.label}
              >
                <Icon size={18} />
                <span className="max-w-full truncate px-0.5 text-[10px] leading-tight text-center">
                  {s.label}
                </span>
              </Link>
            );
          })}
        </nav>

        <div className="flex-1" />

        <button
          onClick={() => signOut()}
          className="flex w-full flex-col items-center gap-1 rounded-lg py-1.5 text-muted hover:bg-sunken hover:text-ink transition-colors duration-150 ease-calm"
          title="Sign out"
        >
          <IconLogout size={16} />
          <span className="text-[10px] leading-none">Sign out</span>
        </button>
      </div>

      {/* Secondary contextual rail (calm grey list) */}
      {active && (
        <div className="w-[220px] border-r border-line bg-canvas px-3 py-5 sticky top-0 h-screen overflow-y-auto">
          <div className="lg:hidden flex justify-end mb-2">
            <button
              onClick={closeMobileNav}
              className="h-7 w-7 rounded-md text-muted hover:text-ink hover:bg-sunken flex items-center justify-center"
              aria-label="Close menu"
            >
              <IconClose size={16} />
            </button>
          </div>
          <div className="fp-eyebrow px-2 mb-1">{active.label}</div>
          <div className="text-base font-semibold text-ink px-2 mb-4">{active.label}</div>

          <nav className="flex flex-col gap-0.5">
            <SecondaryLink href={active.href} label="Overview" active={pathname === active.href} />
            {(active.children ?? []).filter((c) => !c.roles || c.roles.includes(role)).map((c, i) => {
              // Children may carry a query string for in-page deep-links
              // (e.g. /app/equity?tab=Dilution); compare on the path only.
              const cPath = c.href.split("?")[0];
              return (
                <SecondaryLink
                  key={`${c.href}-${i}`}
                  href={c.href}
                  label={c.label}
                  aiHinted={c.aiHinted}
                  active={pathname === cPath || pathname.startsWith(cPath + "/")}
                />
              );
            })}
          </nav>

          <div className="mt-6 px-2 rounded-lg border border-line bg-surface p-3 flex items-center gap-2">
            <Avatar name={email ?? "Guest"} size={28} />
            <div className="min-w-0">
              <div className="text-xs font-medium text-ink truncate">{email ?? "Dev mode"}</div>
              <div className="text-2xs uppercase tracking-eyebrow text-muted">{role}</div>
            </div>
          </div>
        </div>
      )}
    </aside>
    </>
  );
}

function SecondaryLink({
  href,
  label,
  active,
  aiHinted,
}: {
  href: string;
  label: string;
  active: boolean;
  aiHinted?: boolean;
}) {
  return (
    <Link
      href={href}
      className={clsx(
        "group flex items-center justify-between gap-2 rounded-md px-2.5 py-1.5 text-sm transition-colors duration-150 ease-calm",
        active ? "bg-surface text-ink shadow-soft" : "text-body hover:bg-surface/70 hover:text-ink",
      )}
    >
      <span className="min-w-0 truncate">{label}</span>
      {aiHinted && (
        <span
          className="shrink-0 rounded-full bg-accent-soft px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wide text-accent-softFg"
          title="AI-powered"
        >
          AI
        </span>
      )}
    </Link>
  );
}
