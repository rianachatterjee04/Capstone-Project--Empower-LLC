"use client";
/**
 * My 1:1s — the employee side of the continuous-feedback loop.
 *
 * Employees can see their recurring 1:1 series, the shared agenda for the next
 * meeting, add their own agenda items (privately if they want), and track the
 * action items that carry over between meetings. Same backend as the manager
 * surface (/one-on-ones), scoped to the caller.
 */
import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { apiFetch, apiPost, apiPatch } from "@/lib/api";

import { PageHeader, Surface, SectionTitle, Pill, Action, EmptyState, Divider } from "@/components/ds";

type Series = { id: string; cadence: string; next_date: string | null; title: string; meeting_count: number };
type AgendaItem = { id: string; text: string; author_role: string; checked: boolean; is_private: boolean };
type ActionItem = { id: string; text: string; assignee_user_id: string | null; due: string | null; done: boolean };
type Meeting = { id: string; date: string; status: string; agenda_items: AgendaItem[]; talking_points: { id: string; text: string }[]; action_items: ActionItem[] };

const STATUS_TONE: Record<string, "success" | "warn" | "neutral"> = { done: "success", skipped: "warn", scheduled: "neutral" };

export default function MyOneOnOnesPage() {
  const [seriesId, setSeriesId] = useState<string>("");
  const [newAgenda, setNewAgenda] = useState("");
  const [isPrivate, setIsPrivate] = useState(false);

  const seriesQ = useQuery({ queryKey: ["my-oneonone-series"], queryFn: () => apiFetch<{ items: Series[] }>("/one-on-ones/series"), refetchInterval: 90_000 });

  useEffect(() => {
    if (!seriesId && seriesQ.data?.items?.length) setSeriesId(seriesQ.data.items[0].id);
  }, [seriesQ.data, seriesId]);

  const meetingsQ = useQuery({
    queryKey: ["my-oneonone-meetings", seriesId],
    queryFn: () => apiFetch<{ items: Meeting[] }>(`/one-on-ones/series/${seriesId}/meetings`),
    enabled: !!seriesId,
    refetchInterval: 90_000,
  });

  const meetings = meetingsQ.data?.items ?? [];
  const current = meetings[0];

  // Carried-over action items: everything still open across the whole series.
  const openActions = useMemo(() => {
    const out: { item: ActionItem; date: string }[] = [];
    for (const m of meetings) for (const a of m.action_items) if (!a.done) out.push({ item: a, date: m.date });
    return out;
  }, [meetings]);

  async function addAgenda() {
    if (!current || !newAgenda.trim()) return;
    await apiPost(`/one-on-ones/meetings/${current.id}/agenda`, { text: newAgenda, is_private: isPrivate });
    setNewAgenda("");
    setIsPrivate(false);
    await meetingsQ.refetch();
  }
  async function toggleAgenda(a: AgendaItem) {
    await apiPatch(`/one-on-ones/agenda/${a.id}`, { checked: !a.checked });
    await meetingsQ.refetch();
  }
  async function toggleAction(a: ActionItem) {
    await apiPatch(`/one-on-ones/actions/${a.id}`, { done: !a.done });
    await meetingsQ.refetch();
  }

  return (
    <div className="space-y-7 fp-fade-in">
      <PageHeader
        eyebrow="Growth"
        title="My 1:1s"
        subtitle="Your recurring check-ins. Add what you want to talk about, and keep track of the follow-ups that carry over."
      />

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        {/* Series + carried-over actions */}
        <div className="space-y-4">
          <Surface>
            <SectionTitle eyebrow="Your check-ins" title="Series" />
            <div className="mt-3 space-y-1.5">
              {seriesQ.isLoading ? (
                <div className="text-sm text-muted">Loading…</div>
              ) : (seriesQ.data?.items ?? []).length === 0 ? (
                <EmptyState title="No 1:1s yet" description="Ask your manager to set up a recurring 1:1." />
              ) : (
                (seriesQ.data?.items ?? []).map((s) => (
                  <button
                    key={s.id}
                    onClick={() => setSeriesId(s.id)}
                    className={`w-full text-left rounded-md px-3 py-2 border text-sm ${
                      seriesId === s.id ? "bg-accent text-accent-fg border-accent" : "bg-surface border-line text-body hover:bg-sunken"
                    }`}
                  >
                    <div className="font-medium">{s.title}</div>
                    <div className="text-xs opacity-80">{s.cadence} · next {s.next_date ?? "—"}</div>
                  </button>
                ))
              )}
            </div>
          </Surface>

          <Surface>
            <SectionTitle eyebrow="Follow-ups" title="Carried over" description="Open action items across your 1:1s." />
            <div className="mt-3 space-y-2">
              {openActions.length === 0 ? (
                <div className="text-sm text-muted">Nothing outstanding. Nice.</div>
              ) : (
                openActions.map(({ item, date }) => (
                  <label key={item.id} className="flex items-start gap-2 text-sm">
                    <input type="checkbox" checked={item.done} onChange={() => toggleAction(item)} className="mt-1" />
                    <span className="text-body">
                      {item.text}
                      <span className="block text-2xs uppercase tracking-eyebrow text-muted">from {date}{item.due ? ` · due ${item.due}` : ""}</span>
                    </span>
                  </label>
                ))
              )}
            </div>
          </Surface>
        </div>

        {/* Current meeting agenda */}
        <div className="lg:col-span-2 space-y-4">
          {meetingsQ.isLoading ? (
            <Surface><EmptyState title="Loading…" /></Surface>
          ) : !current ? (
            <Surface><EmptyState title="No upcoming meeting" description="Your next 1:1 agenda will appear here." /></Surface>
          ) : (
            <>
              <Surface>
                <div className="flex items-center justify-between">
                  <SectionTitle eyebrow={`Next meeting · ${current.date}`} title="Agenda" />
                  <Pill tone={STATUS_TONE[current.status] ?? "neutral"}>{current.status}</Pill>
                </div>
                <div className="mt-3 space-y-2">
                  {current.agenda_items.length === 0 ? (
                    <div className="text-sm text-muted">No agenda items yet. Add the first one below.</div>
                  ) : (
                    current.agenda_items.map((a) => (
                      <label key={a.id} className="flex items-start gap-2 text-sm">
                        <input type="checkbox" checked={a.checked} onChange={() => toggleAgenda(a)} className="mt-1" />
                        <span className={a.checked ? "line-through text-muted" : "text-body"}>{a.text}</span>
                        {a.is_private && <Pill tone="warn">private</Pill>}
                        <span className="text-2xs uppercase tracking-eyebrow text-muted ml-auto">{a.author_role}</span>
                      </label>
                    ))
                  )}
                </div>
                <Divider className="my-3" />
                <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
                  <input
                    value={newAgenda}
                    onChange={(e) => setNewAgenda(e.target.value)}
                    onKeyDown={(e) => { if (e.key === "Enter") addAgenda(); }}
                    placeholder="Add something to talk about…"
                    className="flex-1 h-9 rounded-md border border-line bg-canvas px-3 text-sm text-ink outline-none focus:bg-surface"
                  />
                  <label className="flex items-center gap-1.5 text-xs text-muted">
                    <input type="checkbox" checked={isPrivate} onChange={(e) => setIsPrivate(e.target.checked)} />
                    Private (only you)
                  </label>
                  <Action variant="primary" onClick={addAgenda} disabled={!newAgenda.trim()}>Add</Action>
                </div>
              </Surface>

              {current.talking_points.length > 0 && (
                <Surface>
                  <SectionTitle eyebrow="Shared" title="Talking points" />
                  <ul className="mt-3 space-y-1.5">
                    {current.talking_points.map((t) => <li key={t.id} className="text-sm text-body">• {t.text}</li>)}
                  </ul>
                </Surface>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
