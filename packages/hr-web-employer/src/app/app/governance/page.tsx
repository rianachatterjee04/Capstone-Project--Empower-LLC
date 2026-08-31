"use client";

/**
 * Governance decisions — the first UI over the HR governance seam
 * (app/api/routers/governance.py, GET /governance/pending-decisions).
 *
 * The backend normalises every pending HR workforce decision (amount-tier
 * approvals + live Workforce-Risk alerts) to one cross-domain trust contract:
 * a trust score, a recommended verdict (approve / challenge / block), an
 * exposure or qualitative impact, urgency, and a guardrail action. This page
 * surfaces that queue so leadership can see — and act on — what is awaiting
 * sign-off, ranked by risk. Read-only; each row deep-links to where the
 * decision is actually made.
 */
import { useMemo } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";

import { PageHeader, Surface, SectionTitle, Pill, MetricStat, EmptyState, Divider } from "@/components/ds";
import { IconArrowUpRight } from "@/components/icons";

type Decision = {
  id: string;
  kind: string;
  title: string;
  actor: string;
  counterparty: string;
  exposure_usd?: number | null;
  impact?: number | null;
  urgency: number;
  urgency_label: string;
  trust_score: number;
  recommended_verdict: "approve" | "challenge" | "block" | string;
  deep_link: string;
  reason: string;
  trust_context: string;
  guardrail_action: string;
  module?: string;
  /** True when the underlying risk alert is about the sample cohort. */
  is_sample?: boolean;
};

type Payload = { module: string; org_id: string; count: number; decisions: Decision[] };

const VERDICT_TONE: Record<string, "success" | "warn" | "danger" | "neutral"> = {
  approve: "success",
  challenge: "warn",
  block: "danger",
};

// The backend emits domain-relative deep links (/approvals, /comp, /equity,
// /recruiting, /investigations, /workforce/risk). Map them onto the HR app's
// actual routes.
function toAppHref(deep: string): string {
  if (!deep) return "/app";
  if (deep === "/workforce/risk") return "/app/risk";
  return `/app${deep.startsWith("/") ? deep : `/${deep}`}`;
}

function trustTone(score: number): "success" | "warn" | "danger" {
  if (score >= 55) return "success";
  if (score >= 25) return "warn";
  return "danger";
}

const money = (n: number) => new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(n);

