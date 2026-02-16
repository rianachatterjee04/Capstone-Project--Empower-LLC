"use client";
import { useMemo, useState } from "react";
import { apiFetch, apiPost } from "@/lib/api";
import { useQuery } from "@tanstack/react-query";
import { Input } from "@/components/Input";
import { Button } from "@/components/Button";

export default function CFOPage() {
  const summary = useQuery({ queryKey: ["cfo_summary"], queryFn: () => apiFetch<{ headcount: number }>("/cfo/org-summary") });

  const [current, setCurrent] = useState(0);
  const [hires, setHires] = useState(10);
  const [attrition, setAttrition] = useState(0.1);
  const [avgSalary, setAvgSalary] = useState(120000);
  const [result, setResult] = useState<{ future_headcount: number; annual_payroll: number } | null>(null);

  useMemo(() => {
    if (summary.data?.headcount != null && current === 0) setCurrent(summary.data.headcount);
  }, [summary.data?.headcount]);

  async function run() {
    const r = await apiPost("/cfo/scenario", {
      current_headcount: current,
      planned_hires: hires,
      attrition_rate: attrition,
      avg_salary: avgSalary,
    });
    setResult(r);
  }

  return (
    <div className="space-y-6">
      <div>
        <div className="text-2xl font-semibold">CFO Scenario Modeling</div>
        <div className="text-sm text-black/60">
          API-backed modeling for headcount + payroll. Next: multi-scenario compare + approvals.
        </div>
      </div>

      <div className="rounded-2xl border border-black/10 p-4 grid grid-cols-1 md:grid-cols-2 gap-4">
        <Input label="Current headcount" type="number" value={current} onChange={(e) => setCurrent(parseInt(e.target.value || "0"))} />
        <Input label="Planned hires" type="number" value={hires} onChange={(e) => setHires(parseInt(e.target.value || "0"))} />
        <Input label="Attrition rate (0–1)" type="number" value={attrition} onChange={(e) => setAttrition(parseFloat(e.target.value || "0"))} />
        <Input label="Avg salary (annual)" type="number" value={avgSalary} onChange={(e) => setAvgSalary(parseFloat(e.target.value || "0"))} />
        <div className="md:col-span-2">
          <Button onClick={run}>Run scenario</Button>
        </div>
      </div>

      {result && (
        <div className="rounded-2xl border border-black/10 p-4">
          <div className="text-sm font-semibold">Result</div>
          <div className="mt-2 text-sm">Future headcount: <span className="font-medium">{result.future_headcount}</span></div>
          <div className="text-sm">Annual payroll: <span className="font-medium">${Math.round(result.annual_payroll).toLocaleString()}</span></div>
        </div>
      )}
    </div>
  );
}
