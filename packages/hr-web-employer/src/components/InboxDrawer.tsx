"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";
import { useShellState } from "./ShellState";
import { Pill } from "./ds";
import { IconClose } from "./icons";

type Priority = {
  id: string; kind: string; title: string; detail: string;
  urgency: "urgent" | "today" | "this_week";
  cta_label: string; cta_href: string; impact: string; icon: string;
};
type Recommendation = { id: string; headline: string; rationale: string; confidence: "low" | "medium" | "high"; suggested_action: string; requires_approval_by: string[] };
type Report = { headline: string; priorities: Priority[]; recommendations: Recommendation[] };

const URGENCY_TONE: Record<string, "danger" | "warn" | "neutral"> = {
  urgent: "danger",
  today: "warn",
  this_week: "neutral",
};

export function InboxDrawer() {
  const { inboxOpen, closeInbox } = useShellState();
  const q = useQuery({
    queryKey: ["cpo-report-inbox"],
    queryFn: () => apiFetch<Report>("/cpo/report"),
    refetchInterval: 60_000,
    enabled: inboxOpen,
  });

  if (!inboxOpen) return null;
  const r = q.data;

  return (
    <div className="fixed inset-0 z-40">
      <div className="absolute inset-0 bg-ink/10" onClick={closeInbox} />
      <aside className="absolute right-0 top-0 h-full w-[440px] max-w-[92vw] bg-surface border-l border-line shadow-lift fp-slide-in flex flex-col">
        <header className="h-14 flex items-center justify-between px-5 border-b border-line">
          <div className="text-sm">
            <div className="font-semibold text-ink">Inbox</div>
            <div className="text-xs text-muted">{r?.headline ?? "Loading…"}</div>
          </div>
          <button onClick={closeInbox} className="text-muted hover:text-ink"><IconClose /></button>
        </header>

        <div className="flex-1 overflow-y-auto p-5 space-y-5">
          <section>
            <div className="fp-eyebrow mb-2">Priorities</div>
            {(r?.priorities ?? []).length === 0 ? (
              <div className="text-sm text-muted py-6 text-center">Nothing critical right now.</div>
            ) : (
              <div className="space-y-2">
                {r!.priorities.map((p) => (
                  <Link
                    key={p.id}
                    href={p.cta_href}
                    onClick={closeInbox}
                    className="block rounded-lg border border-line bg-canvas hover:bg-sunken transition-colors duration-150 ease-calm p-3"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="text-sm font-semibold text-ink">{p.title}</div>
                      <Pill tone={URGENCY_TONE[p.urgency] ?? "neutral"}>{p.urgency.replace("_", " ")}</Pill>
                    </div>
                    <div className="mt-1 text-xs text-muted">{p.detail}</div>
                  </Link>
                ))}
              </div>
            )}
          </section>

          <section>
            <div className="fp-eyebrow mb-2">AI recommendations</div>
            {(r?.recommendations ?? []).length === 0 ? (
              <div className="text-sm text-muted py-3">No proactive recommendations yet.</div>
            ) : (
              <div className="space-y-2">
                {r!.recommendations.map((rec) => (
                  <div key={rec.id} className="rounded-lg border border-line p-3">
                    <div className="flex items-start justify-between gap-2">
                      <div className="text-sm font-semibold text-ink">{rec.headline}</div>
                      <Pill tone={rec.confidence === "high" ? "success" : rec.confidence === "medium" ? "warn" : "neutral"}>
                        {rec.confidence}
                      </Pill>
                    </div>
                    <div className="mt-1 text-xs text-body">{rec.rationale}</div>
                    <div className="mt-2 text-xs text-muted">→ {rec.suggested_action}</div>
                    <div className="mt-1 text-2xs uppercase tracking-eyebrow text-muted">
                      Approval: {rec.requires_approval_by.join(" · ")}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </section>
        </div>
      </aside>
    </div>
  );
}
