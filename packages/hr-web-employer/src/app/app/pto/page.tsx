"use client";

import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch, apiPost } from "@/lib/api";
import { PageHeader, StatusPill } from "@/components/ds";

type Employee = {
  id: string;
  legal_name: string;
  email: string;
};

type PTORequest = {
  id: string;
  employee_id: string;
  start_date: string;
  end_date: string;
  reason: string;
  status: "pending" | "approved" | "denied";
  review_note?: string | null;
  created_at: string;
};

type Policy = {
  id: string;
  name: string;
  accrual_hours_per_period: number;
  accrual_period: string;
  max_balance_hours: number | null;
  carryover_max_hours: number | null;
  hours_per_day: number;
  is_default: boolean;
};

type Balance = {
  employee_id: string;
  employee_name?: string | null;
  policy: string | null;
  accrued_hours: number;
  used_hours: number;
  balance_hours: number;
  balance_days: number | null;
};

type CalendarEntry = {
  id: string;
  employee_id: string;
  employee_name: string | null;
  start_date: string;
  end_date: string;
  status: string;
  reason?: string;
};

type Tab = "requests" | "policies" | "calendar";

export default function EmployerPTOPage() {
  const [tab, setTab] = useState<Tab>("requests");

  return (
    <div className="space-y-6 fp-fade-in">
      <PageHeader
        eyebrow="People"
        title="Time off"
        subtitle="Approvals, accrual policies, live balances, and the team calendar."
      />

      <div className="flex gap-1 rounded-md border border-line bg-surface p-1 w-fit">
        {(
          [
            ["requests", "Requests"],
            ["policies", "Policies & balances"],
            ["calendar", "Team calendar"],
          ] as [Tab, string][]
        ).map(([key, label]) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            className={`rounded-sm px-3 py-1.5 text-sm font-medium transition-colors duration-150 ease-calm ${
              tab === key ? "bg-accent text-accent-fg" : "text-muted hover:bg-sunken hover:text-ink"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {tab === "requests" && <RequestsTab />}
      {tab === "policies" && <PoliciesTab />}
      {tab === "calendar" && <CalendarTab />}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Requests (existing approve/deny flow)                              */
/* ------------------------------------------------------------------ */
function RequestsTab() {
  const qc = useQueryClient();
  const [noteById, setNoteById] = useState<Record<string, string>>({});

  const requestsQ = useQuery({
    queryKey: ["employer-pto-requests"],
    queryFn: () => apiFetch<PTORequest[]>("/pto/requests"),
  });
  const employeesQ = useQuery({
    queryKey: ["employees"],
    queryFn: () => apiFetch<Employee[]>("/employees"),
  });

  const employeeMap = useMemo(
    () => Object.fromEntries((employeesQ.data ?? []).map((e) => [e.id, e])),
    [employeesQ.data]
  );

  const reviewMutation = useMutation({
    mutationFn: async ({ id, action }: { id: string; action: "approve" | "deny" }) => {
      const review_note = (noteById[id] ?? "").trim() || undefined;
      return apiPost<PTORequest>(`/pto/requests/${id}/${action}`, { review_note });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["employer-pto-requests"] });
      qc.invalidateQueries({ queryKey: ["timeoff-balances"] });
    },
  });

  const all = requestsQ.data ?? [];
  const pending = all.filter((r) => r.status === "pending");
  const reviewed = all.filter((r) => r.status !== "pending");

  return (
    <div className="space-y-6">
      <div className="rounded-lg border border-line bg-surface">
        <div className="border-b border-line px-5 py-4">
          <div className="text-md font-semibold text-ink">Pending requests</div>
          <div className="text-xs text-muted mt-0.5">
            {pending.length} pending · approving deducts hours from the accrual ledger
          </div>
        </div>
        {requestsQ.isLoading ? (
          <div className="p-5 text-sm text-muted">Loading…</div>
        ) : pending.length === 0 ? (
          <div className="p-5 text-sm text-muted">No pending PTO requests.</div>
        ) : (
          <div className="divide-y divide-rule">
            {pending.map((r) => {
              const emp = employeeMap[r.employee_id];
              const isBusy = reviewMutation.isPending;
              return (
                <div key={r.id} className="px-5 py-4 space-y-3">
                  <div className="flex items-start justify-between gap-4">
                    <div>
                      <div className="text-sm font-semibold text-ink">{emp?.legal_name ?? r.employee_id}</div>
                      <div className="text-xs text-muted">{emp?.email ?? "Unknown employee"}</div>
                      <div className="text-sm text-body mt-1">
                        {r.start_date} to {r.end_date}
                      </div>
                      <div className="text-xs text-muted mt-1">{r.reason}</div>
                    </div>
                    <StatusPill value={r.status} />
                  </div>
                  <div className="grid grid-cols-1 md:grid-cols-[1fr_auto_auto] gap-2">
                    <input
                      className="rounded-md border border-line bg-surface text-ink px-3 py-2 text-sm outline-none placeholder:text-faint focus:ring-2 focus:ring-accent/30 focus:border-accent"
                      placeholder="Optional note"
                      value={noteById[r.id] ?? ""}
                      onChange={(e) =>
                        setNoteById((prev) => ({ ...prev, [r.id]: e.target.value }))
                      }
                    />
                    <button
                      className="rounded-md bg-accent px-3 py-2 text-sm font-medium text-accent-fg hover:opacity-90 transition-opacity duration-150 ease-calm disabled:opacity-40"
                      disabled={isBusy}
                      onClick={() => reviewMutation.mutate({ id: r.id, action: "approve" })}
                    >
                      Approve
                    </button>
                    <button
                      className="rounded-md border border-line bg-surface px-3 py-2 text-sm font-medium text-ink hover:bg-sunken transition-colors duration-150 ease-calm disabled:opacity-40"
                      disabled={isBusy}
                      onClick={() => reviewMutation.mutate({ id: r.id, action: "deny" })}
                    >
                      Deny
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      <div className="rounded-lg border border-line bg-surface">
        <div className="border-b border-line px-5 py-4">
          <div className="text-md font-semibold text-ink">Reviewed requests</div>
          <div className="text-xs text-muted mt-0.5">{reviewed.length} total</div>
        </div>
        {reviewed.length === 0 ? (
          <div className="p-5 text-sm text-muted">No reviewed requests yet.</div>
        ) : (
          <div className="divide-y divide-rule">
            {reviewed.map((r) => {
              const emp = employeeMap[r.employee_id];
              return (
                <div key={r.id} className="flex items-center justify-between px-5 py-3 gap-3">
                  <div>
                    <div className="text-sm font-medium text-ink">{emp?.legal_name ?? r.employee_id}</div>
                    <div className="text-xs text-muted">
                      {r.start_date} to {r.end_date}
                      {r.review_note ? ` · Note: ${r.review_note}` : ""}
                    </div>
                  </div>
                  <StatusPill value={r.status} />
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Policies + balances + accrual run                                  */
/* ------------------------------------------------------------------ */
function PoliciesTab() {
  const qc = useQueryClient();
  const policiesQ = useQuery({
    queryKey: ["timeoff-policies"],
    queryFn: () => apiFetch<Policy[]>("/timeoff/policies"),
  });
  const balancesQ = useQuery({
    queryKey: ["timeoff-balances"],
    queryFn: () => apiFetch<Balance[]>("/timeoff/balances"),
  });
  const employeesQ = useQuery({
    queryKey: ["employees"],
    queryFn: () => apiFetch<Employee[]>("/employees"),
  });

  const [form, setForm] = useState({
    name: "",
    accrual_hours_per_period: "6.67",
    accrual_period: "monthly",
    max_balance_hours: "",
    carryover_max_hours: "",
    hours_per_day: "8",
  });
  const [assign, setAssign] = useState({ policy_id: "", employee_id: "" });
  const [msg, setMsg] = useState<string | null>(null);

  const createPolicy = useMutation({
    mutationFn: () =>
      apiPost("/timeoff/policies", {
        name: form.name.trim(),
        accrual_hours_per_period: Number(form.accrual_hours_per_period),
        accrual_period: form.accrual_period,
        max_balance_hours: form.max_balance_hours ? Number(form.max_balance_hours) : null,
        carryover_max_hours: form.carryover_max_hours ? Number(form.carryover_max_hours) : null,
        hours_per_day: Number(form.hours_per_day),
      }),
    onSuccess: async () => {
      setMsg("Policy created.");
      setForm({ ...form, name: "" });
      await qc.invalidateQueries({ queryKey: ["timeoff-policies"] });
    },
    onError: (e) => setMsg((e as Error).message),
  });

  const assignPolicy = useMutation({
    mutationFn: () =>
      apiPost(`/timeoff/policies/${assign.policy_id}/assign`, {
        employee_id: assign.employee_id,
      }),
    onSuccess: async () => {
      setMsg("Policy assigned.");
      await qc.invalidateQueries({ queryKey: ["timeoff-balances"] });
    },
    onError: (e) => setMsg((e as Error).message),
  });

  const runAccruals = useMutation({
    mutationFn: () => apiPost<{ granted: number; skipped_existing: number }>("/timeoff/accruals/run", {}),
    onSuccess: async (r) => {
      setMsg(`Accruals run: ${r.granted} granted, ${r.skipped_existing} already existed.`);
      await qc.invalidateQueries({ queryKey: ["timeoff-balances"] });
    },
    onError: (e) => setMsg((e as Error).message),
  });

  const policies = policiesQ.data ?? [];
  const balances = balancesQ.data ?? [];

  const inputCls = "rounded-md border border-line bg-surface text-ink px-3 py-2 text-sm outline-none placeholder:text-faint focus:ring-2 focus:ring-accent/30 focus:border-accent";

  return (
    <div className="space-y-6">
      {msg && (
        <div className="rounded-md border border-line bg-sunken px-4 py-2.5 text-sm text-body">{msg}</div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Policies */}
        <div className="rounded-lg border border-line bg-surface">
          <div className="border-b border-line px-5 py-4 flex items-center justify-between">
            <div>
              <div className="text-md font-semibold text-ink">Accrual policies</div>
              <div className="text-xs text-muted mt-0.5">{policies.length} configured</div>
            </div>
            <button
              className="rounded-md border border-line bg-surface px-3 py-1.5 text-xs font-medium text-ink hover:bg-sunken transition-colors duration-150 ease-calm disabled:opacity-40"
              disabled={runAccruals.isPending}
              onClick={() => runAccruals.mutate()}
            >
              {runAccruals.isPending ? "Running…" : "Run accruals to today"}
            </button>
          </div>
          <div className="divide-y divide-rule">
            {policies.map((p) => (
              <div key={p.id} className="px-5 py-3">
                <div className="text-sm font-medium text-ink">{p.name}</div>
                <div className="text-xs text-muted">
                  +{p.accrual_hours_per_period}h / {p.accrual_period}
                  {p.max_balance_hours != null ? ` · cap ${p.max_balance_hours}h` : " · uncapped"}
                  {p.carryover_max_hours != null ? ` · carryover max ${p.carryover_max_hours}h` : ""}
                  {` · ${p.hours_per_day}h day`}
                </div>
              </div>
            ))}
            {policies.length === 0 && (
              <div className="px-5 py-4 text-sm text-muted">
                No policies yet — create one below (e.g. 6.67h/month ≈ 10 days/yr).
              </div>
            )}
          </div>
          <div className="border-t border-line px-5 py-4 space-y-2">
            <div className="fp-eyebrow">New policy</div>
            <div className="grid grid-cols-2 gap-2">
              <input
                className={`${inputCls} col-span-2`}
                placeholder="Name (e.g. Standard PTO)"
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
              />
              <input
                className={inputCls}
                placeholder="Hours per period"
                value={form.accrual_hours_per_period}
                onChange={(e) => setForm({ ...form, accrual_hours_per_period: e.target.value })}
              />
              <select
                className={inputCls}
                value={form.accrual_period}
                onChange={(e) => setForm({ ...form, accrual_period: e.target.value })}
              >
                <option value="monthly">Monthly</option>
                <option value="biweekly">Biweekly</option>
                <option value="annual">Annual</option>
              </select>
              <input
                className={inputCls}
                placeholder="Balance cap (h, optional)"
                value={form.max_balance_hours}
                onChange={(e) => setForm({ ...form, max_balance_hours: e.target.value })}
              />
              <input
                className={inputCls}
                placeholder="Carryover max (h, optional)"
                value={form.carryover_max_hours}
                onChange={(e) => setForm({ ...form, carryover_max_hours: e.target.value })}
              />
            </div>
            <button
              className="rounded-md bg-accent px-3 py-2 text-sm font-medium text-accent-fg hover:opacity-90 transition-opacity duration-150 ease-calm disabled:opacity-40"
              disabled={createPolicy.isPending || !form.name.trim() || !Number(form.accrual_hours_per_period)}
              onClick={() => createPolicy.mutate()}
            >
              {createPolicy.isPending ? "Creating…" : "Create policy"}
            </button>
          </div>
          <div className="border-t border-line px-5 py-4 space-y-2">
            <div className="fp-eyebrow">Assign employee</div>
            <div className="grid grid-cols-2 gap-2">
              <select
                className={inputCls}
                value={assign.policy_id}
                onChange={(e) => setAssign({ ...assign, policy_id: e.target.value })}
              >
                <option value="">Select policy…</option>
                {policies.map((p) => (
                  <option key={p.id} value={p.id}>{p.name}</option>
                ))}
              </select>
              <select
                className={inputCls}
                value={assign.employee_id}
                onChange={(e) => setAssign({ ...assign, employee_id: e.target.value })}
              >
                <option value="">Select employee…</option>
                {(employeesQ.data ?? []).map((e) => (
                  <option key={e.id} value={e.id}>{e.legal_name}</option>
                ))}
              </select>
            </div>
            <button
              className="rounded-md border border-line bg-surface px-3 py-2 text-sm font-medium text-ink hover:bg-sunken transition-colors duration-150 ease-calm disabled:opacity-40"
              disabled={assignPolicy.isPending || !assign.policy_id || !assign.employee_id}
              onClick={() => assignPolicy.mutate()}
            >
              {assignPolicy.isPending ? "Assigning…" : "Assign"}
            </button>
          </div>
        </div>

        {/* Balances */}
        <div className="rounded-lg border border-line bg-surface">
          <div className="border-b border-line px-5 py-4">
            <div className="text-md font-semibold text-ink">Live balances</div>
            <div className="text-xs text-muted mt-0.5">
              Ledger-derived (accruals − usage ± adjustments)
            </div>
          </div>
          {balancesQ.isLoading ? (
            <div className="p-5 text-sm text-muted">Loading…</div>
          ) : balances.length === 0 ? (
            <div className="p-5 text-sm text-muted">
              No ledger entries yet. Assign a policy and run accruals.
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-xs text-muted border-b border-line">
                    <th className="px-5 py-2 font-medium">Employee</th>
                    <th className="px-2 py-2 font-medium">Policy</th>
                    <th className="px-2 py-2 font-medium text-right">Accrued</th>
                    <th className="px-2 py-2 font-medium text-right">Used</th>
                    <th className="px-5 py-2 font-medium text-right">Balance</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-rule">
                  {balances.map((b) => (
                    <tr key={b.employee_id}>
                      <td className="px-5 py-2.5 font-medium text-ink">{b.employee_name ?? b.employee_id}</td>
                      <td className="px-2 py-2.5 text-muted">{b.policy ?? "—"}</td>
                      <td className="px-2 py-2.5 text-right tabular-nums text-body">{b.accrued_hours}h</td>
                      <td className="px-2 py-2.5 text-right tabular-nums text-body">{b.used_hours}h</td>
                      <td className="px-5 py-2.5 text-right tabular-nums font-semibold text-ink">
                        {b.balance_hours}h{b.balance_days != null ? ` (${b.balance_days}d)` : ""}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Team calendar (month grid)                                          */
/* ------------------------------------------------------------------ */
function CalendarTab() {
  const today = new Date();
  const [year, setYear] = useState(today.getFullYear());
  const [month, setMonth] = useState(today.getMonth()); // 0-based

  const first = new Date(Date.UTC(year, month, 1));
  const last = new Date(Date.UTC(year, month + 1, 0));
  const iso = (d: Date) => d.toISOString().slice(0, 10);

  const calQ = useQuery({
    queryKey: ["timeoff-calendar", year, month],
    queryFn: () =>
      apiFetch<CalendarEntry[]>(`/timeoff/calendar?start=${iso(first)}&end=${iso(last)}`),
  });

  const entries = calQ.data ?? [];
  const daysInMonth = last.getUTCDate();
  const startWeekday = first.getUTCDay(); // 0=Sun

  const byDay: Record<number, CalendarEntry[]> = {};
  for (const e of entries) {
    const s = new Date(e.start_date + "T00:00:00Z");
    const en = new Date(e.end_date + "T00:00:00Z");
    for (let d = 1; d <= daysInMonth; d++) {
      const cur = new Date(Date.UTC(year, month, d));
      if (cur >= s && cur <= en) (byDay[d] ??= []).push(e);
    }
  }

  const prevMonth = () => {
    if (month === 0) { setYear(year - 1); setMonth(11); } else setMonth(month - 1);
  };
  const nextMonth = () => {
    if (month === 11) { setYear(year + 1); setMonth(0); } else setMonth(month + 1);
  };
  const monthName = first.toLocaleString("en-US", { month: "long", timeZone: "UTC" });

  return (
    <div className="rounded-lg border border-line bg-surface">
      <div className="border-b border-line px-5 py-4 flex items-center justify-between">
        <div>
          <div className="text-md font-semibold text-ink">Who&apos;s out — {monthName} {year}</div>
          <div className="text-xs text-muted mt-0.5">
            {entries.length} request{entries.length === 1 ? "" : "s"} overlapping this month
            · amber = pending, green = approved
          </div>
        </div>
        <div className="flex gap-2">
          <button className="rounded-md border border-line bg-surface px-2.5 py-1.5 text-sm text-ink hover:bg-sunken transition-colors duration-150 ease-calm" onClick={prevMonth}>←</button>
          <button className="rounded-md border border-line bg-surface px-2.5 py-1.5 text-sm text-ink hover:bg-sunken transition-colors duration-150 ease-calm" onClick={nextMonth}>→</button>
        </div>
      </div>
      <div className="p-4 overflow-x-auto">
        <div className="grid grid-cols-7 gap-1 min-w-[640px]">
          {["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"].map((d) => (
            <div key={d} className="text-xs text-faint font-medium px-1 py-1">{d}</div>
          ))}
          {Array.from({ length: startWeekday }).map((_, i) => (
            <div key={`pad-${i}`} />
          ))}
          {Array.from({ length: daysInMonth }).map((_, i) => {
            const day = i + 1;
            const out = byDay[day] ?? [];
            return (
              <div key={day} className="min-h-[72px] rounded-md border border-line p-1.5">
                <div className="text-xs text-muted">{day}</div>
                <div className="mt-1 space-y-1">
                  {out.slice(0, 3).map((e) => (
                    <div
                      key={e.id + day}
                      title={`${e.employee_name ?? ""} · ${e.status}`}
                      className={`truncate rounded-sm px-1 py-0.5 text-[10px] font-medium ${
                        e.status === "approved"
                          ? "bg-success-bg text-success-fg"
                          : "bg-warn-bg text-warn-fg"
                      }`}
                    >
                      {e.employee_name ?? "—"}
                    </div>
                  ))}
                  {out.length > 3 && (
                    <div className="text-[10px] text-faint">+{out.length - 3} more</div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
