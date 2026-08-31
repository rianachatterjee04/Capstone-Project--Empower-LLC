"use client";
/**
 * Pay-run review — the approver screen of the payroll bridge.
 * Per-employee gross/net with diff-vs-previous, anomaly flags, and
 * approve/reject actions (payroll RBAC decides who may act: a 403 from the
 * service is surfaced inline, buttons are always visible).
 */
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { KeyValue, MetricStat, PageHeader, Pill, SectionTitle, StatusPill, Surface } from "@/components/ds";
import {
  fmtCents,
  payrollGet,
  payrollPost,
  type AnomalyFlag,
  type PayRunSummary,
  type ReviewRow,
} from "@/lib/payroll";
import { PayrollGate } from "../../PayrollGate";

type ReviewPayload = {
  run: PayRunSummary;
  review: { rows?: ReviewRow[]; total_cash_required?: string; flag_count?: number };
  anomaly_flags: AnomalyFlag[];
  agent_summary?: string | null;
};

type PaychecksPayload = {
  paychecks: Array<{
    id: string;
    employee_id: string;
    status: string;
    pay_method: string;
    gross_cents: number;
    net_cents: number;
    employee?: { id: string; name: string; email: string };
  }>;
};

export default function PayRunReviewPage() {
  const params = useParams<{ id: string }>();
  const runId = params?.id ?? "";
  const qc = useQueryClient();
  const [comment, setComment] = useState("");
  const [actionMsg, setActionMsg] = useState("");
  const [acting, setActing] = useState<"" | "approve" | "reject">("");

  const reviewQ = useQuery({
    enabled: !!runId,
    queryKey: ["payroll-run-review", runId],
    queryFn: () => payrollGet<ReviewPayload>(`runs/${runId}/review`),
  });
  const checksQ = useQuery({
    enabled: !!runId,
    queryKey: ["payroll-run-paychecks", runId],
    queryFn: () => payrollGet<PaychecksPayload>(`runs/${runId}/paychecks`),
  });

  const result = reviewQ.data ?? null;
  const run = result?.data?.run ?? null;
  const rows = result?.data?.review?.rows ?? [];
  const flags = result?.data?.anomaly_flags ?? [];
  const paychecks = checksQ.data?.data?.paychecks ?? [];
  const canAct = run ? ["draft", "submitted"].includes(run.status) : false;

  async function act(kind: "approve" | "reject") {
    setActing(kind);
    setActionMsg("");
    const res = await payrollPost<PayRunSummary>(`runs/${runId}/${kind}`, { comment: comment || null });
    if (res.data) {
      setActionMsg(kind === "approve" ? "Run approved — remittance liabilities were generated." : "Run rejected back to draft.");
    } else {
      setActionMsg(`${kind === "approve" ? "Approve" : "Reject"} failed: ${res.error}`);
    }
    setActing("");
    qc.invalidateQueries({ queryKey: ["payroll-run-review", runId] });
    qc.invalidateQueries({ queryKey: ["payroll-run-paychecks", runId] });
    qc.invalidateQueries({ queryKey: ["payroll-runs"] });
  }

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        eyebrow="Payroll · Run review"
        title={run ? `Pay run ${run.period_start} → ${run.period_end}` : "Pay run"}
        subtitle={result?.data?.agent_summary ?? "Review per-employee amounts, diffs vs the previous cycle and anomaly flags before approving."}
        actions={
          <Link
            href="/app/payroll"
            className="inline-flex h-9 items-center rounded-md border border-line bg-surface px-3 text-sm font-medium text-ink hover:bg-sunken"
          >
            ← All runs
          </Link>
        }
      />

      <PayrollGate result={result} />

      {run && (
        <>
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            <MetricStat label="Status" value={<StatusPill value={run.status} />} hint={`pay date ${run.pay_date}`} />
            <MetricStat label="Gross" value={fmtCents(run.totals?.gross_cents)} hint={`${run.totals?.employees ?? 0} employees`} />
            <MetricStat label="Net pay" value={fmtCents(run.totals?.net_cents)} />
            <MetricStat
              label="Anomaly flags"
              value={String(flags.length)}
              tone={flags.length ? "warn" : "success"}
              hint={flags.length ? "review before approving" : "clean run"}
            />
          </div>

          {flags.length > 0 && (
            <Surface>
              <SectionTitle title="Anomaly flags" description="Deterministic rules — a flagged run can never be auto-approved." />
              <ul className="mt-3 flex flex-col gap-2">
                {flags.map((f, i) => (
                  <li key={i} className="flex items-start gap-2 text-sm text-ink">
                    <Pill tone="warn">{f.code}</Pill>
                    <span>{f.message}</span>
                  </li>
                ))}
              </ul>
            </Surface>
          )}

          <Surface pad="none">
            <div className="p-5 pb-3">
              <SectionTitle title="Per-employee review" description="Diff compares net pay against the employee's previous paycheck." />
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-t border-line text-left text-xs uppercase tracking-wide text-muted">
                    <th className="px-5 py-2 font-medium">Employee</th>
                    <th className="px-5 py-2 font-medium text-right">Gross</th>
                    <th className="px-5 py-2 font-medium text-right">Net</th>
                    <th className="px-5 py-2 font-medium text-right">Diff vs prev</th>
                    <th className="px-5 py-2 font-medium">Flags</th>
                  </tr>
                </thead>
                <tbody>
                  {(rows.length
                    ? rows
                    : paychecks.map((c) => ({
                        employee_id: c.employee_id,
                        name: c.employee?.name ?? c.employee_id,
                        gross_cents: c.gross_cents,
                        net_cents: c.net_cents,
                        diff_vs_prev_cents: null as number | null,
                        diff_vs_prev_pct: null as number | null,
                      }))
                  ).map((row) => {
                    const empFlags = flags.filter((f) => f.employee_id === row.employee_id);
                    const diff = row.diff_vs_prev_cents;
                    return (
                      <tr key={row.employee_id} className="border-t border-line">
                        <td className="px-5 py-2.5 font-medium text-ink">{row.name}</td>
                        <td className="px-5 py-2.5 text-right tabular-nums">{fmtCents(row.gross_cents)}</td>
                        <td className="px-5 py-2.5 text-right tabular-nums">{fmtCents(row.net_cents)}</td>
                        <td className="px-5 py-2.5 text-right tabular-nums">
                          {diff == null ? (
                            <span className="text-muted">first check</span>
                          ) : diff === 0 ? (
                            <span className="text-muted">±$0.00</span>
                          ) : (
                            <span className={diff > 0 ? "text-success" : "text-danger"}>
                              {diff > 0 ? "+" : "−"}
                              {fmtCents(Math.abs(diff))}
                              {row.diff_vs_prev_pct != null ? ` (${row.diff_vs_prev_pct}%)` : ""}
                            </span>
                          )}
                        </td>
                        <td className="px-5 py-2.5">
                          {empFlags.length ? (
                            <div className="flex flex-wrap gap-1">
                              {empFlags.map((f, i) => (
                                <Pill key={i} tone="warn">
                                  {f.code}
                                </Pill>
                              ))}
                            </div>
                          ) : (
                            <span className="text-muted">—</span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                  {rows.length === 0 && paychecks.length === 0 && (
                    <tr className="border-t border-line">
                      <td colSpan={5} className="px-5 py-6 text-center text-sm text-muted">
                        No paychecks on this run yet (draft runs show rows after calculation; submit to build the review payload).
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </Surface>

          <Surface>
            <SectionTitle
              title="Decision"
              description="Approve locks the run and books YTD + remittance liabilities. Reject returns it to draft. Payroll RBAC and segregation-of-duties apply — the service refuses self-approval."
            />
            <div className="mt-3 flex flex-col gap-3">
              <textarea
                value={comment}
                onChange={(e) => setComment(e.target.value)}
                placeholder="Review comment (optional, audited)"
                rows={2}
                className="w-full rounded-md border border-line bg-surface p-2 text-sm text-ink"
              />
              <div className="flex items-center gap-2">
                <button
                  onClick={() => act("approve")}
                  disabled={!canAct || acting !== ""}
                  className="inline-flex h-9 items-center rounded-md bg-accent px-4 text-sm font-medium text-accent-fg hover:opacity-90 disabled:opacity-50"
                >
                  {acting === "approve" ? "Approving…" : "Approve run"}
                </button>
                <button
                  onClick={() => act("reject")}
                  disabled={!canAct || acting !== ""}
                  className="inline-flex h-9 items-center rounded-md border border-line bg-surface px-4 text-sm font-medium text-ink hover:bg-sunken disabled:opacity-50"
                >
                  {acting === "reject" ? "Rejecting…" : "Reject"}
                </button>
                {!canAct && <span className="text-xs text-muted">run is {run.status}; no review actions available</span>}
              </div>
              {actionMsg && <div className="text-sm text-ink">{actionMsg}</div>}
              <div className="grid gap-x-8 sm:grid-cols-2">
                <KeyValue label="Created by" value={run.created_by ?? "—"} />
                <KeyValue label="Submitted by" value={run.submitted_by ?? "—"} />
                <KeyValue label="Approved by" value={run.approved_by ?? "—"} />
                <KeyValue label="Cash required" value={fmtCents(run.totals?.total_cash_required_cents)} />
              </div>
            </div>
          </Surface>
        </>
      )}
    </div>
  );
}
