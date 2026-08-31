"use client";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";

import { PageHeader, Surface, Pill, Action, EmptyState, LinkAction } from "@/components/ds";
import { IconArrowUpRight, IconSparkle } from "@/components/icons";
import { useShellState } from "@/components/ShellState";

type Chart = { series: number[]; labels: string[]; suffix: string };
type Insight = {
  id: string;
  headline: string;
  narrative: string;
  metric_label: string;
  metric_value: string;
  delta_label?: string | null;
  delta_direction: "up" | "down" | "flat";
  delta_tone: string;
  chart?: Chart | null;
  suggested_action?: string | null;
  cta_label?: string | null;
  cta_href?: string | null;
  /** The query this insight was computed from. */
  evidence?: string | null;
};
type Unavailable = { topic: string; reason: string; needs: string };
type AnalyticsResponse = {
  generated_at: string;
  insights: Insight[];
  unavailable?: Unavailable[];
  note?: string;
};

const DELTA_TONE: Record<string, "danger" | "warn" | "success" | "neutral"> = {
  danger: "danger", warn: "warn", success: "success", neutral: "neutral",
};

function Sparkline({ chart }: { chart: Chart }) {
  if (!chart || chart.series.length === 0) return null;
  const max = Math.max(...chart.series);
  const min = Math.min(...chart.series);
  const range = max - min || 1;
  const w = 240, h = 56, step = chart.series.length > 1 ? w / (chart.series.length - 1) : 0;
  const points = chart.series.map((v, i) => {
    const x = i * step;
    const y = h - ((v - min) / range) * (h - 8) - 4;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });
  const dPath = `M ${points.join(" L ")}`;
  const dFill = `${dPath} L ${(w).toFixed(1)},${h} L 0,${h} Z`;
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="w-full h-14">
      <path d={dFill} fill="rgba(15,118,110,0.08)" />
      <path d={dPath} fill="none" stroke="#0F766E" strokeWidth="1.4" />
      {chart.series.map((v, i) => (
        <circle key={i} cx={(i * step).toFixed(1)} cy={(h - ((v - min) / range) * (h - 8) - 4).toFixed(1)} r="1.8" fill="#0F766E" />
      ))}
    </svg>
  );
}

export default function AnalyticsPage() {
  const q = useQuery({
    queryKey: ["narrative-analytics"],
    queryFn: () => apiFetch<AnalyticsResponse>("/narrative-analytics"),
    refetchInterval: 5 * 60_000,
  });
  const { openAssistant } = useShellState();

  const insights = q.data?.insights ?? [];

  return (
    <div className="space-y-7 fp-fade-in">
      <PageHeader
        eyebrow="Analytics"
        title="Narrative insights"
        subtitle="Every insight here is computed from your own records and says which query it came from. Topics with no evidence are listed as unavailable rather than estimated."
        actions={
          <>
            <Action variant="subtle" onClick={() => q.refetch()}>Refresh</Action>
            <button
              onClick={openAssistant}
              className="h-9 px-3 rounded-md bg-accent text-accent-fg hover:opacity-90 transition-opacity duration-150 ease-calm flex items-center gap-2 text-sm"
            >
              <IconSparkle /> Ask follow-up
            </button>
          </>
        }
      />

      {q.isLoading ? (
        <Surface><EmptyState title="Loading…" /></Surface>
      ) : insights.length === 0 ? (
        <Surface><EmptyState title="No insights yet" /></Surface>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
          {insights.map((ins) => (
            <Surface key={ins.id} pad="lg">
              <div className="text-base font-semibold text-ink tracking-tight leading-snug">{ins.headline}</div>
              <p className="mt-2 text-sm text-body leading-relaxed">{ins.narrative}</p>

              <div className="mt-5 flex items-end justify-between gap-4">
                <div>
                  <div className="fp-eyebrow">{ins.metric_label}</div>
                  <div className="mt-1 text-3xl font-bold tracking-tight text-ink">{ins.metric_value}</div>
                  {ins.delta_label && (
                    <div className="mt-1">
                      <Pill tone={DELTA_TONE[ins.delta_tone] ?? "neutral"}>{ins.delta_label}</Pill>
                    </div>
                  )}
                </div>
                {ins.chart && (
                  <div className="flex-1 max-w-[260px]">
                    <Sparkline chart={ins.chart} />
                  </div>
                )}
              </div>

              {ins.suggested_action && (
                <>
                  <div className="mt-5 fp-eyebrow flex items-center gap-1.5"><IconSparkle size={12}/> What AI suggests</div>
                  <p className="mt-1 text-sm text-body">{ins.suggested_action}</p>
                </>
              )}

              {/* Two of the four insights this page used to show were invented
                  end to end — an attrition narrative with a trend line and a
                  payroll-versus-budget percentage, neither backed by any
                  query. Naming the source on every card is what stops that
                  coming back unnoticed. */}
              {ins.evidence && (
                <p className="mt-4 text-xs text-muted">Computed from: {ins.evidence}</p>
              )}

              {ins.cta_href && (
                <div className="mt-4 pt-3 border-t border-rule">
                  <Link href={ins.cta_href} className="text-sm text-ink hover:underline flex items-center gap-1">
                    {ins.cta_label ?? "Open"} <IconArrowUpRight />
                  </Link>
                </div>
              )}
            </Surface>
          ))}
        </div>
      )}

      {(q.data?.unavailable?.length ?? 0) > 0 && (
        <Surface pad="lg">
          <div className="fp-eyebrow">What this page cannot tell you yet</div>
          <p className="mt-1 text-sm text-muted">
            These are not zero and they are not fine — they are unmeasured. Each says what it
            would take to compute.
          </p>
          <ul className="mt-3 space-y-2">
            {(q.data?.unavailable ?? []).map((u) => (
              <li key={u.topic} className="text-sm">
                <span className="font-medium text-ink">{u.topic}</span>
                <span className="text-body"> — {u.reason}</span>
                <span className="block text-xs text-muted">Needs: {u.needs}</span>
              </li>
            ))}
          </ul>
        </Surface>
      )}

      <p className="text-xs text-muted">Numbers shown are live from your HR data. Stories are generated from the same signals the agents and CPO use.</p>
    </div>
  );
}
