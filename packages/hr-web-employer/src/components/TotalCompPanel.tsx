"use client";
import { useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";
import { Surface, SectionTitle, Pill, KeyValue, Divider } from "@/components/ds";

// ---------------------------------------------------------------------------
// Types — mirror packages/hr-api GET /comp/total/{employee_id}
// ---------------------------------------------------------------------------
type Component = { available: boolean; reason?: string | null };

export type TotalComp = {
  employee_id: string | null;
  plan_year: number;
  currency: string;
  current_fmv: number | null;
  base_salary: number;
  bonus: { target: number; actual: number };
  benefits_value: number;
  /** Present since the API learned to distinguish "no record" from "zero". */
  cash?: { available: boolean; reason?: string | null; as_of?: string | null };
  commission: Component & { earned_ytd: number; accrued_pending: number; plan_target: number };
  payroll_actual: Component & { source: string; gross_ytd: number };
  equity: Component & {
    grant_value: number; vested_value: number; unvested_value: number; annualized: number;
  };
  totals: {
    target_total_comp: number;
    actual_total_comp: number;
    variance_to_target: number;
    attainment_pct: number | null;
    mix_pct_by_component: Record<string, number>;
  };
  cash_as_of: string | null;
};

function currency(n: number, ccy = "USD") {
  return new Intl.NumberFormat("en-US", {
    style: "currency", currency: ccy, maximumFractionDigits: 0,
  }).format(n || 0);
}

// Stable, calm colors per component (no rainbow) — CSS design tokens.
const MIX_ORDER = ["base_salary", "bonus", "benefits", "commission", "equity"] as const;
const MIX_LABEL: Record<string, string> = {
  base_salary: "Base salary",
  bonus: "Bonus",
  benefits: "Benefits",
  commission: "Commission",
  equity: "Equity",
};
const MIX_BAR: Record<string, string> = {
  base_salary: "bg-[var(--ink,#111)]",
  bonus: "bg-info-fg",
  benefits: "bg-success-fg",
  commission: "bg-warn-fg",
  equity: "bg-[var(--brand,#6366f1)]",
};

// ---------------------------------------------------------------------------
// Panel
// ---------------------------------------------------------------------------
export function TotalCompPanel({
  employeeId,
  planYear,
}: {
  employeeId: string;
  planYear?: number;
}) {
  const [data, setData] = useState<TotalComp | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const year = planYear ?? new Date().getFullYear();

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError(null);
    apiFetch<TotalComp>(`/comp/total/${employeeId}?plan_year=${year}`)
      .then((d) => alive && setData(d))
      .catch((e) => alive && setError(e?.message ?? "Failed to load total comp"))
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, [employeeId, year]);

  if (loading) {
    return (
      <Surface>
        <SectionTitle eyebrow="Total compensation" title="Loading…" />
      </Surface>
    );
  }
  if (error) {
    return (
      <Surface>
        <SectionTitle eyebrow="Total compensation" title="Unavailable" />
        <p className="mt-2 text-sm text-danger-fg">{error}</p>
      </Surface>
    );
  }
  if (!data) return null;

  const mix = data.totals.mix_pct_by_component;
  const ccy = data.currency;
  // A payload from before the API distinguished them has no cash block;
  // treat that as available so an older server does not blank the rows.
  const cashAvailable = data.cash?.available ?? true;
  // Every stream unavailable means the totals below are a sum over nothing.
  const nothingMeasured =
    !cashAvailable &&
    !data.commission.available &&
    !data.payroll_actual.available &&
    !data.equity.available;

  return (
    <Surface>
      <SectionTitle
        eyebrow="Total compensation"
        title={`Every pay stream, ${data.plan_year}`}
        description="Base + bonus + benefits + commission + payroll actuals + equity, aggregated from each source."
        trailing={
          data.totals.attainment_pct != null ? (
            <Pill tone={data.totals.attainment_pct >= 100 ? "success" : "neutral"}>
              {data.totals.attainment_pct.toFixed(1)}% of target
            </Pill>
          ) : null
        }
      />

      {/* Target vs actual headline.

          When every component below reads "unavailable", these two totalled
          them to $0 and printed it in the largest type on the panel. Nothing
          was measured; a sum of nothing is not zero compensation. */}
      <div className="mt-4 grid grid-cols-1 md:grid-cols-2 gap-3">
        <div className="rounded-lg border border-line bg-surface p-4">
          <div className="fp-eyebrow">Target total comp</div>
          <div className="mt-1 text-2xl font-semibold tracking-tight tabular-nums text-ink">
            {nothingMeasured ? "Not on file" : currency(data.totals.target_total_comp, ccy)}
          </div>
          {nothingMeasured && (
            <div className="text-xs text-muted">
              no pay stream is connected for this employee
            </div>
          )}
        </div>
        <div className="rounded-lg border border-success-line ring-1 ring-success-line bg-surface p-4">
          <div className="fp-eyebrow">Actual (tracking)</div>
          <div className="mt-1 text-2xl font-semibold tracking-tight tabular-nums text-success-fg">
            {nothingMeasured ? "Not on file" : currency(data.totals.actual_total_comp, ccy)}
          </div>
          <div className="text-xs text-muted" hidden={nothingMeasured}>
            {data.totals.variance_to_target >= 0 ? "+" : ""}
            {currency(data.totals.variance_to_target, ccy)} vs target
          </div>
        </div>
      </div>

      {/* Stacked component mix bar */}
      {Object.keys(mix).length > 0 && (
        <div className="mt-5">
          <div className="fp-eyebrow mb-1.5">Pay mix</div>
          <div className="flex h-4 w-full overflow-hidden rounded-full border border-line">
            {MIX_ORDER.filter((k) => mix[k]).map((k) => (
              <div
                key={k}
                className={MIX_BAR[k]}
                style={{ width: `${mix[k]}%` }}
                title={`${MIX_LABEL[k]} — ${mix[k]}%`}
              />
            ))}
          </div>
          <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-2xs text-muted">
            {MIX_ORDER.filter((k) => mix[k]).map((k) => (
              <span key={k} className="inline-flex items-center gap-1.5">
                <span className={`inline-block h-2 w-2 rounded-full ${MIX_BAR[k]}`} />
                {MIX_LABEL[k]} {mix[k]}%
              </span>
            ))}
          </div>
        </div>
      )}

      <Divider className="my-4" />

      {/* Component rows */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-x-8">
        <div>
          {/* Commission, payroll and equity said "unavailable — <reason>" while
              these three showed $0 for an employee with no comp record at all.
              Three honest lines beside three that quietly assert a salary is
              worse than either on its own. Same row component, same rule. */}
          <ComponentRow
            label="Base salary"
            available={cashAvailable}
            reason={data.cash?.reason}
            value={currency(data.base_salary, ccy)}
          />
          <ComponentRow
            label="Bonus (target / actual)"
            available={cashAvailable}
            reason={data.cash?.reason}
            value={`${currency(data.bonus.target, ccy)} / ${currency(data.bonus.actual, ccy)}`}
          />
          <ComponentRow
            label="Benefits"
            available={cashAvailable}
            reason={data.cash?.reason}
            value={currency(data.benefits_value, ccy)}
          />
        </div>
        <div>
          <ComponentRow
            label="Commission"
            available={data.commission.available}
            reason={data.commission.reason}
            value={
              <>
                {currency(data.commission.earned_ytd, ccy)} earned
                <span className="text-muted">
                  {" · "}
                  {currency(data.commission.accrued_pending, ccy)} pending
                </span>
              </>
            }
          />
          <ComponentRow
            label="Payroll actual (gross YTD)"
            available={data.payroll_actual.available}
            reason={data.payroll_actual.reason}
            value={currency(data.payroll_actual.gross_ytd, ccy)}
          />
          <ComponentRow
            label="Equity (annualized)"
            available={data.equity.available}
            reason={data.equity.reason}
            value={
              <>
                {currency(data.equity.annualized, ccy)}
                <span className="text-muted">
                  {" · "}vested {currency(data.equity.vested_value, ccy)}
                  {" · "}unvested {currency(data.equity.unvested_value, ccy)}
                </span>
              </>
            }
          />
        </div>
      </div>

      <p className="mt-4 text-2xs text-muted italic">
        Payroll gross YTD is shown for reconciliation and is not re-added to the actual
        total (it already contains paid base, bonus and commission). Equity value is an
        estimate at the latest 409A fair market value and is not guaranteed.
      </p>
    </Surface>
  );
}

function ComponentRow({
  label,
  available,
  reason,
  value,
}: {
  label: string;
  available: boolean;
  reason?: string | null;
  value: React.ReactNode;
}) {
  if (!available) {
    return (
      <div className="flex items-baseline justify-between gap-3 py-1.5 border-b border-line/60 last:border-0">
        <span className="text-sm text-muted">{label}</span>
        <span className="text-xs text-faint italic text-right">
          unavailable — {reason || "source not connected"}
        </span>
      </div>
    );
  }
  return (
    <div className="flex items-baseline justify-between gap-3 py-1.5 border-b border-line/60 last:border-0">
      <span className="text-sm text-body">{label}</span>
      <span className="text-sm tabular-nums text-ink text-right">{value}</span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Team roll-up (GET /comp/total)
// ---------------------------------------------------------------------------
type RollUp = {
  plan_year: number;
  count: number;
  roll_up: {
    target_total_comp: number;
    actual_total_comp: number;
    variance_to_target: number;
  };
  employees: TotalComp[];
};

export function TotalCompRollUp({ planYear }: { planYear?: number }) {
  const [data, setData] = useState<RollUp | null>(null);
  const [error, setError] = useState<string | null>(null);
  const year = planYear ?? new Date().getFullYear();

  useEffect(() => {
    let alive = true;
    apiFetch<RollUp>(`/comp/total?plan_year=${year}`)
      .then((d) => alive && setData(d))
      .catch((e) => alive && setError(e?.message ?? "Failed to load roster"));
    return () => {
      alive = false;
    };
  }, [year]);

  if (error) {
    return (
      <Surface>
        <SectionTitle eyebrow="Team" title="Total comp roll-up" />
        <p className="mt-2 text-sm text-danger-fg">{error}</p>
      </Surface>
    );
  }
  if (!data) return null;

  return (
    <Surface>
      <SectionTitle
        eyebrow="Team"
        title="Total comp roll-up"
        description={`${data.count} employees · plan year ${data.plan_year}`}
      />
      <div className="mt-4 grid grid-cols-1 md:grid-cols-3 gap-3">
        <KeyValue label="Target total" value={currency(data.roll_up.target_total_comp)} />
        <KeyValue label="Actual total" value={currency(data.roll_up.actual_total_comp)} />
        <KeyValue
          label="Variance"
          value={`${data.roll_up.variance_to_target >= 0 ? "+" : ""}${currency(
            data.roll_up.variance_to_target
          )}`}
        />
      </div>
    </Surface>
  );
}
