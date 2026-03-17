"use client";

import { useMemo, useState } from "react";
import { apiPost } from "@/lib/api";

type ScenarioResponse = {
  future_headcount: number;
  salary_cost: number;
  benefits_cost: number;
  bonus_cost: number;
  total_annual_cost: number;
  monthly_burn: number;
  runway_months: number | null;
};

export default function CFOPage() {
  const [current, setCurrent] = useState(0);
  const [plannedHires, setPlannedHires] = useState(10);
  const [attritionRate, setAttritionRate] = useState(0.1);
  const [avgSalary, setAvgSalary] = useState(120000);
  const [cashAvailable, setCashAvailable] = useState(0);

  const [result, setResult] = useState<ScenarioResponse | null>(null);

  const projectedHeadcount = useMemo(() => {
    return current + plannedHires - Math.floor(current * attritionRate);
  }, [current, plannedHires, attritionRate]);

  async function run() {
    const r = await apiPost<ScenarioResponse>("/cfo/scenario", {
      current_headcount: current,
      planned_hires: plannedHires,
      attrition_rate: attritionRate,
      avg_salary: avgSalary,
      cash_available: cashAvailable,
    });

    setResult(r);
  }

  return (
    <div className="space-y-6">
      <div className="text-2xl font-semibold">CFO Scenario Modeling</div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <label className="space-y-1">
          <div className="text-sm font-medium">Current headcount</div>
          <input
            className="w-full border rounded px-3 py-2"
            type="number"
            value={current}
            onChange={(e) => setCurrent(Number(e.target.value))}
          />
        </label>

        <label className="space-y-1">
          <div className="text-sm font-medium">Planned hires</div>
          <input
            className="w-full border rounded px-3 py-2"
            type="number"
            value={plannedHires}
            onChange={(e) => setPlannedHires(Number(e.target.value))}
          />
        </label>

        <label className="space-y-1">
          <div className="text-sm font-medium">Attrition rate</div>
          <input
            className="w-full border rounded px-3 py-2"
            type="number"
            step="0.01"
            value={attritionRate}
            onChange={(e) => setAttritionRate(Number(e.target.value))}
          />
        </label>

        <label className="space-y-1">
          <div className="text-sm font-medium">Average salary</div>
          <input
            className="w-full border rounded px-3 py-2"
            type="number"
            value={avgSalary}
            onChange={(e) => setAvgSalary(Number(e.target.value))}
          />
        </label>

        <label className="space-y-1 md:col-span-2">
          <div className="text-sm font-medium">Cash available</div>
          <input
            className="w-full border rounded px-3 py-2"
            type="number"
            value={cashAvailable}
            onChange={(e) => setCashAvailable(Number(e.target.value))}
          />
        </label>
      </div>

      <div className="rounded-2xl border border-black/10 bg-white p-5 shadow-sm">
        <div className="text-sm text-black/60">Projected headcount</div>
        <div className="text-2xl font-bold tracking-tight">{projectedHeadcount}</div>
      </div>

      <button className="rounded-xl border border-black/15 px-4 py-2 text-sm font-medium hover:bg-black/5 transition" onClick={run}>
        Run scenario
      </button>

      {result && (
        <div className="space-y-2 rounded border p-4">
          <div><strong>Future headcount:</strong> {result.future_headcount}</div>
          <div><strong>Salary cost:</strong> ${result.salary_cost.toLocaleString()}</div>
          <div><strong>Benefits cost:</strong> ${result.benefits_cost.toLocaleString()}</div>
          <div><strong>Bonus cost:</strong> ${result.bonus_cost.toLocaleString()}</div>
          <div><strong>Total annual cost:</strong> ${result.total_annual_cost.toLocaleString()}</div>
          <div><strong>Monthly burn:</strong> ${result.monthly_burn.toLocaleString()}</div>
          <div>
            <strong>Runway months:</strong>{" "}
            {result.runway_months === null ? "N/A" : result.runway_months.toFixed(1)}
          </div>
        </div>
      )}
    </div>
  );
}
