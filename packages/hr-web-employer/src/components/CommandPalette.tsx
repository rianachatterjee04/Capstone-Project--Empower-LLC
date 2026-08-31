"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { apiPost } from "@/lib/api";

import { useShellState } from "./ShellState";
import { NAV } from "./nav-config";
import { Kbd } from "./ds";
import { IconArrowUpRight, IconSparkle } from "./icons";

type Item =
  | { kind: "nav"; id: string; label: string; href: string; group: string; aiHinted?: boolean }
  | { kind: "agent"; id: string; label: string; agent: string }
  | { kind: "action"; id: string; label: string; group: string; href: string };

const AGENTS: { key: string; name: string }[] = [
  { key: "recruiting", name: "Recruiting agent" },
  { key: "onboarding", name: "Onboarding agent" },
  { key: "compliance", name: "Compliance agent" },
  { key: "performance", name: "Performance agent" },
  { key: "compensation", name: "Compensation agent" },
  { key: "workforce_planning", name: "Workforce planning agent" },
];

const QUICK_ACTIONS: { label: string; href: string; group: string }[] = [
  { label: "Open settings", href: "/app/settings", group: "Quick actions" },
  { label: "Open setup wizard", href: "/app/setup", group: "Quick actions" },
  { label: "Open engagement pulse", href: "/app/pulse", group: "Quick actions" },
  { label: "Open inbox", href: "/app/inbox", group: "Quick actions" },
  { label: "Open approvals", href: "/app/approvals", group: "Quick actions" },
  { label: "Open notifications", href: "/app/notifications", group: "Quick actions" },
  { label: "Open activity timeline", href: "/app/activity", group: "Quick actions" },
  { label: "Open calendar", href: "/app/calendar", group: "Quick actions" },
  { label: "Open goals & OKRs", href: "/app/goals", group: "Quick actions" },
  { label: "Open recognition", href: "/app/recognition", group: "Quick actions" },
  { label: "Open analytics", href: "/app/analytics", group: "Quick actions" },
  { label: "Open work hub", href: "/app/work", group: "Quick actions" },
  { label: "Open manager OS", href: "/app/manager", group: "Quick actions" },
  { label: "Open executive brief", href: "/app/brief", group: "Quick actions" },
  { label: "Open team workspaces", href: "/app/teams", group: "Quick actions" },
  { label: "Open company memory", href: "/app/memory", group: "Quick actions" },
  { label: "Open people CRM", href: "/app/crm", group: "Quick actions" },
  { label: "Open workforce finance", href: "/app/finance", group: "Quick actions" },
  { label: "Open org graph", href: "/app/org-graph", group: "Quick actions" },
  { label: "Open agent store", href: "/app/agent-store", group: "Quick actions" },
  { label: "Open command center", href: "/app/command-center", group: "Quick actions" },
  { label: "Ask the executive copilot", href: "/app/exec-copilot", group: "Quick actions" },
  { label: "Generate a job description", href: "/app/content-studio", group: "Quick actions" },
  { label: "Run AI interview", href: "/app/interview-ai", group: "Quick actions" },
  { label: "Review workforce risk", href: "/app/risk", group: "Quick actions" },
  { label: "Compensation review", href: "/app/comp", group: "Quick actions" },
  { label: "Performance cycle", href: "/app/performance", group: "Quick actions" },
  { label: "Submit a confidential report", href: "/app/ombudsman", group: "Quick actions" },
];

