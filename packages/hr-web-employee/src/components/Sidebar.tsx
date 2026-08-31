"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import clsx from "clsx";

import { getUserContext, signOut, type AppRole } from "@/lib/auth";
import { NAV } from "./nav-config";
import { Avatar } from "./ds";
import { IconLogout } from "./icons";

/**
 * Employee portal sidebar — same calm pattern as employer, employee language.
 */
export function Sidebar() {
  const [role, setRole] = useState<AppRole>("employee");
  const [email, setEmail] = useState<string | null>(null);
  const pathname = usePathname() ?? "/app";

  useEffect(() => {
    getUserContext().then((ctx) => {
      setRole(ctx.role);
      setEmail(ctx.email);
    });
  }, []);

  const sections = useMemo(() => NAV.filter((s) => s.roles.includes(role)), [role]);

  const active = useMemo(() => {
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
    <aside className="flex">
      <div className="w-[68px] border-r border-line bg-canvas flex flex-col items-center py-3 gap-2 sticky top-0 h-screen">
        <div className="mb-3 mt-1 flex h-9 items-center justify-center font-semibold text-sm text-ink">
          Fintra
        </div>

        <nav className="flex flex-col items-center gap-1.5">
          {sections.map((s) => {
            const isActive = active?.id === s.id;
            const Icon = s.icon;
            return (
              <Link
                key={s.id}
                href={s.href}
                className={clsx(
                  "group relative flex h-10 w-10 items-center justify-center rounded-lg text-muted",
                  "transition-colors duration-150 ease-calm",
                  isActive ? "bg-accent text-accent-fg" : "hover:bg-sunken hover:text-ink",
                )}
                aria-current={isActive ? "page" : undefined}
                title={s.label}
              >
                <Icon size={18} />
                <span
                  className={clsx(
                    "pointer-events-none absolute left-12 top-1/2 -translate-y-1/2 whitespace-nowrap rounded-md px-2 py-1 text-xs",
                    "bg-ink text-canvas opacity-0 transition-opacity duration-150 ease-calm",
                    "group-hover:opacity-100",
                  )}
                >
                  {s.label}
                </span>
              </Link>
            );
          })}
        </nav>

        <div className="flex-1" />

        <button
          onClick={() => signOut()}
          className="h-9 w-9 flex items-center justify-center rounded-lg text-muted hover:bg-sunken hover:text-ink transition-colors duration-150 ease-calm"
          title="Sign out"
        >
          <IconLogout size={16} />
        </button>
      </div>

      {active && (
        <div className="w-[220px] border-r border-line bg-canvas px-3 py-5 sticky top-0 h-screen overflow-y-auto">
          <div className="fp-eyebrow px-2 mb-1">{active.label}</div>
          <div className="text-base font-semibold text-ink px-2 mb-4">{active.label}</div>

          <nav className="flex flex-col gap-0.5">
            <SecondaryLink href={active.href} label="Overview" active={pathname === active.href} />
            {(active.children ?? []).map((c) => (
              <SecondaryLink
                key={c.href}
                href={c.href}
                label={c.label}
                active={pathname === c.href || pathname.startsWith(c.href + "/")}
              />
            ))}
          </nav>

          <div className="mt-6 rounded-lg border border-line bg-surface p-3 flex items-center gap-2">
            <Avatar name={email ?? "Guest"} size={28} />
            <div className="min-w-0">
              <div className="text-xs font-medium text-ink truncate">{email ?? "Dev mode"}</div>
              <div className="text-2xs uppercase tracking-eyebrow text-muted">{role}</div>
            </div>
          </div>
        </div>
      )}
    </aside>
  );
}

function SecondaryLink({
  href, label, active,
}: { href: string; label: string; active: boolean }) {
  return (
    <Link
      href={href}
      className={clsx(
        "group flex items-center justify-between rounded-md px-2.5 py-1.5 text-sm transition-colors duration-150 ease-calm",
        active ? "bg-surface text-ink shadow-soft" : "text-body hover:bg-surface/70 hover:text-ink",
      )}
    >
      <span>{label}</span>
    </Link>
  );
}
