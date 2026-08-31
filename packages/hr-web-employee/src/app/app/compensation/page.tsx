"use client";

import { useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";
import { PageHeader, Surface, SectionTitle, Pill, Divider, EmptyState } from "@/components/ds";
import {
  fmtMoney,
  fmtNum,
  fmtDate,
  StackedBar,
  Legend,
  Skeleton,
  SERIES,
  type Segment,
} from "@/components/comp-ui";

/**
 * Mirror of GET /api/comp/total/me.
 *
 * This type used to describe an API that does not exist -- `cash.total` and a
 * top-level `total_comp`, neither of which the server has ever returned. Both
 * read as `undefined`, `undefined > 0` is false, and the page rendered "No
 * compensation on file yet" for an employee whose salary was right there in the
 * response. TypeScript could not catch it: the shape was asserted, not checked.
 * The fields below are transcribed from an actual response.
 */
type TotalComp = {
  currency: string;
  plan_year: number;
  current_fmv: number | null;
  base_salary: number;
  benefits_value: number;
  bonus: { target: number; actual: number };
  cash: {
    available: boolean;
    reason: string | null;
    base_salary: number;
    bonus_target: number;
    bonus_actual: number;
    benefits_value: number;
    as_of: string | null;
  };
  equity: {
    available: boolean;
    reason: string | null;
    annualized: number;
    vested_value: number;
    unvested_value: number;
  };
  commission: { available: boolean; reason: string | null; earned_ytd: number };
  payroll_actual: { available: boolean; reason: string | null; gross_ytd: number };
  totals: {
    target_total_comp: number;
    actual_total_comp: number;
    variance_to_target: number;
    attainment_pct: number;
    mix_pct_by_component: Record<string, number>;
  };
  cash_as_of: string | null;
  methodology: string;
};

export default function CompensationPage() {
  const [data, setData] = useState<TotalComp | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        // /api/comp/total — the cap-table module is not part of this build,
        // and the equity-scoped total-comp route went with it.
        const d = await apiFetch<TotalComp>(`/api/comp/total/me`);
        setData(d);
      } catch (e: any) {
        setError(e?.message || "Failed to load your compensation");
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  if (loading) return <LoadingState />;
  if (error)
    return (
      <Surface>
        <p className="text-sm text-danger-fg">{error}</p>
      </Surface>
    );
  if (!data) return null;

  const cash =
    (data.cash?.base_salary ?? 0) +
    (data.cash?.bonus_actual ?? 0) +
    (data.cash?.benefits_value ?? 0);
  // The cap-table module is not in this build, so the API reports equity as
  // unavailable with a reason. Showing 0 would read as "you have no equity",
  // which is a different and untrue statement — the segment is omitted instead.
  const hasEquity = Boolean(data.equity?.available);
  const equity = hasEquity ? (data.equity?.annualized ?? 0) : 0;
  const total = data.totals?.actual_total_comp ?? 0;
  const hasComp = total > 0;

  const segments: Segment[] = [
    { label: "Cash", value: cash, color: SERIES[6] },
    ...(hasEquity
      ? [{ label: "Equity (annualized)", value: equity, color: SERIES[0] }]
      : []),
  ];

  return (
    <div className="space-y-6 fp-fade-in">
      <PageHeader
        eyebrow="Workflows"
        title="My compensation"
        subtitle="Your full package in one number."
      />

      {!hasComp ? (
        <EmptyState
          title="No compensation on file yet"
          description="Once your salary and any equity are recorded, your total compensation will appear here."
        />
      ) : (
        <>
          {/* Hero total */}
          <Surface className="relative overflow-hidden" pad="lg">
            <div className="pointer-events-none absolute -right-20 -top-20 h-64 w-64 rounded-full bg-accent-soft opacity-40 blur-2xl" />
            <div className="relative">
              <div className="fp-eyebrow">Estimated total annual compensation</div>
              <div className="mt-1 text-4xl font-semibold tracking-tight text-ink tabular-nums">
                {fmtMoney(total)}
              </div>
              <p className="mt-2 max-w-2xl text-sm text-muted">
                {hasEquity ? (
                  <>
                    <span className="font-medium text-ink">{fmtMoney(cash)}</span> cash +{" "}
                    <span className="font-medium text-ink">{fmtMoney(equity)}</span> equity
                    (annualized) ={" "}
                    <span className="font-medium text-ink">{fmtMoney(total)}</span> total.
                  </>
                ) : (
                  <>
                    <span className="font-medium text-ink">{fmtMoney(cash)}</span> cash
                    compensation.
                  </>
                )}
              </p>

              <div className="mt-5">
                <StackedBar segments={segments} height={20} />
                <div className="mt-3">
                  <Legend segments={segments} />
                </div>
              </div>
            </div>
          </Surface>

          {/* Breakdown */}
          <div className="grid gap-4 lg:grid-cols-2">
            <CashPanel data={data} />
            <UnavailablePanel
              title="Equity"
              reason={data.equity?.reason}
              available={Boolean(data.equity?.available)}
            />
          </div>

          {/* Methodology */}
          <Surface inset>
            <SectionTitle title="How this is calculated" />
            <p className="mt-2 text-sm leading-relaxed text-body">{data.methodology}</p>
            {/* The equity footer stats and the "My equity" link are rendered only
                when the server can actually value equity. With the cap table out
                of this build they showed "$0" and "$0" and linked to a page that
                no longer exists -- three confident statements about an employee's
                equity, on an install that cannot compute any of them. */}
            {hasEquity && (
              <>
                <Divider className="my-4" />
                <div className="grid gap-3 sm:grid-cols-3">
                  <Foot label="Total unvested equity" value={fmtMoney(data.equity.unvested_value)} hint="Not in the annual figure above" />
                  <Foot label="Vested equity value" value={fmtMoney(data.equity.vested_value)} hint="Yours today at the 409A" />
                  <Foot
                    label="409A / share"
                    value={data.current_fmv ? fmtMoney(data.current_fmv, { cents: true }) : "—"}
                    hint="Latest fair market value"
                  />
                </div>
              </>
            )}
          </Surface>
        </>
      )}
    </div>
  );
}

function CashPanel({ data }: { data: TotalComp }) {
  return (
    <Surface>
      <SectionTitle title="Cash compensation" description={data.cash.as_of ? `Effective ${fmtDate(data.cash.as_of)}` : "Current"} />
      <div className="mt-4 space-y-2">
        <Row label="Base salary" value={fmtMoney(data.cash.base_salary)} />
        <Row label="Target bonus / variable" value={fmtMoney(data.cash.bonus_target)} />
        <Row label="Benefits" value={fmtMoney(data.cash.benefits_value)} />
        <Divider className="my-1" />
        {/* Derived from the parts the API actually returns; there is no
            `cash.total` field, and reading one produced a blank total. */}
        <Row
          label="Total cash & benefits"
          value={fmtMoney(
            (data.cash.base_salary ?? 0) + (data.cash.bonus_actual ?? 0) + (data.cash.benefits_value ?? 0),
          )}
          strong
        />
      </div>
    </Surface>
  );
}

/**
 * A pay stream the server could not compute, shown as such.
 *
 * The cap table is deliberately not part of this deployment, so equity cannot
 * be valued here. The previous version of this page rendered a grants table
 * from `equity.grants` -- a field this API does not return -- which meant an
 * employee saw an empty equity table reading "No equity grants on file". That
 * is a claim about their compensation, and it was not true; the truth is that
 * this install cannot answer the question. The server sends a reason, so show
 * the reason.
 */
function UnavailablePanel({
  title,
  reason,
  available,
}: {
  title: string;
  reason: string | null | undefined;
  available: boolean;
}) {
  return (
    <Surface>
      <SectionTitle
        title={title}
        description={available ? undefined : "Not available in this deployment"}
        trailing={<Pill>unavailable</Pill>}
      />
      <p className="mt-4 text-sm leading-relaxed text-muted">
        {reason || "This component of your compensation could not be retrieved."}
      </p>
      <p className="mt-3 text-xs text-muted">
        This is not a statement that the amount is zero — it is not known here.
      </p>
    </Surface>
  );
}

function Row({ label, value, strong }: { label: string; value: string; strong?: boolean }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <span className={`text-sm ${strong ? "font-semibold text-ink" : "text-muted"}`}>{label}</span>
      <span className={`tabular-nums ${strong ? "text-base font-semibold text-ink" : "text-sm text-ink"}`}>{value}</span>
    </div>
  );
}

function Foot({ label, value, hint }: { label: string; value: string; hint: string }) {
  return (
    <div className="rounded-lg border border-line bg-surface p-3">
      <div className="fp-eyebrow">{label}</div>
      <div className="mt-0.5 text-sm font-semibold tabular-nums text-ink">{value}</div>
      <div className="text-[11px] text-muted">{hint}</div>
    </div>
  );
}

function LoadingState() {
  return (
    <div className="space-y-6">
      <PageHeader eyebrow="Workflows" title="My compensation" subtitle="Loading…" />
      <Surface pad="lg">
        <Skeleton className="h-4 w-56" />
        <Skeleton className="mt-3 h-10 w-64" />
        <Skeleton className="mt-5 h-5 w-full" />
      </Surface>
      <div className="grid gap-4 lg:grid-cols-2">
        <Surface>
          <Skeleton className="h-4 w-40" />
          <Skeleton className="mt-4 h-24 w-full" />
        </Surface>
        <Surface>
          <Skeleton className="h-4 w-40" />
          <Skeleton className="mt-4 h-24 w-full" />
        </Surface>
      </div>
    </div>
  );
}
