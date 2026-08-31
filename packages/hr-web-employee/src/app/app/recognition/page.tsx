"use client";
/**
 * Recognition — the employee side. Give public praise to a colleague, react to
 * others' shout-outs, and see the wall + who's being recognised. Same backend
 * as the manager surface (/recognition).
 */
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { apiFetch, apiPost } from "@/lib/api";

import { PageHeader, Surface, SectionTitle, Pill, Action, EmptyState, Avatar, Divider } from "@/components/ds";

type Reaction = { emoji: string; count: number; by: string[] };
type Recognition = { id: string; from_name: string; to_name: string; body: string; values: string[]; visibility: string; reactions: Reaction[]; created_at: string };
type RecResponse = { items: Recognition[]; leaderboard: { name: string; received: number }[]; value_counts: Record<string, number>; values: string[]; total: number };

const REACTIONS = ["❤", "✨", "🙌", "🛠"];

function timeAgo(iso?: string) {
  if (!iso) return "—";
  const d = (Date.now() - new Date(iso).getTime()) / 1000;
  if (d < 3600) return `${Math.round(d / 60)}m ago`;
  if (d < 86400) return `${Math.round(d / 3600)}h ago`;
  return `${Math.round(d / 86400)}d ago`;
}

export default function MyRecognitionPage() {
  const [composing, setComposing] = useState(false);
  const [toName, setToName] = useState("");
  const [body, setBody] = useState("");
  const [selectedValues, setSelectedValues] = useState<string[]>([]);
  const [msg, setMsg] = useState<string | null>(null);

  const q = useQuery({ queryKey: ["my-recognition"], queryFn: () => apiFetch<RecResponse>("/recognition"), refetchInterval: 90_000 });
  const data = q.data;

  async function post() {
    if (!toName.trim() || !body.trim()) return;
    try {
      await apiPost("/recognition", { to_name: toName, body, values: selectedValues, from_name: "You" });
      setToName(""); setBody(""); setSelectedValues([]); setComposing(false); setMsg("Recognition posted.");
      await q.refetch();
    } catch (e) {
      setMsg((e as Error).message);
    }
  }
  async function react(id: string, emoji: string) {
    await apiPost(`/recognition/${id}/react`, { emoji, by: "You" });
    await q.refetch();
  }

  return (
    <div className="space-y-7 fp-fade-in">
      <PageHeader
        eyebrow="Culture"
        title="Recognition"
        subtitle="Catch someone doing great work. Public praise, tagged with the values they lived out."
        actions={<Action variant="primary" onClick={() => setComposing((v) => !v)}>{composing ? "Cancel" : "Give recognition"}</Action>}
      />

      {composing && (
        <Surface>
          <SectionTitle eyebrow="Compose" title="Recognise a colleague" />
          <div className="mt-3 grid grid-cols-1 md:grid-cols-3 gap-3">
            <input value={toName} onChange={(e) => setToName(e.target.value)} placeholder="To · their name"
              className="md:col-span-1 h-9 rounded-md border border-line bg-canvas px-3 text-sm text-ink outline-none focus:bg-surface" />
            <textarea value={body} onChange={(e) => setBody(e.target.value)} placeholder="Be specific. What did they do, and what was the impact?" rows={3}
              className="md:col-span-2 rounded-md border border-line bg-canvas px-3 py-2 text-sm text-ink outline-none focus:bg-surface" />
          </div>
          <div className="mt-3 flex flex-wrap gap-1.5">
            {(data?.values ?? []).map((v) => {
              const active = selectedValues.includes(v);
              return (
                <button key={v} onClick={() => setSelectedValues((prev) => active ? prev.filter((x) => x !== v) : [...prev, v])}
                  className={`text-xs rounded-md px-3 py-1.5 border ${active ? "bg-accent text-accent-fg border-accent" : "bg-surface border-line text-body hover:bg-sunken"}`}>
                  {v}
                </button>
              );
            })}
          </div>
          <div className="mt-3 flex items-center gap-2">
            <Action variant="primary" onClick={post} disabled={!toName.trim() || !body.trim()}>Post</Action>
            <span className="text-xs text-muted">Visible to the company by default.</span>
          </div>
          {msg && <div className="mt-2 text-xs text-muted">{msg}</div>}
        </Surface>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        <div className="lg:col-span-2 space-y-4">
          {q.isLoading ? (
            <Surface><EmptyState title="Loading…" /></Surface>
          ) : (data?.items ?? []).length === 0 ? (
            <Surface><EmptyState title="No recognition yet" description="Be the first to praise someone." /></Surface>
          ) : (
            (data?.items ?? []).map((r) => (
              <Surface key={r.id}>
                <div className="flex items-start gap-3">
                  <Avatar name={r.from_name} size={36} />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2 flex-wrap text-sm">
                      <span className="font-semibold text-ink">{r.from_name}</span>
                      <span className="text-muted">recognised</span>
                      <span className="font-semibold text-ink">{r.to_name}</span>
                      <span className="text-2xs uppercase tracking-eyebrow text-muted">{timeAgo(r.created_at)}</span>
                    </div>
                    <p className="mt-2 text-sm text-body leading-relaxed">{r.body}</p>
                    {(r.values ?? []).length > 0 && (
                      <div className="mt-3 flex flex-wrap gap-1.5">{(r.values ?? []).map((v) => <Pill key={v} tone="info">{v}</Pill>)}</div>
                    )}
                    <Divider className="my-3" />
                    <div className="flex items-center gap-1.5">
                      {REACTIONS.map((emoji) => {
                        const found = (r.reactions ?? []).find((rr) => rr.emoji === emoji);
                        return (
                          <button key={emoji} onClick={() => react(r.id, emoji)}
                            className={`h-7 px-2.5 rounded-full border text-xs flex items-center gap-1 ${found ? "bg-sunken border-line text-ink" : "bg-surface border-line text-body hover:bg-sunken"}`}>
                            <span>{emoji}</span>{found && <span className="tabular-nums">{found.count}</span>}
                          </button>
                        );
                      })}
                    </div>
                  </div>
                </div>
              </Surface>
            ))
          )}
        </div>

        <div className="space-y-4">
          <Surface>
            <SectionTitle eyebrow="Top received" title="Leaderboard" />
            <ol className="mt-3 space-y-2">
              {(data?.leaderboard ?? []).length === 0 ? (
                <div className="text-sm text-muted">No recognition yet.</div>
              ) : (data?.leaderboard ?? []).map((row, i) => (
                <li key={row.name} className="flex items-center justify-between gap-2 rounded-md px-2 py-1.5 hover:bg-sunken">
                  <div className="flex items-center gap-2 min-w-0">
                    <span className="text-2xs uppercase tracking-eyebrow text-muted w-4 text-right">{i + 1}</span>
                    <Avatar name={row.name} size={22} />
                    <span className="text-sm text-ink truncate">{row.name}</span>
                  </div>
                  <span className="text-sm tabular-nums text-muted">{row.received}</span>
                </li>
              ))}
            </ol>
          </Surface>
        </div>
      </div>
    </div>
  );
}
