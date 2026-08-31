"use client";
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch, apiPost } from "@/lib/api";

import { PageHeader, Surface, SectionTitle, Pill, Action, EmptyState, Divider } from "@/components/ds";

type Question = { id: string; prompt: string; scale_label: string; helper: string };
type Cycle = { id: string; label: string; opened_at: string; closed_at?: string | null; n_submissions: number; averages: Record<string, number>; sentiment_score: number };
type Pulse = {
  questions: Question[];
  open_cycle: Cycle;
  history: Cycle[];
  summary: {
    current_sentiment_pct: number;
    delta: number;
    trend: { series: number[]; labels: string[]; suffix: string };
    total_submissions: number;
  };
};

function TrendChart({ series, labels }: { series: number[]; labels: string[] }) {
  if (series.length === 0) return null;
  const max = Math.max(...series);
  const min = Math.min(...series);
  const range = max - min || 1;
  const w = 320, h = 56, step = series.length > 1 ? w / (series.length - 1) : 0;
  const points = series.map((v, i) => {
    const x = i * step;
    const y = h - ((v - min) / range) * (h - 8) - 4;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });
  const dPath = `M ${points.join(" L ")}`;
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="w-full h-14">
      <path d={`${dPath} L ${w},${h} L 0,${h} Z`} fill="rgba(15,118,110,0.08)" />
      <path d={dPath} fill="none" stroke="#0F766E" strokeWidth="1.4" />
      {series.map((v, i) => (
        <circle key={i} cx={(i * step).toFixed(1)} cy={(h - ((v - min) / range) * (h - 8) - 4).toFixed(1)} r="1.8" fill="#0F766E" />
      ))}
    </svg>
  );
}

