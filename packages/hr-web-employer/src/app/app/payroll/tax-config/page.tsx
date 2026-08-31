"use client";
/**
 * Tax configuration & versioned rates — surfaces the built-but-unlinked
 * payroll tax-config engine (packages/payroll app/api/routers/tax_config.py):
 *   - GET /api/payroll/tax-rates?year=      (versioned constants + brackets)
 *   - GET /api/payroll/org-tax-config       (SUTA rate, deposit schedule)
 * through the allow-listed /api/payroll proxy (fail-soft, read-only).
 */
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { MetricStat, PageHeader, SectionTitle, Surface, Pill } from "@/components/ds";
import { payrollGet } from "@/lib/payroll";
import { PayrollGate } from "../PayrollGate";

type Constant = { key: string; value: string; unit: string; source: string; verified: boolean };
type Bracket = {
  jurisdiction: string;
  level: string;
  schedule: string;
  filing_status: string;
  min_cents: number;
  max_cents: number | null;
  rate: string;
  verified: boolean;
  source: string;
};
type TaxRates = { rate_year: number; constants: Constant[]; brackets: Bracket[] };

function money(cents: number | null): string {
  if (cents == null) return "—";
  return (cents / 100).toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });
}

export default function TaxConfigPage() {
  const nowYear = new Date().getFullYear();
  const [year, setYear] = useState(nowYear);

  const ratesQ = useQuery({
    queryKey: ["payroll-tax-rates", year],
    queryFn: () => payrollGet<TaxRates>(`tax-rates?year=${year}`),
  });

  const result = ratesQ.data ?? null;
  const rates = result?.data ?? null;
  const constants = rates?.constants ?? [];
  const brackets = rates?.brackets ?? [];
  const unverified = [...constants, ...brackets].filter((r) => !r.verified).length;
  const years = [nowYear + 1, nowYear, nowYear - 1];

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        eyebrow="Payroll · Configuration"
        title="Tax rates & configuration"
        subtitle="The versioned, source-attributed tax tables the payroll engine uses — federal constants, state/local brackets, and their verification status."
        actions={
          <label className="text-xs text-muted">
            Rate year{" "}
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

      <PayrollGate result={result} />

      {rates && (
        <>
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-3">
            <MetricStat label="Rate year" value={String(rates.rate_year)} />
            <MetricStat label="Constants + brackets" value={String(constants.length + brackets.length)} />
            <MetricStat
              label="Unverified rows"
              value={String(unverified)}
              tone={unverified ? "warn" : "success"}
              hint={unverified ? "require CPA sign-off" : "all verified"}
            />
          </div>

          <Surface pad="none">
            <div className="p-5 pb-3">
              <SectionTitle title="Federal & FICA constants" description="Rates and wage bases, with the reviewed source each was seeded from." />
            </div>
            {constants.length === 0 ? (
              <div className="px-5 pb-6 text-sm text-muted">No constants seeded for {year}. An owner can refresh rates from the reviewed data files.</div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-t border-line text-left text-xs uppercase tracking-wide text-muted">
                      <th className="px-5 py-2 font-medium">Key</th>
                      <th className="px-5 py-2 font-medium text-right">Value</th>
                      <th className="px-5 py-2 font-medium">Unit</th>
                      <th className="px-5 py-2 font-medium">Source</th>
                      <th className="px-5 py-2 font-medium">Verified</th>
                    </tr>
                  </thead>
                  <tbody>
                    {constants.map((c) => (
                      <tr key={c.key} className="border-t border-line hover:bg-sunken">
                        <td className="px-5 py-2.5 font-mono text-xs text-ink">{c.key}</td>
                        <td className="px-5 py-2.5 text-right tabular-nums">{c.value}</td>
                        <td className="px-5 py-2.5 text-muted">{c.unit}</td>
                        <td className="px-5 py-2.5 text-xs text-muted">{c.source}</td>
                        <td className="px-5 py-2.5">
                          <Pill tone={c.verified ? "success" : "warn"}>{c.verified ? "verified" : "unverified"}</Pill>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Surface>

          {brackets.length > 0 && (
            <Surface pad="none">
              <div className="p-5 pb-3">
                <SectionTitle title="Withholding brackets" description="Federal and state/local marginal brackets by filing status." />
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-t border-line text-left text-xs uppercase tracking-wide text-muted">
                      <th className="px-5 py-2 font-medium">Jurisdiction</th>
                      <th className="px-5 py-2 font-medium">Schedule</th>
                      <th className="px-5 py-2 font-medium">Filing</th>
                      <th className="px-5 py-2 font-medium text-right">From</th>
                      <th className="px-5 py-2 font-medium text-right">To</th>
                      <th className="px-5 py-2 font-medium text-right">Rate</th>
                    </tr>
                  </thead>
                  <tbody>
                    {brackets.slice(0, 200).map((b, i) => (
                      <tr key={i} className="border-t border-line">
                        <td className="px-5 py-2.5 text-ink">{b.jurisdiction}</td>
                        <td className="px-5 py-2.5 text-muted">{b.schedule}</td>
                        <td className="px-5 py-2.5 text-muted">{b.filing_status}</td>
                        <td className="px-5 py-2.5 text-right tabular-nums">{money(b.min_cents)}</td>
                        <td className="px-5 py-2.5 text-right tabular-nums">{money(b.max_cents)}</td>
                        <td className="px-5 py-2.5 text-right tabular-nums">{(parseFloat(b.rate) * 100).toFixed(2)}%</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Surface>
          )}
        </>
      )}
    </div>
  );
}
