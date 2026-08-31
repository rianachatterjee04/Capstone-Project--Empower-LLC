#!/usr/bin/env node
/**
 * WHOLE_APP_SMOKE — does every screen in the employer app actually load?
 *
 *     node tools/smoke.mjs                     # every route
 *     node tools/smoke.mjs --group trucking    # one group
 *     node tools/smoke.mjs --base http://localhost:3001/people
 *
 * WHAT THIS IS FOR
 * The suite has thousands of unit tests and until tonight nothing had ever
 * asked the simplest question a buyer asks first: click every item in the
 * navigation and see whether anything breaks. A page that throws during render
 * still passes every test of the functions it calls.
 *
 * WHAT IT CHECKS, per route
 *   * the HTTP status
 *   * that the HTML is not Next's error or not-found page, which are BOTH
 *     served with a 200 in the app router -- a status code alone would call
 *     them healthy
 *
 * WHAT IT DOES NOT CHECK, AND WILL NOT PRETEND TO
 * Whether anything is ON the page. Every screen here is a client component, so
 * the server sends a shell and React fills it in. Console exceptions, dead
 * controls, empty states and interaction all need a real browser. This is the
 * cheap sweep that says where to point one.
 *
 * Dynamic routes need a real id, so they are listed with one. A route whose
 * id is missing from the demo data is reported as SKIPPED with the reason,
 * never as a pass.
 */
const arg = (n, d) => {
  const i = process.argv.indexOf(`--${n}`);
  return i > -1 ? process.argv[i + 1] : d;
};
const BASE = arg("base", "http://localhost:3001/people");
const ONLY = arg("group", null);
const TIMEOUT = Number(arg("timeout", "45000"));

/** id-bearing routes get their id from the demo seed, via the API. */
const API = arg("api", "http://localhost:8000");
const DEV_TOKEN =
  "dev:11111111-1111-1111-1111-111111111111:owner:dev@local.test:22222222-2222-2222-2222-222222222222";

const GROUPS = {
  home: ["/app", "/app/brief", "/app/inbox", "/app/activity", "/app/notifications"],
  hr: ["/app/hr", "/app/people", "/app/org", "/app/teams", "/app/onboarding",
       "/app/offboarding", "/app/pto", "/app/performance", "/app/goals",
       "/app/one-on-ones", "/app/recognition", "/app/learning", "/app/skills"],
  recruiting: ["/app/recruiting", "/app/hiring", "/app/ats", "/app/talent",
               "/app/referrals", "/app/recruiter-cockpit", "/app/reference-check",
               "/app/calibration", "/app/candidate-integrity"],
  interviews: ["/app/ai-interviews", "/app/interviews", "/app/interview-ai",
               "/app/interview-loop", "/app/interview-monitor",
               "/app/interviews/scorecards", "/app/interviews/live"],
  payroll: ["/app/payroll", "/app/payroll/employees", "/app/payroll/remittances",
            "/app/payroll/tax-config", "/app/payroll/year-end",
            "/app/payroll-risk", "/app/payroll-trust", "/app/pay-equity"],
  finance: ["/app/finance", "/app/cfo", "/app/comp", "/app/bonuses",
            "/app/benefits", "/app/equity", "/app/reports", "/app/analytics"],
  trucking: ["/app/trucking"],
  commercial: ["/app/commercial", "/app/market", "/app/crm", "/app/grow",
               "/app/content-studio", "/app/marketplace"],
  assurance: ["/app/audit", "/app/compliance", "/app/governance", "/app/risk",
              "/app/approvals", "/app/escalations", "/app/investigations",
              "/app/policies", "/app/cases", "/app/ombudsman", "/app/verification"],
  ai: ["/app/agents", "/app/agent-store", "/app/assistant", "/app/automations",
       "/app/ai-coaching", "/app/ai-onboarding", "/app/ai-productivity",
       "/app/ai-skills-matrix", "/app/workforce-ai", "/app/exec-copilot"],
  workforce: ["/app/workforce-graph", "/app/workforce-registry",
              "/app/workforce-finance-intel", "/app/org-design", "/app/org-graph",
              "/app/digital-twin", "/app/engagement", "/app/pulse", "/app/insights"],
  ops: ["/app/work", "/app/calendar", "/app/checklists", "/app/documents",
        "/app/integrations", "/app/settings", "/app/setup", "/app/memory",
        "/app/command-center", "/app/manager", "/app/reports"],
};

/** Filled from the demo data at run time. */
const DYNAMIC = [
  { group: "interviews", path: (id) => `/app/interview-review/${id}`, need: "interview" },
  { group: "trucking", path: (id) => `/app/trucking/loads/${id}`, need: "load" },
];

