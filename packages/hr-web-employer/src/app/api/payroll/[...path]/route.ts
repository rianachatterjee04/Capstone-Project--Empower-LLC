import { NextRequest, NextResponse } from "next/server";

/**
 * Server-side fail-soft proxy to the standalone Fintra Payroll service
 * (packages/payroll, PAYROLL_API_URL, default http://localhost:8050).
 *
 * SECURITY
 *  - Only the allow-listed employer endpoints below are reachable; anything
 *    else 404s here without touching payroll.
 *  - The HR->payroll internal secret (PAYROLL_INTERNAL_SECRET) is NEVER used
 *    or exposed by this route: employer traffic authenticates with payroll's
 *    bearer RBAC (dev-token mapping `dev:<org>:<role>:<email>:<user>` in
 *    non-production — mirrors packages/payroll/app/api/deps.py).
 *  - The browser's Authorization header is forwarded when it is a dev token;
 *    otherwise a server-side dev bearer is constructed from env.
 *
 * FAIL-SOFT: a network error or timeout returns HTTP 502 with { error:
 * "payroll unreachable" } rather than a stack trace, so the client helper
 * (src/lib/payroll.ts) can degrade the page to an empty state. Upstream
 * statuses (incl. the 402 license lock) pass through as-is.
 *
 * This comment used to say those errors returned 200. They return 502, and
 * have for as long as the code below has read `{ status: 502 }`. A comment
 * that disagrees with its code about a status code is worse than no comment:
 * the next person debugging an empty payroll page trusts it.
 */
export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const BASE = process.env.PAYROLL_API_URL || "http://localhost:8050";
const ORG = process.env.PAYROLL_DEMO_ORG || "11111111-1111-1111-1111-111111111111";
const ROLE = process.env.PAYROLL_DEV_ROLE || "owner";
const USER = process.env.PAYROLL_DEV_USER || "22222222-2222-2222-2222-222222222222";
const TIMEOUT_MS = 3500;

// Employer-safe allow-list (payroll RBAC still applies on top).
const ALLOW: Array<{ method: string; re: RegExp }> = [
  { method: "GET", re: /^license\/status$/ },
  { method: "GET", re: /^runs$/ },
  { method: "GET", re: /^runs\/[A-Za-z0-9-]+$/ },
  { method: "GET", re: /^runs\/[A-Za-z0-9-]+\/paychecks$/ },
  { method: "GET", re: /^runs\/[A-Za-z0-9-]+\/review$/ },
  { method: "POST", re: /^runs\/[A-Za-z0-9-]+\/(approve|reject)$/ },
  { method: "POST", re: /^runs\/[A-Za-z0-9-]+\/(submit|process)$/ },
  { method: "GET", re: /^employees$/ },
  {
    method: "GET",
    re: /^reports\/(payroll-summary|cash-requirements|labor-cost-by-department|coverage|w2-summary|form-940|1099-nec|1099-nec-summary|contractor-payments|tax-liability|tax-wage-summary)$/,
  },
  // Remittances / EFTPS liabilities (view + mark deposited).
  { method: "GET", re: /^remittances$/ },
  { method: "GET", re: /^remittance-destinations$/ },
  { method: "POST", re: /^remittances\/[A-Za-z0-9-]+\/mark-paid$/ },
  // Tax configuration / versioned rates (read-only surfaces).
  { method: "GET", re: /^tax-rates$/ },
  { method: "GET", re: /^tax-rates\/verification$/ },
  { method: "GET", re: /^tax-rates\/refresh-log$/ },
  { method: "GET", re: /^org-tax-config$/ },
  { method: "GET", re: /^org-settings$/ },
  { method: "GET", re: /^gl-map$/ },
  { method: "GET", re: /^compliance\/calendar$/ },
];

function authHeader(req: NextRequest): string {
  const incoming = req.headers.get("authorization") || "";
  if (incoming.startsWith("Bearer dev:")) return incoming;
  return `Bearer dev:${ORG}:${ROLE}:payroll@people.local:${USER}`;
}

/**
 * SECURITY: this proxy mints an unsigned `dev:` bearer token server-side, so any
 * browser that can reach it inherits whatever role the token asserts. That is only
 * acceptable outside production. Treated as production unless the environment says
 * otherwise, matching the fail-closed default in the Python services. The upstream
 * payroll service also refuses `dev:` tokens in production (packages/payroll/
 * app/api/deps.py), so this is defence in depth rather than the only control.
 */
function devProxyDisabled(): boolean {
  const env = (process.env.VERCEL_ENV || process.env.NODE_ENV || "production").toLowerCase();
  return !["development", "dev", "test", "local", "preview"].includes(env);
}

async function proxy(req: NextRequest, params: { path: string[] }) {
  if (devProxyDisabled()) {
    return NextResponse.json(
      { error: "This payroll proxy is disabled in production: it mints an unsigned dev token. Configure real authentication." },
      { status: 501 },
    );
  }

  const path = (params.path || []).join("/");
  const allowed = ALLOW.some((a) => a.method === req.method && a.re.test(path));
  if (!allowed) {
    return NextResponse.json(
      { error: `endpoint not allowed through this proxy: ${req.method} ${path}` },
      { status: 404 },
    );
  }

  const url = new URL(`${BASE}/api/payroll/${path}`);
  req.nextUrl.searchParams.forEach((v, k) => url.searchParams.set(k, v));

  const init: RequestInit = {
    method: req.method,
    headers: {
      Authorization: authHeader(req),
      "Content-Type": "application/json",
    },
    cache: "no-store",
  };
  if (req.method !== "GET") {
    const body = await req.text();
    init.body = body || "{}";
  }

  try {
    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort(), TIMEOUT_MS);
    const r = await fetch(url, { ...init, signal: ctrl.signal });
    clearTimeout(t);
    const text = await r.text();
    let json: unknown;
    try {
      json = text ? JSON.parse(text) : {};
    } catch {
      json = { error: `payroll returned non-JSON (${r.status})` };
    }
    return NextResponse.json(json, { status: r.status });
  } catch {
    // Fail-soft: service down is a normal state for the UI, not a 5xx.
    return NextResponse.json(
      { error: "payroll unreachable" },
      { status: 502 },
    );
  }
}

export async function GET(req: NextRequest, ctx: { params: { path: string[] } }) {
  return proxy(req, ctx.params);
}
export async function POST(req: NextRequest, ctx: { params: { path: string[] } }) {
  return proxy(req, ctx.params);
}
