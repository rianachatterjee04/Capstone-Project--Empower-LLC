"use client";
import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { apiFetch, apiPost } from "@/lib/api";

import { PageHeader, Surface, SectionTitle, Pill, Action, EmptyState, MetricStat, Divider } from "@/components/ds";

type Survey = { id: string; title: string; type: string; status: string; anonymous: boolean; response_count: number };
type Driver = { category: string; mean: number | null; correlation: number | null; n: number; suppressed: boolean };
type Results = {
  survey_id: string;
  title: string;
  status: string;
  anonymous: boolean;
  response_count: number;
  participation_rate: number | null;
  overall_score: number | null;
  overall_pct: number | null;
  enps: number | null;
  drivers: Driver[];
  top_correlated_drivers?: string[];
  suppressed: boolean;
  k_anon: number;
};
type Insights = { summary: string; themes: string[]; driver_readout: string[]; source: string };

function enpsTone(v: number | null): "success" | "warn" | "danger" | "neutral" {
  if (v === null) return "neutral";
  if (v >= 30) return "success";
  if (v >= 0) return "warn";
  return "danger";
}

export default function EngagementPage() {
  const [surveyId, setSurveyId] = useState<string>("");
  const [insights, setInsights] = useState<Insights | null>(null);

  const surveysQ = useQuery({
    queryKey: ["engagement-surveys"],
    queryFn: () => apiFetch<{ items: Survey[] }>("/engagement/surveys"),
    refetchInterval: 90_000,
  });

  useEffect(() => {
    if (!surveyId && surveysQ.data?.items?.length) setSurveyId(surveysQ.data.items[0].id);
  }, [surveysQ.data, surveyId]);

  const resultsQ = useQuery({
    queryKey: ["engagement-results", surveyId],
    queryFn: () => apiFetch<Results>(`/engagement/surveys/${surveyId}/results`),
    enabled: !!surveyId,
    refetchInterval: 90_000,
  });
  const r = resultsQ.data;

  async function loadInsights() {
    if (!surveyId) return;
    const out = await apiFetch<Insights>(`/engagement/surveys/${surveyId}/insights`);
    setInsights(out);
  }

  const maxMean = Math.max(1, ...(r?.drivers ?? []).map((d) => d.mean ?? 0));

  return (
    <div className="space-y-7 fp-fade-in">
      <PageHeader
        eyebrow="Performance"
        title="Engagement"
        subtitle="eNPS and pulse surveys with deterministic driver analysis. Anonymous responses are aggregated with k-anonymity — never shown individually."
        actions={<Action variant="subtle" onClick={loadInsights}>AI insight</Action>}
      />

      {/* Survey selector */}
      <div className="flex flex-wrap gap-1.5">
        {(surveysQ.data?.items ?? []).map((s) => (
          <button
            key={s.id}
            onClick={() => { setSurveyId(s.id); setInsights(null); }}
            className={`text-xs rounded-md px-3 py-1.5 border ${
              surveyId === s.id ? "bg-accent text-accent-fg border-accent" : "bg-surface border-line text-body hover:bg-sunken"
            }`}
          >
            {s.title} · {s.status}
          </button>
        ))}
      </div>

      {resultsQ.isLoading ? (
        <Surface><EmptyState title="Loading…" /></Surface>
      ) : !r ? (
        <Surface><EmptyState title="No survey selected" /></Surface>
      ) : r.suppressed ? (
        <Surface>
          <EmptyState
            title="Results hidden"
            description={`Fewer than ${r.k_anon} responses — aggregates are suppressed to protect anonymity.`}
          />
        </Surface>
      ) : (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <MetricStat label="eNPS" value={r.enps ?? "—"} tone={enpsTone(r.enps)} hint="promoters − detractors" />
            <MetricStat label="Overall" value={r.overall_score != null ? `${r.overall_score}/5` : "—"} hint={r.overall_pct != null ? `${r.overall_pct}%` : ""} />
            <MetricStat label="Participation" value={r.participation_rate != null ? `${r.participation_rate}%` : "—"} />
            <MetricStat label="Responses" value={r.response_count} hint={r.anonymous ? "anonymous" : "attributed"} />
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
            <div className="lg:col-span-2">
              <Surface>
                <SectionTitle eyebrow="Driver analysis" title="Scores by category" description="Bar = mean (1–5). Correlation = how strongly the driver moves with the headline score." />
                <div className="mt-4 space-y-3">
                  {r.drivers.map((d) => (
                    <div key={d.category}>
                      <div className="flex items-center justify-between text-sm">
                        <span className="text-ink capitalize">{d.category}</span>
                        <span className="font-mono text-xs text-muted">
                          {d.suppressed ? "hidden (k-anon)" : `${d.mean}/5 · r=${d.correlation}`}
                        </span>
                      </div>
                      <div className="mt-1 h-2 rounded-full bg-sunken overflow-hidden">
                        <div className="h-full bg-accent" style={{ width: d.suppressed ? "0%" : `${((d.mean ?? 0) / maxMean) * 100}%` }} />
                      </div>
                    </div>
                  ))}
                </div>
                {(r.top_correlated_drivers ?? []).length > 0 && (
                  <>
                    <Divider className="my-3" />
                    <div className="flex items-center gap-2 flex-wrap text-sm">
                      <span className="text-muted">Most correlated with the headline:</span>
                      {(r.top_correlated_drivers ?? []).map((c) => <Pill key={c} tone="info">{c}</Pill>)}
                    </div>
                  </>
                )}
              </Surface>
            </div>

            <div>
              <Surface>
                <SectionTitle eyebrow="AI assist" title="Insight summary" />
                {insights ? (
                  <div className="mt-3 space-y-3">
                    <p className="text-sm text-body leading-relaxed">{insights.summary}</p>
                    {insights.themes.length > 0 && (
                      <div className="flex flex-wrap gap-1.5">
                        {insights.themes.map((t) => <Pill key={t} tone="neutral">{t}</Pill>)}
                      </div>
                    )}
                    {insights.driver_readout.length > 0 && (
                      <ul className="space-y-1 text-xs text-muted">
                        {insights.driver_readout.map((d, i) => <li key={i}>{d}</li>)}
                      </ul>
                    )}
                  </div>
                ) : (
                  <div className="mt-3 text-sm text-muted">Click “AI insight” for a plain-English readout.</div>
                )}
              </Surface>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
