"use client";
import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { apiFetch, apiPost } from "@/lib/api";

import { PageHeader, Surface, SectionTitle, Pill, Action, EmptyState, MetricStat, Divider } from "@/components/ds";

type Level = { id: string; name: string; title: string; index: number };
type Competency = { id: string; name: string; category: string; description: string };
type Ladder = { id: string; family: string; levels: Level[]; competencies: Competency[]; expectations: any[] };
type GapRow = {
  competency_id: string;
  competency: string;
  category: string;
  target_expected_rating: number | null;
  current_rating: number;
  gap: number | null;
  below_bar: boolean;
  rubric: string | null;
};
type Gap = {
  plan_id: string;
  employee_id: string;
  current_level_id: string | null;
  target_level_id: string | null;
  linked_goal_id: string | null;
  competencies: GapRow[];
  below_bar: GapRow[];
  below_bar_count: number;
};
type Plan = { id: string; employee_id: string; ladder_id: string; status: string };

export default function GrowPage() {
  const [ladderId, setLadderId] = useState<string>("");
  const [actions, setActions] = useState<string[]>([]);

  const laddersQ = useQuery({
    queryKey: ["grow-ladders"],
    queryFn: () => apiFetch<{ items: Ladder[] }>("/grow/ladders"),
    refetchInterval: 120_000,
  });
  useEffect(() => {
    if (!ladderId && laddersQ.data?.items?.length) setLadderId(laddersQ.data.items[0].id);
  }, [laddersQ.data, ladderId]);
  const ladder = (laddersQ.data?.items ?? []).find((l) => l.id === ladderId);

  const plansQ = useQuery({
    queryKey: ["grow-plans"],
    queryFn: () => apiFetch<{ items: Plan[] }>("/grow/plans"),
    refetchInterval: 120_000,
  });
  const plan = plansQ.data?.items?.[0];

  const gapQ = useQuery({
    queryKey: ["grow-gap", plan?.id],
    queryFn: () => apiFetch<Gap>(`/grow/plans/${plan!.id}/gap`),
    enabled: !!plan?.id,
    refetchInterval: 120_000,
  });
  const gap = gapQ.data;

  async function suggest() {
    if (!plan?.id) return;
    const out = await apiPost<{ actions: string[] }>(`/grow/plans/${plan.id}/suggest-actions`, {});
    setActions(out.actions ?? []);
  }

  const levelName = (id: string | null | undefined) =>
    ladder?.levels.find((l) => l.id === id)?.name ?? "—";

  return (
    <div className="space-y-7 fp-fade-in">
      <PageHeader
        eyebrow="Performance"
        title="Grow"
        subtitle="Career ladders, competency frameworks, and growth plans. See the gap between where you are and the next level."
        actions={<Action variant="subtle" onClick={suggest}>Suggest development actions</Action>}
      />

      {/* Ladder selector */}
      <div className="flex flex-wrap gap-1.5">
        {(laddersQ.data?.items ?? []).map((l) => (
          <button
            key={l.id}
            onClick={() => setLadderId(l.id)}
            className={`text-xs rounded-md px-3 py-1.5 border ${
              ladderId === l.id ? "bg-accent text-accent-fg border-accent" : "bg-surface border-line text-body hover:bg-sunken"
            }`}
          >
            {l.family}
          </button>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        {/* Ladder view */}
        <div className="lg:col-span-2 space-y-4">
          <Surface>
            <SectionTitle eyebrow="Career ladder" title={ladder ? `${ladder.family} levels` : "Ladder"} />
            {ladder ? (
              <div className="mt-3 flex flex-wrap gap-2">
                {ladder.levels.map((lv) => (
                  <div key={lv.id} className="rounded-md border border-line bg-surface px-3 py-2 text-sm">
                    <div className="font-semibold text-ink">{lv.name}</div>
                    <div className="text-xs text-muted">{lv.title}</div>
                  </div>
                ))}
              </div>
            ) : (
              <EmptyState title="No ladders yet" />
            )}
          </Surface>

          <Surface>
            <SectionTitle eyebrow="Competencies" title="Framework" />
            <div className="mt-3 space-y-2">
              {(ladder?.competencies ?? []).map((c) => (
                <div key={c.id} className="flex items-start gap-2">
                  <Pill tone="neutral">{c.category}</Pill>
                  <div>
                    <div className="text-sm text-ink">{c.name}</div>
                    {c.description && <div className="text-xs text-muted">{c.description}</div>}
                  </div>
                </div>
              ))}
            </div>
          </Surface>
        </div>

        {/* My growth plan + gap view */}
        <div className="space-y-4">
          <Surface>
            <SectionTitle eyebrow="My growth plan" title="Level & target" />
            {gap ? (
              <>
                <div className="mt-3 grid grid-cols-2 gap-3">
                  <MetricStat label="Current" value={levelName(gap.current_level_id)} />
                  <MetricStat label="Target" value={levelName(gap.target_level_id)} tone="info" />
                </div>
                {gap.linked_goal_id && (
                  <div className="mt-2 text-xs text-muted">Tied to goal <span className="font-mono">{gap.linked_goal_id}</span></div>
                )}
                <Divider className="my-3" />
                <div className="text-sm font-medium text-ink mb-2">
                  {gap.below_bar_count} competenc{gap.below_bar_count === 1 ? "y" : "ies"} below target
                </div>
                <div className="space-y-2">
                  {gap.competencies.map((row) => (
                    <div key={row.competency_id}>
                      <div className="flex items-center justify-between text-sm">
                        <span className="text-ink">{row.competency}</span>
                        <span className="font-mono text-xs text-muted">
                          {row.current_rating}/{row.target_expected_rating ?? "—"}
                          {row.below_bar && <span className="text-danger"> · gap {row.gap}</span>}
                        </span>
                      </div>
                      <div className="mt-1 h-1.5 rounded-full bg-sunken overflow-hidden">
                        <div
                          className={`h-full ${row.below_bar ? "bg-danger" : "bg-success"}`}
                          style={{ width: `${Math.min(100, (row.current_rating / (row.target_expected_rating || 5)) * 100)}%` }}
                        />
                      </div>
                    </div>
                  ))}
                </div>
              </>
            ) : (
              <EmptyState title="No growth plan" description="Ask HR to create your growth plan." />
            )}
          </Surface>

          {actions.length > 0 && (
            <Surface>
              <SectionTitle eyebrow="AI assist" title="Development actions" />
              <ul className="mt-3 space-y-2">
                {actions.map((a, i) => (
                  <li key={i} className="text-sm text-body flex gap-2">
                    <span className="text-muted">•</span>
                    <span>{a}</span>
                  </li>
                ))}
              </ul>
            </Surface>
          )}
        </div>
      </div>
    </div>
  );
}