export function CommandPalette() {
  const { paletteOpen, closePalette } = useShellState();
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement>(null);
  const [query, setQuery] = useState("");
  const [busy, setBusy] = useState<string | null>(null);

  // Build the full item index.
  const items: Item[] = useMemo(() => {
    const out: Item[] = [];
    for (const section of NAV) {
      out.push({ kind: "nav", id: `nav-${section.id}`, label: section.label, href: section.href, group: "Sections" });
      for (const child of section.children ?? []) {
        out.push({
          kind: "nav",
          id: `nav-${section.id}-${child.href}`,
          label: `${section.label} · ${child.label}`,
          href: child.href,
          group: section.label,
          aiHinted: child.aiHinted,
        });
      }
    }
    for (const a of AGENTS) {
      out.push({ kind: "agent", id: `agent-${a.key}`, label: `Run ${a.name}`, agent: a.key });
    }
    for (const q of QUICK_ACTIONS) {
      out.push({ kind: "action", id: `action-${q.href}`, label: q.label, href: q.href, group: q.group });
    }
    return out;
  }, []);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return items;
    return items.filter((it) => it.label.toLowerCase().includes(q));
  }, [items, query]);

  const grouped = useMemo(() => {
    const m = new Map<string, Item[]>();
    for (const it of filtered) {
      const g = it.kind === "agent" ? "AI agents" : (it as any).group ?? "Other";
      m.set(g, [...(m.get(g) ?? []), it]);
    }
    return Array.from(m.entries());
  }, [filtered]);

  const [activeIdx, setActiveIdx] = useState(0);
  useEffect(() => { setActiveIdx(0); }, [query, paletteOpen]);

  // Focus input on open
  useEffect(() => {
    if (paletteOpen) {
      setQuery("");
      setTimeout(() => inputRef.current?.focus(), 10);
    }
  }, [paletteOpen]);

  if (!paletteOpen) return null;

  function go(it: Item) {
    if (it.kind === "nav" || it.kind === "action") {
      router.push(it.href);
      closePalette();
    } else if (it.kind === "agent") {
      setBusy(it.agent);
      apiPost(`/agents/${it.agent}/run`, {})
        .catch(() => { /* surfaced inside agents page */ })
        .finally(() => {
          setBusy(null);
          router.push(`/app/agents?agent=${it.agent}`);
          closePalette();
        });
    }
  }

  function onKey(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "ArrowDown") { e.preventDefault(); setActiveIdx((i) => Math.min(filtered.length - 1, i + 1)); }
    if (e.key === "ArrowUp")   { e.preventDefault(); setActiveIdx((i) => Math.max(0, i - 1)); }
    if (e.key === "Enter")     { e.preventDefault(); if (filtered[activeIdx]) go(filtered[activeIdx]); }
  }

  let runningIdx = -1;

  return (
    <div className="fixed inset-0 z-50 fp-fade-in">
      <div className="absolute inset-0 bg-ink/30" onClick={closePalette} />
      <div className="relative mx-auto mt-[12vh] max-w-2xl rounded-2xl bg-surface shadow-lift border border-line overflow-hidden">
        <div className="flex items-center gap-3 px-4 py-3 border-b border-line">
          <input
            ref={inputRef}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={onKey}
            className="flex-1 text-base bg-transparent outline-none placeholder:text-muted text-ink"
            placeholder="Search or run a command…"
          />
          <Kbd>esc</Kbd>
        </div>
        <div className="max-h-[60vh] overflow-y-auto p-2">
          {grouped.length === 0 && (
            <div className="px-3 py-10 text-center text-sm text-muted">No matches. Try a section name or an agent.</div>
          )}
          {grouped.map(([group, list]) => (
            <div key={group} className="py-1">
              <div className="px-3 py-1.5 fp-eyebrow">{group}</div>
              <div>
                {list.map((it) => {
                  runningIdx += 1;
                  const active = runningIdx === activeIdx;
                  return (
                    <button
                      key={it.id}
                      onClick={() => go(it)}
                      onMouseEnter={() => setActiveIdx(runningIdx)}
                      className={[
                        "w-full flex items-center justify-between gap-3 px-3 py-2 rounded-md text-left text-sm transition-colors duration-150 ease-calm",
                        active ? "bg-sunken text-ink" : "text-body hover:bg-sunken/60",
                      ].join(" ")}
                    >
                      <span className="flex items-center gap-2">
                        {it.kind === "agent" && <IconSparkle className="text-muted" />}
                        <span>{it.label}</span>
                        {("aiHinted" in it && it.aiHinted) ? <span className="text-2xs uppercase tracking-eyebrow text-muted">AI</span> : null}
                      </span>
                      <span className="flex items-center gap-2 text-muted">
                        {it.kind === "agent" && busy === (it as any).agent ? (
                          <span className="text-xs">running…</span>
                        ) : (
                          <IconArrowUpRight />
                        )}
                      </span>
                    </button>
                  );
                })}
              </div>
            </div>
          ))}
        </div>
        <div className="flex items-center justify-between px-4 py-2 border-t border-line bg-canvas text-xs text-muted">
          <div className="flex items-center gap-2">
            <Kbd>↑</Kbd><Kbd>↓</Kbd><span>navigate</span>
          </div>
          <div className="flex items-center gap-2">
            <Kbd>↵</Kbd><span>open</span>
          </div>
        </div>
      </div>
    </div>
  );
}
