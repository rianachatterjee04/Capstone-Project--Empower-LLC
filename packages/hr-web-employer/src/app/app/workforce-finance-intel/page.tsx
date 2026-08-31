"use client";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { apiFetch, apiPost } from "@/lib/api";

import { PageHeader, Surface, SectionTitle, Pill, EmptyState, Divider } from "@/components/ds";

type TeamRoi = {
  team: string; headcount: number; annual_cost_loaded: number;
  revenue_attributed: number; revenue_per_head: number; cost_per_head: number;
  roi_ratio: number; is_cost_center: boolean;
};
type EmpRoi = { id: string; name: string; team: string; annual_cost_loaded: number; revenue_contribution: number; roi_ratio: number };
type RoiData = {
  org_roi_ratio: number; total_revenue_attributed: number; total_cost_loaded: number;
  teams: TeamRoi[]; employees: EmpRoi[]; top_teams: TeamRoi[]; top_employees: EmpRoi[];
};

type Scenario = "commission_change" | "headcount_add" | "attrition" | "new_market";

const SCENARIOS: { key: Scenario; label: string; blurb: string }[] = [
  { key: "commission_change", label: "Commission change", blurb: "Move the Sales commission rate → payroll + EBITDA delta." },
  { key: "headcount_add", label: "Add headcount", blurb: "Add N to a team → added cost + when-to-hire + payback." },
  { key: "attrition", label: "If they quit…", blurb: "Cost-to-backfill + knowledge/risk impact for one employee." },
  { key: "new_market", label: "Open a new market", blurb: "Recommended headcount by role + estimated payroll." },
];

function money(n?: number): string {
  if (n == null) return "—";
  const sign = n < 0 ? "-" : "";
  return `${sign}$${Math.abs(Math.round(n)).toLocaleString()}`;
}