export default function GovernancePage() {
  const q = useQuery({
    queryKey: ["governance-pending"],
    queryFn: () => apiFetch<Payload>("/governance/pending-decisions"),
    refetchInterval: 60_000,
  });
  const decisions = q.data?.decisions ?? [];

  const realDecisions = decisions.filter((d) => !d.is_sample);

  const sampleDecisions = decisions.length - realDecisions.length;


  const summary = useMemo(() => {
    const by = { approve: 0, challenge: 0, block: 0 } as Record<string, number>;
    let exposure = 0;
    for (const d of decisions) {
      by[d.recommended_verdict] = (by[d.recommended_verdict] ?? 0) + 1;
      if (typeof d.exposure_usd === "number") exposure += d.exposure_usd;
    }
    return { by, exposure };
  }, [decisions]);

  // Riskiest first: block, then challenge, then by ascending trust.
  const ordered = useMemo(() => {
    const rank: Record<string, number> = { block: 0, challenge: 1, approve: 2 };
    return [...decisions].sort(
      (a, b) => (rank[a.recommended_verdict] ?? 3) - (rank[b.recommended_verdict] ?? 3) || a.trust_score - b.trust_score,
    );
  }, [decisions]);

  return (
    <div className="space-y-7 fp-fade-in">
      <PageHeader
        eyebrow="Compliance"
        title="Governance decisions"
        subtitle="Every pending workforce decision awaiting sign-off — amount-tier approvals and live workforce-risk alerts — ranked on one trust scale. Act where the decision lives."
      />

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {/* Four of the five decisions in this queue were "Attrition risk —
            Avery Chen", "Burnout risk — Avery Chen", "Comp Equity risk — Avery
            Chen" and "Manager risk — Morgan Lee": the workforce risk engine's
            sample cohort, ranked on a trust scale and presented as awaiting
            sign-off. A decision queue counting work nobody can sign off is the
            same defect as an inbox counting drafts that do not exist. */}
        <MetricStat
          label="Pending decisions"
          value={q.isLoading ? "—" : realDecisions.length}
          hint={sampleDecisions ? `${sampleDecisions} sample also listed` : undefined}
        />
        <MetricStat label="Recommend block" value={q.isLoading ? "—" : summary.by.block ?? 0} tone={summary.by.block ? "danger" : "neutral"} />
        <MetricStat label="Recommend challenge" value={q.isLoading ? "—" : summary.by.challenge ?? 0} tone={summary.by.challenge ? "warn" : "neutral"} />
        <MetricStat label="Approval exposure" value={q.isLoading ? "—" : summary.exposure ? money(summary.exposure) : "—"} hint="sum of amount-tier approvals" />
      </div>

      <Surface pad="none">
        <div className="border-b border-line px-5 py-4 flex items-center justify-between gap-3">
          <div>
            <div className="text-md font-semibold text-ink">Decision queue</div>
            <div className="text-xs text-muted mt-0.5">Riskiest first · refreshes every 60s</div>
          </div>
          {q.isFetching && <span className="text-xs text-muted">Refreshing…</span>}
        </div>

        <div className="divide-y divide-rule">
          {q.isLoading ? (
            <div className="p-5 text-sm text-muted">Loading governance queue…</div>
          ) : q.error ? (
            <div className="p-5 text-sm text-danger-fg">Failed to load: {(q.error as Error).message}</div>
          ) : ordered.length === 0 ? (
            <div className="p-5">
              <EmptyState title="Nothing awaiting sign-off" description="No amount-tier approvals or workforce-risk alerts are currently pending." />
            </div>
          ) : (
            ordered.map((d) => (
              <div key={d.id} className="px-5 py-4">
                <div className="flex items-start justify-between gap-3 flex-wrap">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <Pill tone={VERDICT_TONE[d.recommended_verdict] ?? "neutral"}>{d.recommended_verdict}</Pill>
                      <span className="text-2xs uppercase tracking-eyebrow text-muted">{d.kind}</span>
                    </div>
                    <div className="mt-1 text-sm font-semibold text-ink">{d.title}</div>
                    <div className="text-xs text-muted mt-0.5">{d.actor} → {d.counterparty} · {d.urgency_label}</div>
                  </div>
                  <div className="text-right shrink-0">
                    <div className="fp-eyebrow">Trust</div>
                    <div className={`text-xl font-semibold tabular-nums ${
                      trustTone(d.trust_score) === "danger" ? "text-danger-fg" : trustTone(d.trust_score) === "warn" ? "text-warn-fg" : "text-ink"
                    }`}>{d.trust_score}</div>
                    <div className="text-xs text-muted tabular-nums">
                      {typeof d.exposure_usd === "number" ? money(d.exposure_usd) : typeof d.impact === "number" ? `impact ${Math.round(d.impact * 100)}%` : "—"}
                    </div>
                  </div>
                </div>

                <p className="mt-2 text-sm text-body">{d.reason}</p>

                <Divider className="my-3" />
                <div className="flex items-start justify-between gap-3 flex-wrap">
                  <div className="min-w-0 text-xs">
                    <span className="fp-eyebrow">Guardrail</span>
                    <div className="text-body mt-0.5">{d.guardrail_action}</div>
                    {d.trust_context && <div className="text-muted mt-1">{d.trust_context}</div>}
                  </div>
                  <Link
                    href={toAppHref(d.deep_link)}
                    className="group shrink-0 inline-flex items-center gap-1.5 rounded-md border border-line bg-surface px-3 py-1.5 text-sm text-body hover:text-ink hover:bg-sunken"
                  >
                    Review <IconArrowUpRight />
                  </Link>
                </div>
              </div>
            ))
          )}
        </div>
      </Surface>

      <p className="text-xs text-muted">
        Governance decisions are read from the HR governance seam and normalised to Fintra's cross-domain trust contract, so an HR
        bank-account change is ranked on the same scale as a finance bill-pay. Sign-off happens on the linked surface, under its own controls.
      </p>
    </div>
  );
}
