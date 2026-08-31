"use client";
import { useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch, apiPost } from "@/lib/api";
import { Button } from "@/components/Button";
import { PageHeader, Surface, SectionTitle, MetricStat, StatusPill } from "@/components/ds";

type PTORequest = {
  id: string;
  start_date: string;
  end_date: string;
  reason: string;
  status: "pending" | "approved" | "denied";
  created_at: string;
};

type MyBalance = {
  employee_id: string | null;
  policy?: string | null;
  accrued_hours?: number;
  used_hours?: number;
  balance_hours?: number;
  balance_days?: number | null;
  note?: string;
};

type TeamOut = { id: string; employee_id: string; employee_name: string | null; start_date: string; end_date: string; status: string };

// ---------------------------------------------------------------------------
// Date helpers (local, timezone-safe iso as YYYY-MM-DD)
// ---------------------------------------------------------------------------
const pad = (n: number) => String(n).padStart(2, "0");
const iso = (y: number, m0: number, d: number) => `${y}-${pad(m0 + 1)}-${pad(d)}`;
const isoOf = (d: Date) => iso(d.getFullYear(), d.getMonth(), d.getDate());
const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
const DOW = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

function nthWeekday(year: number, month0: number, weekday: number, n: number): string {
  const first = new Date(year, month0, 1).getDay();
  const day = 1 + ((7 + weekday - first) % 7) + (n - 1) * 7;
  return iso(year, month0, day);
}
function lastWeekday(year: number, month0: number, weekday: number): string {
  const last = new Date(year, month0 + 1, 0);
  const offset = (7 + last.getDay() - weekday) % 7;
  return iso(year, month0, last.getDate() - offset);
}
/** Factual US public holidays for a calendar year (reference only — not your
 * company's specific holiday policy). */
function usHolidays(year: number): Record<string, string> {
  return {
    [iso(year, 0, 1)]: "New Year's Day",
    [nthWeekday(year, 0, 1, 3)]: "MLK Jr. Day",
    [nthWeekday(year, 1, 1, 3)]: "Presidents' Day",
    [lastWeekday(year, 4, 1)]: "Memorial Day",
    [iso(year, 5, 19)]: "Juneteenth",
    [iso(year, 6, 4)]: "Independence Day",
    [nthWeekday(year, 8, 1, 1)]: "Labor Day",
    [nthWeekday(year, 9, 1, 2)]: "Indigenous Peoples' / Columbus Day",
    [iso(year, 10, 11)]: "Veterans Day",
    [nthWeekday(year, 10, 4, 4)]: "Thanksgiving",
    [iso(year, 11, 25)]: "Christmas Day",
  };
}