async function demoIds() {
  const out = {};
  try {
    const r = await fetch(`${API}/api/interview-v2/list`, {
      headers: { Authorization: `Bearer ${DEV_TOKEN}` },
      signal: AbortSignal.timeout(15000),
    });
    if (r.ok) {
      const b = await r.json();
      const withMedia = (b.interviews || []).find((i) => i.recording_parts > 0);
      out.interview = (withMedia || (b.interviews || [])[0])?.id;
    }
  } catch { /* reported as SKIPPED below */ }
  try {
    // There is no /trucking/loads list endpoint -- the Today board reaches
    // loads through the drill-through, which is also the path a user takes.
    const r = await fetch(`${API}/api/trucking/drill/active_loads`, {
      headers: { Authorization: `Bearer ${DEV_TOKEN}` },
      signal: AbortSignal.timeout(15000),
    });
    if (r.ok) {
      const b = await r.json();
      out.load = (b.rows || [])[0]?.id;
    }
  } catch { /* reported as SKIPPED below */ }
  return out;
}

/**
 * Next's app router serves its error and not-found pages with a 200, so the
 * status code alone would call a crashed page healthy.
 */
function verdictFor(status, html) {
  if (status !== 200) return { ok: false, why: `HTTP ${status}` };

  // STRIP SCRIPTS FIRST. Next serialises the route's not-found boundary into
  // the RSC payload of pages that rendered perfectly well, so searching the
  // raw HTML for "This page could not be found" reported every healthy page as
  // a 404. Checked against curl, which disagreed, which is what exposed it.
  const visible = html.replace(/<script[\s\S]*?<\/script>/g, " ");

  if (/This page could not be found/i.test(visible) ||
      /<title>\s*404/i.test(html))
    return { ok: false, why: "Next 404 page (served as 200)" };
  if (/Application error: a (client|server)-side exception/i.test(visible))
    return { ok: false, why: "Next error boundary (served as 200)" };
  if (/Internal Server Error/i.test(visible))
    return { ok: false, why: "server error in the body" };
  // CONTENT IS NOT VISIBLE FROM HERE, and pretending otherwise is worse than
  // not checking. Every screen in this app is a client component, so the
  // server sends a shell and React fills it in the browser. A first draft
  // failed all five home routes for "rendered almost nothing (14 chars)" --
  // they render fine. What HTTP can honestly establish is that the route
  // exists, the server did not error, and the error boundary did not trip.
  // Anything about what is ON the page needs a browser, and this reports that
  // rather than guessing.
  const text = visible.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
  return {
    ok: true,
    why: text.length < 40 ? "route ok (client-rendered; content unverified here)"
                          : `route ok (${text.length} chars server-rendered)`,
  };
}

async function check(path) {
  const t0 = Date.now();
  try {
    const res = await fetch(BASE + path, { signal: AbortSignal.timeout(TIMEOUT) });
    const html = await res.text();
    const v = verdictFor(res.status, html);
    return { path, ...v, ms: Date.now() - t0 };
  } catch (e) {
    return { path, ok: false, why: `${e.name}: ${e.message}`, ms: Date.now() - t0 };
  }
}

const ids = await demoIds();
const rows = [];
const groups = ONLY ? { [ONLY]: GROUPS[ONLY] } : GROUPS;
if (ONLY && !GROUPS[ONLY]) {
  console.error(`no such group '${ONLY}'. Known: ${Object.keys(GROUPS).join(", ")}`);
  process.exit(2);
}

for (const [group, paths] of Object.entries(groups)) {
  for (const p of paths) rows.push({ group, ...(await check(p)) });
  for (const d of DYNAMIC.filter((d) => d.group === group)) {
    const id = ids[d.need];
    if (!id) {
      rows.push({ group, path: d.path(`<no ${d.need}>`), ok: null,
                  why: `SKIPPED — no ${d.need} in the demo data; seed it first`, ms: 0 });
      continue;
    }
    rows.push({ group, ...(await check(d.path(id))) });
  }
}

let lastGroup = "";
for (const r of rows) {
  if (r.group !== lastGroup) { console.log(`\n${r.group.toUpperCase()}`); lastGroup = r.group; }
  const mark = r.ok === null ? "skip" : r.ok ? " ok " : "FAIL";
  console.log(`  ${mark}  ${r.path.padEnd(46)} ${String(r.ms).padStart(5)}ms  ${r.why}`);
}

const failed = rows.filter((r) => r.ok === false);
const skipped = rows.filter((r) => r.ok === null);
console.log(`\n${"─".repeat(64)}`);
console.log(`  ${rows.length} routes · ${rows.length - failed.length - skipped.length} ok · ` +
            `${failed.length} FAILED · ${skipped.length} skipped`);
if (skipped.length) {
  console.log(`\n  skipped (a skip is not a pass):`);
  for (const s of skipped) console.log(`    ${s.path} — ${s.why}`);
}
if (failed.length) {
  console.log(`\n  failures:`);
  for (const f of failed) console.log(`    ${f.path} — ${f.why}`);
}
process.exit(failed.length ? 1 : 0);
