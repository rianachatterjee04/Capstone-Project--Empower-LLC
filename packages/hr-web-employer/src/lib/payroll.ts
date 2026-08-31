/**
 * Fail-soft client for the payroll workspace, via the server-side proxy at
 * /api/payroll/[...path] (which allow-lists employer endpoints and never
 * exposes the internal HR-sync secret).
 *
 * BASE PATH LESSON: this app is served under next.config basePath '/people',
 * and route handlers live under it too — a bare fetch("/api/...") from the
 * browser would miss the base path. Always prefix with NEXT_PUBLIC_BASE_PATH
 * (fallback '/people', matching next.config.mjs).
 */
const BASE = process.env.NEXT_PUBLIC_BASE_PATH || "/people";

export type PayrollResult<T> = {
  data: T | null;
  /** human-readable failure ("" when ok) */
  error: string;
  /** payroll license not activated for this org (HTTP 402) */
  licenseLocked: boolean;
  /** payroll service down / not deployed */
  unreachable: boolean;
  status: number;
};

function detailText(body: any, status: number): string {
  const d = body?.detail ?? body?.error ?? body;
  if (typeof d === "string") return d;
  if (d && typeof d === "object") return d.error || d.detail || JSON.stringify(d);
  return `payroll error (HTTP ${status})`;
}

async function request<T>(path: string, init?: RequestInit): Promise<PayrollResult<T>> {
  try {
    const r = await fetch(`${BASE}/api/payroll/${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
      cache: "no-store",
    });
    let body: any = null;
    try {
      body = await r.json();
    } catch {
      /* empty body */
    }
    if (r.ok && body && !body.error) {
      return { data: body as T, error: "", licenseLocked: false, unreachable: false, status: r.status };
    }
    if (body?.error === "payroll unreachable") {
      return { data: null, error: "Payroll service unreachable", licenseLocked: false, unreachable: true, status: 0 };
    }
    if (r.status === 402) {
      return {
        data: null,
        error: "Payroll module not activated",
        licenseLocked: true,
        unreachable: false,
        status: 402,
      };
    }
    return { data: null, error: detailText(body, r.status), licenseLocked: false, unreachable: false, status: r.status };
  } catch {
    return { data: null, error: "Payroll service unreachable", licenseLocked: false, unreachable: true, status: 0 };
  }
}

export function payrollGet<T>(path: string): Promise<PayrollResult<T>> {
  return request<T>(path);
}

export function payrollPost<T>(path: string, body?: unknown): Promise<PayrollResult<T>> {
  return request<T>(path, { method: "POST", body: JSON.stringify(body ?? {}) });
}

/** integer cents -> "$1,234.56" (payroll money is always integer cents) */
export function fmtCents(cents: number | null | undefined): string {
  if (cents == null || Number.isNaN(cents)) return "—";
  return (cents / 100).toLocaleString("en-US", { style: "currency", currency: "USD" });
}

// ---- shared payload types (subset of packages/payroll responses) ---------
export type PayRunSummary = {
  id: string;
  schedule_id: string;
  status: "draft" | "submitted" | "approved" | "processed" | string;
  run_type: string;
  period_start: string;
  period_end: string;
  pay_date: string;
  created_by?: string | null;
  submitted_by?: string | null;
  approved_by?: string | null;
  totals: {
    employees?: number;
    gross_cents?: number;
    net_cents?: number;
    employee_taxes_cents?: number;
    employer_taxes_cents?: number;
    total_cash_required_cents?: number;
    anomaly_flags?: AnomalyFlag[];
    agent_summary?: string;
  };
};

export type AnomalyFlag = { code: string; employee_id: string | null; message: string };

export type ReviewRow = {
  employee_id: string;
  name: string;
  gross: string;
  net: string;
  gross_cents: number;
  net_cents: number;
  prev_net_cents: number | null;
  diff_vs_prev_cents: number | null;
  diff_vs_prev_pct: number | null;
};

export type PayrollEmployee = {
  id: string;
  hr_employee_id: string | null;
  first_name: string;
  last_name: string;
  email: string;
  ssn: string; // masked by the API ("***-**-1234")
  has_valid_ssn: boolean;
  department: string | null;
  cost_center: string | null;
  status: string;
  pay_basis: string;
  basis_amount_cents: number;
  pay_method: string;
  portal_active: boolean;
  is_contractor: boolean;
};