export default function PTOPage() {
  const qc = useQueryClient();
  const today = new Date();
  const [view, setView] = useState({ y: today.getFullYear(), m: today.getMonth() });
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [reason, setReason] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [statusMsg, setStatusMsg] = useState<string | null>(null);

  const { data: requests = [], isLoading } = useQuery({
    queryKey: ["pto-requests"],
    queryFn: () => apiFetch<PTORequest[]>("/pto/requests"),
  });

  const { data: balance } = useQuery({
    queryKey: ["timeoff-balance-me"],
    queryFn: () => apiFetch<MyBalance>("/timeoff/balances/me"),
  });

  // The 6-week grid the calendar renders, so the team fetch covers every cell.
  const grid = useMemo(() => {
    const first = new Date(view.y, view.m, 1);
    const gridStart = new Date(view.y, view.m, 1 - first.getDay());
    const cells: Date[] = [];
    for (let i = 0; i < 42; i++) cells.push(new Date(gridStart.getFullYear(), gridStart.getMonth(), gridStart.getDate() + i));
    return cells;
  }, [view]);
  const gridStartIso = isoOf(grid[0]);
  const gridEndIso = isoOf(grid[41]);

  const { data: teamOut = [] } = useQuery({
    queryKey: ["timeoff-calendar", gridStartIso, gridEndIso],
    queryFn: () => apiFetch<TeamOut[]>(`/timeoff/calendar?start=${gridStartIso}&end=${gridEndIso}`),
  });

  // date -> names out that day
  const outByDay = useMemo(() => {
    const map: Record<string, string[]> = {};
    for (const t of teamOut) {
      let d = new Date(t.start_date + "T00:00:00");
      const end = new Date(t.end_date + "T00:00:00");
      while (d <= end) {
        const k = isoOf(d);
        (map[k] ||= []).push(t.employee_name || "Someone");
        d = new Date(d.getFullYear(), d.getMonth(), d.getDate() + 1);
      }
    }
    return map;
  }, [teamOut]);

  const holidays = useMemo(() => ({ ...usHolidays(view.y), ...usHolidays(view.y + 1) }), [view.y]);

  const days = startDate && endDate
    ? Math.max(0, Math.ceil((new Date(endDate).getTime() - new Date(startDate).getTime()) / (1000 * 60 * 60 * 24)) + 1)
    : 0;

  function pickDay(dIso: string) {
    // Standard range picker: first click sets start; second (>= start) sets end.
    if (!startDate || (startDate && endDate)) {
      setStartDate(dIso); setEndDate("");
    } else if (dIso < startDate) {
      setStartDate(dIso);
    } else {
      setEndDate(dIso);
    }
  }

  function shiftMonth(delta: number) {
    setView((v) => {
      const m = v.m + delta;
      return { y: v.y + Math.floor(m / 12), m: ((m % 12) + 12) % 12 };
    });
  }

  async function submit() {
    if (!startDate || !endDate || !reason) return;
    setSubmitting(true);
    setStatusMsg(null);
    try {
      await apiPost<PTORequest>("/pto/requests", { start_date: startDate, end_date: endDate, reason });
      await qc.invalidateQueries({ queryKey: ["pto-requests"] });
      await qc.invalidateQueries({ queryKey: ["timeoff-calendar"] });
      setStartDate(""); setEndDate(""); setReason("");
      setStatusMsg("✓ PTO request submitted for review.");
    } catch (e) {
      setStatusMsg((e as Error).message || "Failed to submit request. Please try again.");
    } finally {
      setSubmitting(false);
    }
  }

  const todayIso = isoOf(today);

  return (
    <div className="space-y-7 fp-fade-in">
      <PageHeader eyebrow="Workflows" title="Time off" subtitle="Pick your dates on the calendar, see who's already out, and track approvals." />

      {/* Live accrual balance */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <MetricStat label="Available" value={balance?.balance_days != null ? `${balance.balance_days}d` : "—"} hint={`${balance?.balance_hours ?? 0}h`} />
        <MetricStat label="Accrued" value={`${balance?.accrued_hours ?? 0}h`} />
        <MetricStat label="Used" value={`${balance?.used_hours ?? 0}h`} />
        <MetricStat label="Policy" value={<span className="text-sm font-medium">{balance?.policy ?? "None assigned"}</span>} hint={balance?.note} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[1fr_360px] gap-6">
        {/* Calendar */}
        <Surface pad="lg" className="space-y-4">
          <div className="flex items-center justify-between">
            <SectionTitle title={`${MONTHS[view.m]} ${view.y}`} />
            <div className="flex items-center gap-1">
              <button onClick={() => shiftMonth(-1)} className="h-8 w-8 rounded-md border border-line bg-surface text-ink hover:bg-sunken" aria-label="Previous month">‹</button>
              <button onClick={() => setView({ y: today.getFullYear(), m: today.getMonth() })} className="h-8 px-2 rounded-md border border-line bg-surface text-xs text-body hover:bg-sunken">Today</button>
              <button onClick={() => shiftMonth(1)} className="h-8 w-8 rounded-md border border-line bg-surface text-ink hover:bg-sunken" aria-label="Next month">›</button>
            </div>
          </div>

          <div className="grid grid-cols-7 gap-1">
            {DOW.map((d) => <div key={d} className="text-center text-2xs uppercase tracking-eyebrow text-muted py-1">{d}</div>)}
            {grid.map((d) => {
              const k = isoOf(d);
              const inMonth = d.getMonth() === view.m;
              const isStart = k === startDate;
              const isEnd = k === endDate;
              const inRange = startDate && endDate && k > startDate && k < endDate;
              const holiday = holidays[k];
              const out = outByDay[k] ?? [];
              const selected = isStart || isEnd;
              return (
                <button
                  key={k}
                  onClick={() => pickDay(k)}
                  title={[holiday, out.length ? `Out: ${out.join(", ")}` : ""].filter(Boolean).join(" · ") || undefined}
                  className={[
                    "relative h-16 rounded-md border p-1.5 text-left transition-colors duration-150 ease-calm",
                    inMonth ? "text-ink" : "text-faint",
                    selected ? "bg-accent text-accent-fg border-accent"
                      : inRange ? "bg-accent-soft border-line"
                      : "bg-surface border-line hover:bg-sunken",
                  ].join(" ")}
                >
                  <div className="flex items-center justify-between">
                    <span className={`text-sm font-medium ${k === todayIso && !selected ? "underline decoration-accent decoration-2 underline-offset-2" : ""}`}>{d.getDate()}</span>
                    {holiday && <span className={`h-1.5 w-1.5 rounded-full ${selected ? "bg-accent-fg" : "bg-info-fg"}`} />}
                  </div>
                  {out.length > 0 && (
                    <span className={`absolute bottom-1 left-1.5 text-2xs ${selected ? "text-accent-fg/90" : "text-muted"}`}>
                      {out.length} out
                    </span>
                  )}
                  {holiday && inMonth && (
                    <span className={`absolute bottom-1 right-1.5 text-2xs truncate max-w-[70%] text-right ${selected ? "text-accent-fg/90" : "text-info-fg"}`}>{holiday.split(" ")[0]}</span>
                  )}
                </button>
              );
            })}
          </div>

          {/* Legend */}
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-2xs text-muted pt-1">
            <span className="inline-flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-sm bg-accent" /> Selected</span>
            <span className="inline-flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-sm bg-accent-soft border border-line" /> In range</span>
            <span className="inline-flex items-center gap-1.5"><span className="h-1.5 w-1.5 rounded-full bg-info-fg" /> Public holiday</span>
            <span className="inline-flex items-center gap-1.5">“N out” · teammates already off</span>
          </div>
        </Surface>

        {/* Request form */}
        <Surface pad="lg" className="space-y-4 self-start">
          <SectionTitle title="New request" />
          <div className="rounded-md border border-line bg-canvas px-3 py-2.5 text-sm">
            {startDate ? (
              <div className="flex items-center justify-between gap-2">
                <div>
                  <div className="text-ink font-medium">{startDate}{endDate ? ` → ${endDate}` : ""}</div>
                  <div className="text-xs text-muted">{endDate ? `${days} day${days > 1 ? "s" : ""}` : "Pick an end date"}</div>
                </div>
                <button onClick={() => { setStartDate(""); setEndDate(""); }} className="text-xs text-muted hover:text-ink underline">Clear</button>
              </div>
            ) : (
              <span className="text-muted">Click a start date on the calendar.</span>
            )}
          </div>

          {(() => {
            const holidaysInRange = startDate && endDate
              ? Object.entries(holidays).filter(([k]) => k >= startDate && k <= endDate)
              : [];
            return holidaysInRange.length > 0 ? (
              <div className="text-xs text-muted">
                Includes {holidaysInRange.map(([, n]) => n).join(", ")} — you may not need to spend PTO on {holidaysInRange.length > 1 ? "these" : "this"}.
              </div>
            ) : null;
          })()}

          <div>
            <div className="mb-1 text-sm font-medium text-ink">Reason</div>
            <textarea
              className="w-full rounded-md border border-line bg-surface text-ink px-3 py-2 text-sm outline-none placeholder:text-faint focus:ring-2 focus:ring-accent/30 focus:border-accent"
              rows={3}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="Vacation, personal, medical, etc."
            />
          </div>
          <Button onClick={submit} disabled={!startDate || !endDate || !reason || submitting}>
            {submitting ? "Submitting…" : "Submit request"}
          </Button>
          {statusMsg && (
            <div className={`text-sm rounded-md border px-3 py-2 ${statusMsg.startsWith("✓") ? "bg-success-bg border-success-line text-success-fg" : "bg-danger-bg border-danger-line text-danger-fg"}`}>
              {statusMsg}
            </div>
          )}
        </Surface>
      </div>

      {/* My requests */}
      <Surface pad="none">
        <div className="border-b border-line px-5 py-4">
          <div className="text-md font-semibold text-ink">My requests</div>
          <div className="text-xs text-muted mt-0.5">{requests.length} total</div>
        </div>
        <div className="divide-y divide-rule">
          {isLoading ? (
            <div className="p-5 text-sm text-muted">Loading…</div>
          ) : requests.length === 0 ? (
            <div className="p-5 text-sm text-muted">No requests yet</div>
          ) : (
            requests.map((r) => (
              <div key={r.id} className="flex items-center justify-between px-5 py-3">
                <div>
                  <div className="text-sm font-medium text-ink">{r.start_date} → {r.end_date}</div>
                  <div className="text-xs text-muted">{r.reason}</div>
                  <div className="text-xs text-faint">{new Date(r.created_at).toLocaleString()}</div>
                </div>
                <StatusPill value={r.status} />
              </div>
            ))
          )}
        </div>
      </Surface>
    </div>
  );
}
