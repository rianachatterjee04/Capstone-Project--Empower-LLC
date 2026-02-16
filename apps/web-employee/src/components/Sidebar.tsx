"use client";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { getUserContext, signOut, type AppRole } from "@/lib/auth";

type NavItem = { href: string; label: string; roles: AppRole[] };

const NAV: NavItem[] = [
  {
    "href": "/app",
    "label": "Dashboard",
    "roles": [
      "owner",
      "admin",
      "hr",
      "manager",
      "employee"
    ]
  },
  {
    "href": "/app/org",
    "label": "Org Tree",
    "roles": [
      "owner",
      "admin",
      "hr",
      "manager"
    ]
  },
  {
    "href": "/app/onboarding",
    "label": "Onboarding",
    "roles": [
      "owner",
      "admin",
      "hr",
      "manager",
      "employee"
    ]
  },
  {
    "href": "/app/cases",
    "label": "Reports",
    "roles": [
      "owner",
      "admin",
      "hr",
      "manager",
      "employee"
    ]
  },
  {
    "href": "/app/documents",
    "label": "Documents",
    "roles": [
      "owner",
      "admin",
      "hr",
      "manager",
      "employee"
    ]
  }
] as any;

export function Sidebar() {
  const [role, setRole] = useState<AppRole>("employee");
  const [email, setEmail] = useState<string | null>(null);

  useEffect(() => {
    getUserContext().then((ctx) => {
      setRole(ctx.role);
      setEmail(ctx.email);
    });
  }, []);

  const items = useMemo(() => NAV.filter((i) => i.roles.includes(role)), [role]);

  return (
    <aside className="w-64 border-r border-black/10 p-4">
      <div className="mb-6">
        <div className="text-lg font-semibold">Foundry People</div>
        <div className="text-xs text-black/60">Employee Portal</div>
      </div>

      <nav className="space-y-1">
        {items.map((item) => (
          <Link key={item.href} href={item.href} className="block rounded-xl px-3 py-2 text-sm hover:bg-black/5">
            {item.label}
          </Link>
        ))}
      </nav>

      <div className="mt-8 rounded-xl border border-black/10 p-3">
        <div className="text-xs text-black/60">Signed in</div>
        <div className="truncate text-sm font-medium">{email ?? "—"}</div>
        <div className="mt-2 text-xs text-black/60">
          Role: <span className="font-medium">{role}</span>
        </div>
        <button
          className="mt-3 w-full rounded-xl border border-black/15 px-3 py-2 text-sm hover:bg-black/5"
          onClick={() => signOut()}
        >
          Sign out
        </button>
      </div>
    </aside>
  );
}