export default function WorkforceFinanceIntelPage() {
  const roiQ = useQuery({ queryKey: ["wf-roi"], queryFn: () => apiFetch<RoiData>("/workforce/finance/roi"), refetchInterval: 120_000 });
  const roi = roiQ.data;

  const [scenario, setScenario] = useState<Scenario>("commission_change");
  const [pct, setPct] = useState(2);
  const [team, setTeam] = useState("Engineering");
  const [n, setN] = useState(2);
  const [empId, setEmpId] = useState("e8");
  const [region, setRegion] = useState("Germany");
  const [plan, setPlan] = useState("standard");
  const [result, setResult] = useState<any>(null);
  const [running, setRunning] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function run() {
    setRunning(true); setErr(null);
    const body: any =
      scenario === "commission_change" ? { kind: "commission_change", pct: Number(pct) }
      : scenario === "headcount_add" ? { kind: "headcount_add", team, n: Number(n) }
      : scenario === "attrition" ? { kind: "attrition", employee_id: empId }
      : { kind: "new_market", region, plan };
    try {
      const out = await apiPost<any>("/workforce/finance/simulate", body);
      setResult(out);
    } catch (e: any) {
      setErr(e?.message ?? "Simulation failed");
      setResult(null);
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="space-y-7 fp-fade-in">
      <PageHeader
        eyebrow="Workforce Intelligence"
        title="Workforce Financial Intelligence"
        subtitle="The Finance × HR questions nobody else can answer — because we own both. Rank people and teams by ROI, and simulate commission, headcount, attrition, and market-entry scenarios against the real P&L."
      />

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Stat label="Org ROI" value={roi ? `${roi.org_roi_ratio}×` : "—"} tone="success" />
        <Stat label="Revenue attributed" value={roi ? money(roi.total_revenue_attributed) : "—"} />
        <Stat label="Workforce cost (loaded)" value={roi ? money(roi.total_cost_loaded) : "—"} />
        <Stat label="Teams ranked" value={roi?.teams.length ?? "—"} />
      </div>

      {/* ROI ranking */}
      <Surface pad="sm">
        <SectionTitle eyebrow="ROI" title="Revenue contribution ÷ cost" description="Revenue-bearing teams ranked; cost centers flagged." />
        {roiQ.isLoading ? (
          <EmptyState title="Loading ROI…" />
        ) : !roi ? (
          <EmptyState title="No ROI data" />
        ) : (
          <div className="mt-3 overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-2xs uppercase tracking-eyebrow text-muted border-b border-line">
                  <th className="text-left py-2 font-medium">Team</th>
                  <th className="text-right py-2 font-medium">Headcount</th>
                  <th className="text-right py-2 font-medium">Cost (loaded)</th>
                  <th className="text-right py-2 font-medium">Revenue</th>
                  <th className="text-right py-2 font-medium">Rev / head</th>
                  <th className="text-right py-2 font-medium">ROI</th>
                </tr>
              </thead>
              <tbody>
                {roi.teams.map((t) => (
                  <tr key={t.team} className="border-b border-rule last:border-0">
                    <td className="py-2 text-ink font-medium">{t.team}{t.is_cost_center && <Pill tone="neutral" className="ml-2">cost center</Pill>}</td>
                    <td className="py-2 text-right tabular-nums text-body">{t.headcount}</td>
                    <td className="py-2 text-right tabular-nums text-body">{money(t.annual_cost_loaded)}</td>
                    <td className="py-2 text-right tabular-nums text-body">{money(t.revenue_attributed)}</td>
                    <td className="py-2 text-right tabular-nums text-body">{money(t.revenue_per_head)}</td>
                    <td className="py-2 text-right tabular-nums font-semibold">
                      <Pill tone={t.roi_ratio >= 3 ? "success" : t.roi_ratio > 0 ? "warn" : "neutral"}>{t.roi_ratio}×</Pill>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>

            <Divider className="my-4" />
            <div className="fp-eyebrow mb-2">Top ROI employees</div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
              {roi.top_employees.map((e) => (
                <div key={e.id} className="flex items-center justify-between rounded-md border border-line bg-canvas p-2.5">
                  <div>
                    <div className="text-sm font-medium text-ink">{e.name}</div>
                    <div className="text-2xs uppercase tracking-eyebrow text-muted">{e.team} · {money(e.annual_cost_loaded)} cost</div>
                  </div>
                  <Pill tone={e.roi_ratio >= 3 ? "success" : e.roi_ratio > 0 ? "warn" : "neutral"}>{e.roi_ratio}×</Pill>
                </div>
              ))}
            </div>
          </div>
        )}
      </Surface>

      {/* Scenario simulator */}
      <Surface pad="sm">
        <SectionTitle eyebrow="Scenario simulator" title="What if…" description="Deterministic math from comp, headcount, and revenue. Fail-soft to safe estimates." />

        <div className="mt-3 flex flex-wrap gap-1.5">
          {SCENARIOS.map((sc) => (
            <button
              key={sc.key}
              onClick={() => { setScenario(sc.key); setResult(null); setErr(null); }}
              className={`text-xs rounded-md px-3 py-1.5 border ${scenario === sc.key ? "bg-accent text-accent-fg border-accent" : "bg-surface border-line text-body hover:bg-sunken"}`}
            >
              {sc.label}
            </button>
          ))}
        </div>
        <p className="mt-2 text-xs text-muted">{SCENARIOS.find((s) => s.key === scenario)?.blurb}</p>

        <div className="mt-3 grid grid-cols-1 md:grid-cols-4 gap-2">
          {scenario === "commission_change" && (
            <LabeledInput label="Commission Δ (pts)" type="number" value={pct} onChange={(v) => setPct(Number(v))} />
          )}
          {scenario === "headcount_add" && (
            <>
              <LabeledInput label="Team" value={team} onChange={setTeam} />
              <LabeledInput label="How many" type="number" value={n} onChange={(v) => setN(Number(v))} />
            </>
          )}
          {scenario === "attrition" && (
            <LabeledInput label="Employee id" value={empId} onChange={setEmpId} />
          )}
          {scenario === "new_market" && (
            <>
              <LabeledInput label="Region" value={region} onChange={setRegion} />
              <div>
                <div className="fp-eyebrow mb-1">Plan</div>
                <select value={plan} onChange={(e) => setPlan(e.target.value)} className="h-9 w-full rounded-md border border-line bg-canvas px-3 text-sm text-ink outline-none">
                  <option value="lean">lean</option>
                  <option value="standard">standard</option>
                  <option value="growth">growth</option>
                </select>
              </div>
            </>
          )}
          <div className="flex items-end">
            <button onClick={run} disabled={running} className="h-9 rounded-md bg-accent px-4 text-sm font-medium text-accent-fg disabled:opacity-60">
              {running ? "Running…" : "Simulate"}
            </button>
          </div>
        </div>

        {err && <p className="mt-3 text-sm text-danger-fg">{err}</p>}
        {result && <ScenarioResult result={result} />}
      </Surface>
    </div>
  );
}

function ScenarioResult({ result }: { result: any }) {
  const rows: { label: string; value: React.ReactNode }[] = [];
  if (result.kind === "commission_change") {
    rows.push(
      { label: "Sales revenue base", value: money(result.sales_revenue_base) },
      { label: "Payroll Δ (base)", value: money(result.payroll_base_delta) },
      { label: "Payroll Δ (loaded)", value: money(result.payroll_loaded_delta) },
      { label: "EBITDA Δ", value: <span className={result.ebitda_delta < 0 ? "text-danger-fg" : "text-success-fg"}>{money(result.ebitda_delta)}</span> },
    );
  } else if (result.kind === "headcount_add") {
    rows.push(
      { label: "Avg base / hire", value: money(result.avg_base_per_hire) },
      { label: "Added cost (loaded)", value: money(result.added_cost_loaded) },
      { label: "Months to breakeven", value: result.when_to_hire?.months_to_breakeven ?? "—" },
      { label: "When to hire", value: <span>{result.when_to_hire?.cadence} · <Pill tone="info">{result.when_to_hire?.verdict}</Pill></span> },
    );
  } else if (result.kind === "attrition") {
    rows.push(
      { label: "Employee", value: `${result.name} · ${result.team}` },
      { label: "Recruiting", value: money(result.backfill_breakdown?.recruiting) },
      { label: "Ramp loss", value: money(result.backfill_breakdown?.ramp_loss) },
      { label: "Vacancy productivity", value: money(result.backfill_breakdown?.vacancy_productivity) },
      { label: "Cost to backfill", value: <strong>{money(result.cost_to_backfill)}</strong> },
      { label: "Knowledge risk", value: <Pill tone={result.knowledge_risk === "high" ? "danger" : result.knowledge_risk === "medium" ? "warn" : "success"}>{result.knowledge_risk}</Pill> },
    );
  } else if (result.kind === "new_market") {
    rows.push(
      { label: "Region factor", value: result.region_cost_factor },
      { label: "Total headcount", value: result.total_headcount },
      { label: "Roles", value: (result.roles ?? []).map((r: any) => `${r.count} ${r.role}`).join(", ") },
      { label: "Estimated payroll (loaded)", value: <strong>{money(result.estimated_payroll_loaded)}</strong> },
    );
  }
  return (
    <div className="mt-4 rounded-md border border-line bg-canvas p-4">
      <div className="fp-eyebrow mb-2">Result</div>
      <div className="space-y-1.5">
        {rows.map((r, i) => (
          <div key={i} className="flex items-baseline gap-3 text-sm border-b border-rule last:border-0 py-1.5">
            <div className="w-44 shrink-0 text-xs text-muted">{r.label}</div>
            <div className="text-ink tabular-nums">{r.value}</div>
          </div>
        ))}
      </div>
      {result.narrative?.text && (
        <p className="mt-3 text-sm text-body italic">
          “{result.narrative.text}”
          <span className="ml-1 text-2xs not-italic uppercase tracking-eyebrow text-muted">({result.narrative.source})</span>
        </p>
      )}
    </div>
  );
}

function LabeledInput({ label, value, onChange, type = "text" }: { label: string; value: string | number; onChange: (v: string) => void; type?: string }) {
  return (
    <div>
      <div className="fp-eyebrow mb-1">{label}</div>
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="h-9 w-full rounded-md border border-line bg-canvas px-3 text-sm text-ink outline-none focus:bg-surface"
      />
    </div>
  );
}

function Stat({ label, value, tone = "neutral" }: { label: string; value: React.ReactNode; tone?: "neutral" | "success" | "warn" }) {
  const ring: Record<string, string> = { neutral: "", success: "ring-1 ring-success-line", warn: "ring-1 ring-warn-line" };
  return (
    <div className={`rounded-md border border-line bg-surface p-4 ${ring[tone]}`}>
      <div className="fp-eyebrow">{label}</div>
      <div className="mt-1 text-2xl font-semibold tracking-tight text-ink tabular-nums">{value}</div>
    </div>
  );
}
