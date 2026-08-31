"use client";
import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";
import { PageHeader, Surface, SectionTitle, MetricStat, StatusPill, EmptyState } from "@/components/ds";

type Review = {
  id: string;
  employee_id: string;
  cycle: string;
  status: string;
  ai_decision?: string | null;
};

type KeyResult = { id: string; title: string; progress?: number };
type Objective = { id: string; title: string; status?: string; progress?: number; key_results?: KeyResult[] };

type Tone = "neutral" | "success" | "warn" | "danger" | "info" | "accent";

function statusTone(status: string): Tone {
  switch (status) {
    case "finalized": return "success";
    case "calibration": return "info";
    case "decision": return "accent";
    case "manager_review":
    case "manager_submitted": return "warn";
    default: return "neutral"; // draft, etc.
  }
}

export default function PerformancePage() {
  // Canonical review contract: GET /reviews → { reviews: [...] } (the same
  // contract the employer app consumes). Replaces the older /performance/reviews.
  const reviewsQ = useQuery({
    queryKey: ["reviews"],
    queryFn: () => apiFetch<{ reviews: Review[] }>("/reviews"),
  });

  // Fail-soft: goals are optional; if the endpoint isn't populated the section
  // simply doesn't render.
  const goalsQ = useQuery({
    queryKey: ["my-goals"],
    queryFn: () => apiFetch<Objective[]>("/goals"),
    retry: false,
  });
  const goals = Array.isArray(goalsQ.data) ? goalsQ.data : [];

  const reviews = reviewsQ.data?.reviews ?? [];
  const finalized = reviews.filter((r) => r.status === "finalized").length;
  const pending = reviews.filter((r) => r.status !== "finalized").length;

  return (
    <div className="space-y-7 fp-fade-in">
      <PageHeader
        eyebrow="Growth"
        title="My reviews & goals"
        subtitle="Your performance review history and your current goals / OKRs."
      />

      {goals.length > 0 && (
        <Surface pad="none">
          <div className="border-b border-line px-5 py-4">
            <div className="text-md font-semibold text-ink">My goals & OKRs</div>
            <div className="text-xs text-muted mt-0.5">{goals.length} objective{goals.length === 1 ? "" : "s"}</div>
          </div>
          <div className="divide-y divide-rule">
            {goals.map((o) => (
              <div key={o.id} className="px-5 py-3">
                <div className="flex items-center justify-between gap-3">
                  <div className="text-sm font-medium text-ink">{o.title}</div>
                  {typeof o.progress === "number" && (
                    <span className="text-xs font-medium text-muted tabular-nums">{Math.round(o.progress)}%</span>
                  )}
                </div>
                {typeof o.progress === "number" && (
                  <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-sunken">
                    <div className="h-full rounded-full bg-accent" style={{ width: `${Math.max(0, Math.min(100, o.progress))}%` }} />
                  </div>
                )}
                {o.key_results && o.key_results.length > 0 && (
                  <ul className="mt-2 space-y-1">
                    {o.key_results.map((kr) => (
                      <li key={kr.id} className="flex items-center justify-between text-xs text-muted">
                        <span>{kr.title}</span>
                        {typeof kr.progress === "number" && <span className="tabular-nums">{Math.round(kr.progress)}%</span>}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            ))}
          </div>
        </Surface>
      )}

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <MetricStat label="Total reviews" value={reviewsQ.isLoading ? "—" : reviews.length} />
        <MetricStat label="Finalized" value={reviewsQ.isLoading ? "—" : finalized} tone="success" />
        <MetricStat label="Pending" value={reviewsQ.isLoading ? "—" : pending} tone={pending ? "warn" : "neutral"} />
      </div>

      <Surface pad="none">
        <div className="border-b border-line px-5 py-4">
          <div className="text-md font-semibold text-ink">Review history</div>
          <div className="text-xs text-muted mt-0.5">{reviews.length} total</div>
        </div>
        <div className="divide-y divide-rule">
          {reviewsQ.isLoading && <div className="p-5 text-sm text-muted">Loading reviews…</div>}
          {reviewsQ.error && <div className="p-5 text-sm text-danger-fg">Failed to load reviews</div>}
          {!reviewsQ.isLoading && reviews.length === 0 && (
            <div className="p-5">
              <EmptyState
                title="No performance reviews yet"
                description="Reviews will appear here when your manager initiates a review cycle."
              />
            </div>
          )}
          {reviews.map((r) => (
            <div key={r.id} className="flex items-center justify-between px-5 py-3 hover:bg-sunken/60 transition-colors duration-150 ease-calm">
              <div>
                <div className="text-sm font-medium text-ink">Cycle: {r.cycle}</div>
                <div className="text-xs text-muted">{r.ai_decision ? `AI decision: ${r.ai_decision}` : "Pending review"}</div>
              </div>
              <StatusPill value={r.status.replace(/_/g, " ")} tone={statusTone(r.status)} />
            </div>
          ))}
        </div>
      </Surface>

      <Surface>
        <SectionTitle title="Next review cycle" />
        <div className="mt-3 rounded-md bg-canvas border border-line p-4 text-sm text-muted text-center">
          Your manager will notify you when the next review cycle opens.
        </div>
      </Surface>
    </div>
  );
}
