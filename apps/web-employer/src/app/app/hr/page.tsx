"use client";
import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";

type Employee = { id: string; full_name: string; email: string; job_title?: string | null; department?: string | null; status: string; created_at: string };
type Case = { id: string; title: string; status: string; severity?: string | null; created_at: string };
type EscalationRule = { id: string; name: string; trigger_type: string; is_active: boolean };

function Badge({ status }: { status: string }) {
  const colors: Record<string, string> = {
    active: "bg-emerald-50 text-emerald-700 border-emerald-200",
    inactive: "bg-gray-50 text-gray-500 border-gray-200",
    open: "bg-amber-50 text-amber-700 border-amber-200",
    closed: "bg-gray-50 text-gray-500 border-gray-200",
    investigating: "bg-blue-50 text-blue-700 border-blue-200",
    resolved: "bg-emerald-50 text-emerald-700 border-emerald-200",
    high: "bg-red-50 text-red-700 border-red-200",
    medium: "bg-amber-50 text-amber-700 border-amber-200",
    low: "bg-gray-50 text-gray-500 border-gray-200",
  };
  return (
    <span className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium capitalize ${colors[status] ?? "bg-gray-50 text-gray-600 border-gray-200"}`}>
      {status}
    </span>
  );
}

function StatCard({ label, value, sub, highlight }: { label: string; value: string | number; sub?: string; highlight?: boolean }) {
  return (
    <div className="rounded-2xl border border-black/10 bg-white p-5 shadow-sm">
      <div className="text-xs font-medium uppercase tracking-widest text-black/40">{label}</div>
      <div className={`mt-2 text-3xl font-bold ${highlight ? "text-amber-600" : "text-black"}`}>{value}</div>
      {sub && <div className="mt-1 text-xs text-black/50">{sub}</div>}
    </div>
  );
}

export default function HRPage() {
  const empQ = useQuery({ queryKey: ["employees"], queryFn: () => apiFetch<Employee[]>("/employees") });
  const casesQ = useQuery({ queryKey: ["cases"], queryFn: () => apiFetch<Case[]>("/cases") });
  const escalationsQ = useQuery({ queryKey: ["escalation-rules"], queryFn: () => apiFetch<EscalationRule[]>("/escalations/rules") });

  const employees = empQ.data ?? [];
  const cases = casesQ.data ?? [];
  const escalations = escalationsQ.data ?? [];

  const activeEmployees = employees.filter((e) => e.status === "active").length;
  const openCases = cases.filter((c) => c.status === "open" || c.status === "investigating").length;
  const activeEscalations = escalations.filter((e) => e.is_active).length;
  const departments = Array.from(new Set(employees.map((e) => e.department).filter(Boolean))) as string[];

  return (
    <div className="space-y-8">
      <div className="flex items-start justify-between">
        <div>
          <div className="text-2xl font-semibold">HR Dashboard</div>
          <div className="mt-1 text-sm text-black/50">People, cases, and escalation management</div>
        </div>
        <div className="rounded-xl bg-black px-4 py-2 text-sm font-medium text-white">HR Portal</div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard label="Total Employees" value={empQ.isLoading ? "—" : employees.length} sub={`${activeEmployees} active`} />
        <StatCard label="Departments" value={empQ.isLoading ? "—" : departments.length} sub="unique teams" />
        <StatCard label="Open Cases" value={casesQ.isLoading ? "—" : openCases} sub={`${cases.length} total`} highlight={openCases > 0} />
        <StatCard label="Active Escalations" value={escalationsQ.isLoading ? "—" : activeEscalations} sub={`${escalations.length} rules`} highlight={activeEscalations > 0} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="rounded-2xl border border-black/10 bg-white shadow-sm">
          <div className="border-b border-black/10 px-5 py-4">
            <div className="text-sm font-semibold">Employees</div>
            <div className="text-xs text-black/50 mt-0.5">{employees.length} total</div>
          </div>
          <div className="divide-y divide-black/5 max-h-80 overflow-y-auto">
            {empQ.isLoading && <div className="p-5 text-sm text-black/40">Loading…</div>}
            {empQ.error && <div className="p-5 text-sm text-red-500">Failed to load employees</div>}
            {!empQ.isLoading && employees.length === 0 && <div className="p-5 text-sm text-black/40">No employees found</div>}
            {employees.map((emp) => (
              <div key={emp.id} className="flex items-center justify-between px-5 py-3 hover:bg-black/[0.02]">
                <div>
                  <div className="text-sm font-medium">{emp.full_name}</div>
                  <div className="text-xs text-black/50">{emp.job_title ?? "—"} · {emp.department ?? "—"}</div>
                </div>
                <Badge status={emp.status} />
              </div>
            ))}
          </div>
        </div>

        <div className="rounded-2xl border border-black/10 bg-white shadow-sm">
          <div className="border-b border-black/10 px-5 py-4">
            <div className="text-sm font-semibold">HR Cases</div>
            <div className="text-xs text-black/50 mt-0.5">{openCases} open</div>
          </div>
          <div className="divide-y divide-black/5 max-h-80 overflow-y-auto">
            {casesQ.isLoading && <div className="p-5 text-sm text-black/40">Loading…</div>}
            {casesQ.error && <div className="p-5 text-sm text-red-500">Failed to load cases</div>}
            {!casesQ.isLoading && cases.length === 0 && <div className="p-5 text-sm text-black/40">No cases found</div>}
            {cases.map((c) => (
              <div key={c.id} className="flex items-center justify-between px-5 py-3 hover:bg-black/[0.02]">
                <div>
                  <div className="text-sm font-medium">{c.title}</div>
                  <div className="text-xs text-black/50">{new Date(c.created_at).toLocaleDateString()}</div>
                </div>
                <div className="flex items-center gap-2">
                  {c.severity && <Badge status={c.severity} />}
                  <Badge status={c.status} />
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {departments.length > 0 && (
        <div className="rounded-2xl border border-black/10 bg-white shadow-sm">
          <div className="border-b border-black/10 px-5 py-4">
            <div className="text-sm font-semibold">Department Breakdown</div>
          </div>
          <div className="p-5 grid grid-cols-2 md:grid-cols-4 gap-3">
            {departments.map((dept) => {
              const count = employees.filter((e) => e.department === dept).length;
              const pct = Math.round((count / employees.length) * 100);
              return (
                <div key={dept} className="rounded-xl border border-black/10 p-3">
                  <div className="text-sm font-medium truncate">{dept}</div>
                  <div className="mt-1 text-2xl font-bold">{count}</div>
                  <div className="mt-2 h-1.5 w-full rounded-full bg-black/10">
                    <div className="h-full rounded-full bg-black" style={{ width: `${pct}%` }} />
                  </div>
                  <div className="mt-1 text-xs text-black/40">{pct}% of workforce</div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      <div className="rounded-2xl border border-black/10 bg-white shadow-sm">
        <div className="border-b border-black/10 px-5 py-4">
          <div className="text-sm font-semibold">Escalation Rules</div>
          <div className="text-xs text-black/50 mt-0.5">{activeEscalations} active</div>
        </div>
        <div className="divide-y divide-black/5">
          {escalationsQ.isLoading && <div className="p-5 text-sm text-black/40">Loading…</div>}
          {!escalationsQ.isLoading && escalations.length === 0 && <div className="p-5 text-sm text-black/40">No escalation rules configured</div>}
          {escalations.map((rule) => (
            <div key={rule.id} className="flex items-center justify-between px-5 py-3 hover:bg-black/[0.02]">
              <div>
                <div className="text-sm font-medium">{rule.name}</div>
                <div className="text-xs text-black/50 capitalize">{rule.trigger_type.replace(/_/g, " ")}</div>
              </div>
              <Badge status={rule.is_active ? "active" : "inactive"} />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
