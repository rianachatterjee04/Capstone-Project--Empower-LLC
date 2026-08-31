"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";

import { IconInbox, IconMenu, IconSearch, IconSparkle } from "./icons";
import { Kbd } from "./ds";
import { useShellState } from "./ShellState";

type CPOPriorities = { priorities: unknown[] };

/**
 * Top bar — calm. One row, three intents:
 *  1. Universal search (Cmd+K command palette)
 *  2. Inbox — navigates to /app/inbox; an adjacent "peek" toggles the drawer
 *  3. AI assistant dock (RAG helpdesk)
 */
export function Topbar() {
  const { openPalette, toggleAssistant, toggleInbox, toggleMobileNav } = useShellState();
  const [mac, setMac] = useState(false);

  useEffect(() => {
    setMac(typeof navigator !== "undefined" && /Mac|iPhone|iPad/.test(navigator.platform));
  }, []);

  const inboxQ = useQuery({
    queryKey: ["cpo-priority-count"],
    queryFn: () => apiFetch<CPOPriorities>("/cpo/report"),
    refetchInterval: 90_000,
    staleTime: 60_000,
  });
  const inboxCount = inboxQ.data?.priorities?.length ?? 0;

  return (
    <header className="sticky top-0 z-20 border-b border-line bg-canvas/85 backdrop-blur">
      <div className="flex items-center gap-2 sm:gap-3 px-3 sm:px-6 h-14">
        <button
          onClick={toggleMobileNav}
          className="lg:hidden h-9 w-9 rounded-md border border-line bg-surface text-ink hover:bg-sunken flex items-center justify-center"
          aria-label="Open menu"
        >
          <IconMenu />
        </button>
        <button
          onClick={openPalette}
          className="group flex items-center gap-2.5 text-left h-9 px-3 rounded-md bg-surface border border-line hover:bg-sunken transition-colors duration-150 ease-calm flex-1 lg:flex-none lg:w-[420px] max-w-[60vw]"
        >
          <IconSearch className="text-muted" />
          <span className="text-sm text-muted flex-1 truncate hidden sm:inline">Search people, jobs, policies — or run an agent</span>
          <span className="text-sm text-muted flex-1 truncate sm:hidden">Search…</span>
          <Kbd>{mac ? "⌘" : "Ctrl"} K</Kbd>
        </button>

        <div className="flex-1" />

        {/* Inbox — split: primary link opens the full page, peek toggles the drawer */}
        <div className="flex items-stretch h-9 rounded-md border border-line bg-surface overflow-hidden">
          <Link
            href="/app/inbox"
            className="flex items-center gap-2 px-2.5 sm:px-3 text-sm text-body hover:bg-sunken transition-colors duration-150 ease-calm"
            title="Open inbox"
          >
            <IconInbox />
            <span className="hidden sm:inline">Inbox</span>
            {inboxCount > 0 && (
              <span className="ml-1 inline-flex items-center justify-center h-5 min-w-[20px] rounded-full bg-ink text-canvas text-[10px] font-semibold px-1">
                {inboxCount}
              </span>
            )}
          </Link>
          <button
            onClick={toggleInbox}
            className="hidden sm:block px-2 border-l border-line text-muted hover:bg-sunken hover:text-ink transition-colors duration-150 ease-calm text-2xs uppercase tracking-eyebrow"
            title="Quick peek"
          >
            peek
          </button>
        </div>

        <button
          onClick={toggleAssistant}
          className="h-9 px-2.5 sm:px-3 rounded-md bg-accent text-accent-fg hover:opacity-90 transition-opacity duration-150 ease-calm flex items-center gap-2 text-sm"
          title="Ask the assistant"
        >
          <IconSparkle />
          <span className="hidden sm:inline">Assistant</span>
        </button>
      </div>
    </header>
  );
}
