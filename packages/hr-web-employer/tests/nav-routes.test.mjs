/**
 * Every nav entry points at a page that exists, and every page is reachable.
 *
 * WHY THIS IS A TEST
 * Two defects of this shape, in one session:
 *
 *   /app/interview-review was linked from NOWHERE. The recruiter surface the
 *   product is built around -- scorecard, evidence, recording -- was reachable
 *   only by pasting a UUID into the address bar.
 *
 *   The nav's "Interview scorecards" pointed at /app/interviews while the
 *   actual page lived at /app/interviews/scorecards. Nobody noticed, because
 *   /app/interviews also existed and rendered something plausible.
 *
 * The second one is the reason this checks BOTH directions. A dead nav link is
 * invisible when a neighbouring route happens to answer.
 *
 * Run with:  npm run test:ui
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";

function walk(dir, filter) {
  const out = [];
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) out.push(...walk(p, filter));
    else if (filter(p)) out.push(p);
  }
  return out;
}

/** Every /app/... route the app actually serves. */
function routes() {
  return new Set(
    walk("src/app/app", (p) => p.endsWith("page.tsx")).map((p) =>
      "/" + p.replace(/^src\/app\//, "").replace(/\/page\.tsx$/, ""),
    ),
  );
}

const DYNAMIC = /\[[^\]]+\]/;

test("every nav href resolves to a page that exists", () => {
  const nav = readFileSync("src/components/nav-config.ts", "utf8");
  const served = routes();
  const missing = [];
  for (const m of nav.matchAll(/href:\s*"(\/app[^"]*)"/g)) {
    const href = m[1].replace(/\?.*$/, "").replace(/\/$/, "");
    const ok = served.has(href) ||
      [...served].some((r) => DYNAMIC.test(r) &&
        href.startsWith(r.replace(/\[[^\]]+\].*$/, "")));
    if (!ok) missing.push(href);
  }
  assert.deepEqual(missing, [],
    "nav entries pointing at routes that do not exist:\n  " +
      missing.join("\n  "));
});

test("every page is linked from somewhere", () => {
  const served = routes();
  const sources = walk("src", (p) => p.endsWith(".ts") || p.endsWith(".tsx"))
    .map((p) => readFileSync(p, "utf8"))
    .join("\n");

  // A route counts as reachable if any source mentions its path, including
  // inside a template literal.
  const orphans = [];
  for (const route of served) {
    if (DYNAMIC.test(route)) {
      // Dynamic routes are built with template literals; the prefix is enough.
      const prefix = route.replace(/\/\[[^\]]+\].*$/, "");
      if (!sources.includes(prefix + "/")) orphans.push(route);
      continue;
    }
    // Skip the route's own file mentioning itself in a comment.
    const mentions = sources.split(route + '"').length - 1 +
                     (sources.split(route + "`").length - 1) +
                     (sources.split(route + "?").length - 1) +
                     (sources.split(route + "/").length - 1);
    if (mentions === 0) orphans.push(route);
  }

  // Deliberate legacy redirects: they exist to catch old bookmarks and are
  // meant to be unlinked. Anything else in this list is a page nobody can find.
  const INTENTIONALLY_UNLINKED = new Set(["/app/digital-twin"]);
  const real = orphans.filter((r) => !INTENTIONALLY_UNLINKED.has(r));

  assert.deepEqual(real, [],
    "pages nothing links to (add a nav entry, a link, or list them as a " +
      "deliberate redirect):\n  " + real.join("\n  "));
});
