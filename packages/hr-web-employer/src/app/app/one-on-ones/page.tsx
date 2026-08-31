"use client";
import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { apiFetch, apiPost, apiPatch } from "@/lib/api";

import { PageHeader, Surface, SectionTitle, Pill, Action, EmptyState, Divider } from "@/components/ds";

type Series = {
  id: string;
  manager_user_id: string;
  report_user_id: string;
  cadence: string;
  next_date: string | null;
  title: string;
  meeting_count: number;
};
type AgendaItem = { id: string; text: string; author_role: string; checked: boolean; is_private: boolean };
type TalkingPoint = { id: string; text: string };
type ActionItem = { id: string; text: string; assignee_user_id: string | null; due: string | null; done: boolean };
type Meeting = {
  id: string;
  date: string;
  status: string;
  agenda_items: AgendaItem[];
  talking_points: TalkingPoint[];
  action_items: ActionItem[];
};

const STATUS_TONE: Record<string, "success" | "warn" | "neutral"> = {
  done: "success",
  skipped: "warn",
  scheduled: "neutral",
};

export default function OneOnOnesPage() {
  const [seriesId, setSeriesId] = useState<string>("");
  const [newAgenda, setNewAgenda] = useState("");
  const [isPrivate, setIsPrivate] = useState(false);
  const [suggestions, setSuggestions] = useState<string[]>([]);

  const seriesQ = useQuery({
    queryKey: ["oneonone-series"],
    queryFn: () => apiFetch<{ items: Series[] }>("/one-on-ones/series"),
    refetchInterval: 90_000,
  });

  useEffect(() => {
    if (!seriesId && seriesQ.data?.items?.length) setSeriesId(seriesQ.data.items[0].id);
  }, [seriesQ.data, seriesId]);

  const meetingsQ = useQuery({
    queryKey: ["oneonone-meetings", seriesId],
    queryFn: () => apiFetch<{ items: Meeting[] }>(`/one-on-ones/series/${seriesId}/meetings`),
    enabled: !!seriesId,
    refetchInterval: 90_000,
  });

  const meetings = meetingsQ.data?.items ?? [];
  const current = meetings[0];

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

  async function markDone() {
    if (!current) return;
    await apiPatch(`/one-on-ones/meetings/${current.id}/status`, { status: "done" });
    await meetingsQ.refetch();
  }

  async function suggest() {
    if (!seriesId) return;
    const out = await apiPost<{ suggestions: string[] }>(`/one-on-ones/series/${seriesId}/suggest-agenda`, {});
    setSuggestions(out.suggestions ?? []);
  }

  return (
    <div className="space-y-7 fp-fade-in">
      <PageHeader
        eyebrow="Performance"
        title="1:1s"
        subtitle="Recurring manager ↔ report meetings. Shared agenda, private notes, and action items — private notes stay with their author."
        actions={<Action variant="subtle" onClick={suggest}>Suggest agenda</Action>}
      />

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        {/* Series list */}
        <div className="space-y-4">
          <Surface>
            <SectionTitle eyebrow="Your 1:1s" title="Series" />
            <div className="mt-3 space-y-1.5">
              {(seriesQ.data?.items ?? []).length === 0 ? (
                <EmptyState title="No 1:1s yet" description="Ask your manager or HR to set one up." />
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

          {suggestions.length > 0 && (
            <Surface>
              <SectionTitle eyebrow="AI assist" title="Suggested talking points" />
              <ul className="mt-3 space-y-2">
                {suggestions.map((t, i) => (
                  <li key={i} className="text-sm text-body flex gap-2">
                    <span className="text-muted">•</span>
                    <span>{t}</span>
                  </li>
                ))}
              </ul>
            </Surface>
          )}
        </div>

        {/* Current meeting */}
        <div className="lg:col-span-2 space-y-4">
          {meetingsQ.isLoading ? (
            <Surface><EmptyState title="Loading…" /></Surface>
          ) : !current ? (
            <Surface><EmptyState title="No meetings" description="Create a meeting to start your agenda." /></Surface>
          ) : (
            <>
              <Surface>
                <div className="flex items-center justify-between">
                  <SectionTitle eyebrow={`Meeting · ${current.date}`} title="Agenda" />
                  <div className="flex items-center gap-2">
                    <Pill tone={STATUS_TONE[current.status] ?? "neutral"}>{current.status}</Pill>
                    {current.status !== "done" && <Action variant="subtle" onClick={markDone}>Mark done</Action>}
                  </div>
                </div>

                <div className="mt-3 space-y-2">
                  {current.agenda_items.length === 0 ? (
                    <div className="text-sm text-muted">No agenda items yet.</div>
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
                    placeholder="Add an agenda item…"
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
                    {current.talking_points.map((t) => (
                      <li key={t.id} className="text-sm text-body">• {t.text}</li>
                    ))}
                  </ul>
                </Surface>
              )}

              <Surface>
                <SectionTitle eyebrow="Follow-ups" title="Action items" />
                <div className="mt-3 space-y-2">
                  {current.action_items.length === 0 ? (
                    <div className="text-sm text-muted">No action items.</div>
                  ) : (
                    current.action_items.map((a) => (
                      <label key={a.id} className="flex items-center gap-2 text-sm">
                        <input type="checkbox" checked={a.done} onChange={() => toggleAction(a)} />
                        <span className={a.done ? "line-through text-muted" : "text-body"}>{a.text}</span>
                        {a.due && <span className="text-2xs uppercase tracking-eyebrow text-muted ml-auto">due {a.due}</span>}
                      </label>
                    ))
                  )}
                </div>
              </Surface>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
