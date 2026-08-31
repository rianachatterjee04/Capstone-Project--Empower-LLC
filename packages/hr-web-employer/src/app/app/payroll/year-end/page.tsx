"use client";
/**
 * Year-end filings — surfaces the built-but-unlinked payroll year-end engine
 * (packages/payroll app/services/yearend.py + reports.py):
 *   - W-2 summary        GET /api/payroll/reports/w2-summary?year=
 *   - Form 940 (FUTA)    GET /api/payroll/reports/form-940?year=
 *   - 1099-NEC forms     GET /api/payroll/reports/1099-nec?year=      (NEW)
 * all through the allow-listed /api/payroll proxy (fail-soft via PayrollGate).
 *
 * CSV "download" is built client-side from the fetched JSON because the proxy
 * re-wraps upstream bodies as JSON (it cannot stream text/csv through).
 */
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { MetricStat, PageHeader, SectionTitle, Surface, Pill, Action } from "@/components/ds";
import { fmtCents, payrollGet, type PayrollResult } from "@/lib/payroll";
import { PayrollGate } from "../PayrollGate";

const TABS = ["1099-NEC", "W-2 summary", "Form 940"] as const;
type Tab = (typeof TABS)[number];

type NecForm = {
  recipient_id: string;
  recipient_name: string;
  recipient_tin_masked: string;
  box1_nonemployee_comp_cents: number;
  box1_nonemployee_comp: string;
  box6_state: string;
  filing_required: boolean;
};
type NecPayload = {
  year: number;
  forms: NecForm[];
  totals: {
    recipients: number;
    forms_required: number;
    total_nonemployee_comp_cents: number;
    total_nonemployee_comp: string;
    filing_threshold_cents: number;
  };
};
type W2Row = {
  employee_id: string;
  name: string;
  ssn_masked: string;
  box1_wages_cents: number;
  box2_fit_withheld_cents: number;
  box3_ss_wages_cents: number;
  box5_medicare_wages_cents: number;
};
type W2Payload = { report: string; rows: W2Row[] };
type Form940 = {
  year: number;
  line3_total_payments_cents: number;
  line7_taxable_futa_wages_cents: number;
  line8_futa_tax_cents: number;
  deposited_cents: number;
  balance_due_cents: number;
  note: string;
};