export default function PulsePage() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["pulse"], queryFn: () => apiFetch<Pulse>("/wellness"), refetchInterval: 90_000 });
  const data = q.data;

  const [answers, setAnswers] = useState<Record<string, number>>({});
  const [comment, setComment] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);

  async function submit() {
    if (Object.keys(answers).length === 0) return;
    setSubmitting(true);
    try {
      await apiPost("/wellness/submit", { answers, comment });
      setSubmitted(true);
      setAnswers({});
      setComment("");
      await qc.invalidateQueries({ queryKey: ["pulse"] });
    } finally {
      setSubmitting(false);
    }
  }

  const sentimentTone: "success" | "warn" | "danger" =
    (data?.summary.current_sentiment_pct ?? 0) >= 75 ? "success"
    : (data?.summary.current_sentiment_pct ?? 0) >= 60 ? "warn"
    : "danger";

  return (
    <div className="space-y-7 fp-fade-in">
      <PageHeader
        eyebrow="Culture"
        title="Engagement pulse"
        subtitle="A 60-second weekly check-in. Anonymous, aggregated, trended over time. Your responses inform how leadership operates."
      />

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Stat label="Current sentiment" value={`${data?.summary.current_sentiment_pct ?? "—"}%`} tone={sentimentTone} />
        <Stat label="Δ vs. prior" value={data ? `${data.summary.delta > 0 ? "+" : ""}${(data.summary.delta * 100).toFixed(1)}%` : "—"} />
        <Stat label="This cycle" value={data?.open_cycle.label ?? "—"} />
        <Stat label="Submissions" value={data?.summary.total_submissions ?? "—"} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        {/* Submit */}
        <Surface className="lg:col-span-2">
          <SectionTitle
            eyebrow={data?.open_cycle.label ?? "This week"}
            title="Your pulse"
            description="Five short prompts. 1 = strongly disagree, 5 = strongly agree. Results are anonymous and aggregated."
          />

          {submitted ? (
            <div className="mt-4 rounded-md border border-success-line bg-success-bg text-success-fg px-4 py-3 text-sm">
              ✓ Thanks. Your response is in. The trend updates each Friday.
            </div>
          ) : (
            <ul className="mt-4 space-y-4">
              {(data?.questions ?? []).map((q) => (
                <li key={q.id} className="rounded-md border border-line bg-canvas p-3">
                  <div className="text-sm font-medium text-ink">{q.prompt}</div>
                  {q.helper && <div className="text-xs text-muted mt-0.5">{q.helper}</div>}
                  <div className="mt-2 flex items-center gap-1.5">
                    {[1, 2, 3, 4, 5].map((n) => {
                      const active = answers[q.id] === n;
                      return (
                        <button
                          key={n}
                          onClick={() => setAnswers((a) => ({ ...a, [q.id]: n }))}
                          className={`h-9 w-9 rounded-md border text-sm font-semibold transition-colors duration-150 ease-calm ${
                            active ? "bg-accent text-accent-fg border-accent" : "bg-surface border-line text-body hover:bg-sunken"
                          }`}
                        >
                          {n}
                        </button>
                      );
                    })}
                    <div className="ml-3 text-2xs uppercase tracking-eyebrow text-muted">{q.scale_label}</div>
                  </div>
                </li>
              ))}
            </ul>
          )}

          {!submitted && (
            <>
              <div className="mt-4">
                <div className="fp-eyebrow mb-1">Anonymous comment (optional)</div>
                <textarea
                  value={comment}
                  onChange={(e) => setComment(e.target.value)}
                  rows={3}
                  placeholder="Anything else leadership should know — kept anonymous."
                  className="w-full rounded-md border border-line bg-canvas px-3 py-2 text-sm text-ink outline-none focus:bg-surface"
                />
              </div>
              <div className="mt-3 flex items-center gap-2">
                <Action variant="primary" onClick={submit} disabled={Object.keys(answers).length === 0 || submitting}>
                  {submitting ? "Submitting…" : "Submit pulse"}
                </Action>
                <span className="text-xs text-muted">{Object.keys(answers).length} / {(data?.questions ?? []).length} answered</span>
              </div>
            </>
          )}
        </Surface>

        {/* Trend + history */}
        <Surface>
          <SectionTitle eyebrow="Trend" title="Sentiment over time" />
          {data?.summary.trend.series.length ? (
            <>
              <div className="mt-3"><TrendChart series={data.summary.trend.series} labels={data.summary.trend.labels} /></div>
              <div className="mt-2 flex items-center justify-between text-2xs uppercase tracking-eyebrow text-muted">
                <span>{data.summary.trend.labels[0]}</span>
                <span>{data.summary.trend.labels.at(-1)}</span>
              </div>
            </>
          ) : (
            <EmptyState title="No trend yet" />
          )}

          <Divider className="my-4" />

          <div className="fp-eyebrow mb-2">Past cycles</div>
          <ul className="space-y-1">
            {(data?.history ?? []).slice().reverse().slice(0, 6).map((c) => (
              <li key={c.id} className="flex items-center justify-between text-sm">
                <span className="text-body">{c.label}</span>
                <span className="text-muted tabular-nums">{Math.round(c.sentiment_score * 100)}%</span>
              </li>
            ))}
            {(data?.history ?? []).length === 0 && <div className="text-sm text-muted">—</div>}
          </ul>
        </Surface>
      </div>

      <p className="text-xs text-muted">Pulse results are aggregated — no individual scores or comments are visible to managers or HR.</p>
    </div>
  );
}

function Stat({ label, value, tone = "neutral" }: { label: string; value: React.ReactNode; tone?: "neutral" | "success" | "warn" | "danger" }) {
  const ring: Record<string, string> = {
    neutral: "",
    success: "ring-1 ring-success-line",
    warn: "ring-1 ring-warn-line",
    danger: "ring-1 ring-danger-line",
  };
  return (
    <div className={`rounded-md border border-line bg-surface p-4 ${ring[tone]}`}>
      <div className="fp-eyebrow">{label}</div>
      <div className="mt-1 text-xl font-semibold tracking-tight text-ink truncate">{value}</div>
    </div>
  );
}