function downloadCsv(filename: string, rows: Record<string, unknown>[]) {
  if (!rows.length) return;
  const headers = Object.keys(rows[0]);
  const esc = (v: unknown) => {
    const s = v == null ? "" : String(v);
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  const csv = [headers.join(","), ...rows.map((r) => headers.map((h) => esc(r[h])).join(","))].join("\n");
  const blob = new Blob([csv], { type: "text/csv" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export default function YearEndPage() {
  const [tab, setTab] = useState<Tab>("1099-NEC");
  const nowYear = new Date().getFullYear();
  const [year, setYear] = useState(nowYear - 1);

  const necQ = useQuery({
    queryKey: ["yearend-1099", year],
    queryFn: () => payrollGet<NecPayload>(`reports/1099-nec?year=${year}`),
    enabled: tab === "1099-NEC",
  });
  const w2Q = useQuery({
    queryKey: ["yearend-w2", year],
    queryFn: () => payrollGet<W2Payload>(`reports/w2-summary?year=${year}`),
    enabled: tab === "W-2 summary",
  });
  const f940Q = useQuery({
    queryKey: ["yearend-940", year],
    queryFn: () => payrollGet<Form940>(`reports/form-940?year=${year}`),
    enabled: tab === "Form 940",
  });

  const active: PayrollResult<unknown> | null =
    tab === "1099-NEC" ? necQ.data ?? null : tab === "W-2 summary" ? w2Q.data ?? null : f940Q.data ?? null;

  const years = [nowYear, nowYear - 1, nowYear - 2, nowYear - 3];

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        eyebrow="Payroll · Compliance"
        title="Year-end filings"
        subtitle="W-2 wage summaries, Form 940 (annual FUTA), and 1099-NEC contractor forms — generated straight from live payroll data."
        actions={
          <label className="text-xs text-muted">
            Tax year{" "}
            <select
              value={year}
              onChange={(e) => setYear(parseInt(e.target.value, 10))}
              className="ml-1 rounded border border-line bg-transparent px-2 py-1 text-sm"
            >
              {years.map((y) => (
                <option key={y} value={y}>
                  {y}
                </option>
              ))}
            </select>
          </label>
        }
      />

      <div className="flex flex-wrap gap-2">
        {TABS.map((t) => (
          <Action key={t} variant={t === tab ? "primary" : "subtle"} size="sm" onClick={() => setTab(t)}>
            {t}
          </Action>
        ))}
      </div>

      <PayrollGate result={active} />

      {tab === "1099-NEC" && necQ.data?.data && <NecView data={necQ.data.data} year={year} />}
      {tab === "W-2 summary" && w2Q.data?.data && <W2View data={w2Q.data.data} year={year} />}
      {tab === "Form 940" && f940Q.data?.data && <Form940View data={f940Q.data.data} />}
    </div>
  );
}

function NecView({ data, year }: { data: NecPayload; year: number }) {
  const { totals, forms } = data;
  return (
    <>
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <MetricStat label="Recipients" value={String(totals.recipients)} />
        <MetricStat label="Forms to file" value={String(totals.forms_required)} hint={`≥ ${fmtCents(totals.filing_threshold_cents)} threshold`} />
        <MetricStat label="Total 1099 pay" value={fmtCents(totals.total_nonemployee_comp_cents)} tone="accent" />
        <MetricStat label="Tax year" value={String(year)} />
      </div>
      <Surface pad="none">
        <div className="flex items-center justify-between p-5 pb-3">
          <SectionTitle title="1099-NEC forms" description="One form per contractor; box 1 is total nonemployee compensation." />
          <Action size="sm" onClick={() => downloadCsv(`1099-nec-${year}.csv`, forms as unknown as Record<string, unknown>[])}>
            Download CSV
          </Action>
        </div>
        {forms.length === 0 ? (
          <div className="px-5 pb-6 text-sm text-muted">No contractor payments recorded for {year}.</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-t border-line text-left text-xs uppercase tracking-wide text-muted">
                  <th className="px-5 py-2 font-medium">Recipient</th>
                  <th className="px-5 py-2 font-medium">TIN</th>
                  <th className="px-5 py-2 font-medium">State</th>
                  <th className="px-5 py-2 font-medium text-right">Box 1 (NEC)</th>
                  <th className="px-5 py-2 font-medium text-right">Filing</th>
                </tr>
              </thead>
              <tbody>
                {forms.map((f) => (
                  <tr key={f.recipient_id} className="border-t border-line hover:bg-sunken">
                    <td className="px-5 py-2.5 font-medium text-ink">{f.recipient_name}</td>
                    <td className="px-5 py-2.5 tabular-nums text-muted">{f.recipient_tin_masked || "—"}</td>
                    <td className="px-5 py-2.5 text-muted">{f.box6_state || "—"}</td>
                    <td className="px-5 py-2.5 text-right tabular-nums">{fmtCents(f.box1_nonemployee_comp_cents)}</td>
                    <td className="px-5 py-2.5 text-right">
                      <Pill tone={f.filing_required ? "accent" : "neutral"}>{f.filing_required ? "required" : "under $600"}</Pill>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Surface>
    </>
  );
}

function W2View({ data, year }: { data: W2Payload; year: number }) {
  const rows = data.rows ?? [];
  return (
    <Surface pad="none">
      <div className="flex items-center justify-between p-5 pb-3">
        <SectionTitle title="W-2 wage & tax summary" description="Box 1/2/3/5 per employee, computed from YTD accumulators." />
        <Action size="sm" onClick={() => downloadCsv(`w2-summary-${year}.csv`, rows as unknown as Record<string, unknown>[])}>
          Download CSV
        </Action>
      </div>
      {rows.length === 0 ? (
        <div className="px-5 pb-6 text-sm text-muted">No W-2 data for {year}. Process at least one payroll run first.</div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-t border-line text-left text-xs uppercase tracking-wide text-muted">
                <th className="px-5 py-2 font-medium">Employee</th>
                <th className="px-5 py-2 font-medium">SSN</th>
                <th className="px-5 py-2 font-medium text-right">Box 1 wages</th>
                <th className="px-5 py-2 font-medium text-right">Box 2 FIT</th>
                <th className="px-5 py-2 font-medium text-right">Box 3 SS wages</th>
                <th className="px-5 py-2 font-medium text-right">Box 5 Medicare</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.employee_id} className="border-t border-line hover:bg-sunken">
                  <td className="px-5 py-2.5 font-medium text-ink">{r.name}</td>
                  <td className="px-5 py-2.5 tabular-nums text-muted">{r.ssn_masked || "—"}</td>
                  <td className="px-5 py-2.5 text-right tabular-nums">{fmtCents(r.box1_wages_cents)}</td>
                  <td className="px-5 py-2.5 text-right tabular-nums">{fmtCents(r.box2_fit_withheld_cents)}</td>
                  <td className="px-5 py-2.5 text-right tabular-nums">{fmtCents(r.box3_ss_wages_cents)}</td>
                  <td className="px-5 py-2.5 text-right tabular-nums">{fmtCents(r.box5_medicare_wages_cents)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Surface>
  );
}

function Form940View({ data }: { data: Form940 }) {
  return (
    <div className="flex flex-col gap-4">
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <MetricStat label="Total payments" value={fmtCents(data.line3_total_payments_cents)} />
        <MetricStat label="Taxable FUTA wages" value={fmtCents(data.line7_taxable_futa_wages_cents)} hint="capped at $7,000/employee" />
        <MetricStat label="FUTA tax (line 8)" value={fmtCents(data.line8_futa_tax_cents)} tone="accent" />
        <MetricStat label="Balance due" value={fmtCents(data.balance_due_cents)} hint={`deposited ${fmtCents(data.deposited_cents)}`} />
      </div>
      <Surface>
        <SectionTitle title="Form 940 — annual FUTA" description={data.note} />
      </Surface>
    </div>
  );
}
