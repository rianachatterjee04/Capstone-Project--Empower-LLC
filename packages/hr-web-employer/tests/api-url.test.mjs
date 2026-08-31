/**
 * No request URL doubles the "/api" prefix.
 *
 * WHY THIS IS A TEST
 * `env.apiBaseUrl` already ends in "/api". `apiPath()` exists to strip a
 * leading "/api" off caller paths so the two do not stack. One of the two
 * helpers in lib/api.ts used it and the other did not, so every caller writing
 * "/api/equity/..." produced "/api/api/equity/..." -> 404. The whole equity
 * surface -- cap table, security classes, 409A, ASC 718, tax treatment, total
 * comp: six endpoints -- rendered the words "Not Found" beneath a header
 * promising equity expense posting straight to the ledger.
 *
 * It survived because nothing failed loudly. The page caught the error and
 * rendered a message; no test exercised the URL; and in useLiveData the same
 * slip is quieter still -- it swallows the failure and keeps showing mock data
 * behind a "Sample data" pill, which reads as a design choice rather than a
 * broken request.
 *
 * So this checks the construction site rather than any one caller: every place
 * that concatenates the API base with a caller-supplied path must route that
 * path through apiPath().
 *
 * Run with:  npm run test:ui
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { stripComments } from "./_source.mjs";

function walk(dir, filter) {
  const out = [];
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) out.push(...walk(p, filter));
    else if (filter(p)) out.push(p);
  }
  return out;
}

/** Every `${<base>}${<expr>}` template concatenation, where <base> is an API base. */
const BASE = /\$\{(env\.apiBaseUrl|API_BASE|apiBase)\}\$\{([^}]*)\}/g;

// The employee-facing app has the same helper, the same base ending in "/api",
// and no test suite of its own -- it has no node_modules, so nothing there can
// run. It had the identical defect: four callers writing "/api/equity/..." in
// its equity and compensation pages, every one of them a 404, which is what an
// employee saw when they opened their own equity. Scanned from here because
// this is where a runner exists.
const ROOTS = ["src", "../hr-web-employee/src"];

function concatSites() {
  const sites = [];
  for (const file of ROOTS.flatMap((r) => walk(r, (p) => /\.tsx?$/.test(p)))) {
    const src = stripComments(readFileSync(file, "utf8"));
    const lines = src.split("\n");
    for (const m of src.matchAll(BASE)) {
      const line = src.slice(0, m.index).split("\n").length;
      sites.push({
        file: file + ":" + line,
        base: m[1],
        expr: m[2].trim(),
        text: lines[line - 1].trim(),
      });
    }
  }
  return sites;
}

test("the scan finds the API-base concatenation sites (non-vacuity control)", () => {
  const sites = concatSites();
  // apiFetch, apiObjectUrl, useLiveData. If this drops to zero the regex has
  // rotted and the assertion below would pass against a codebase full of
  // doubled prefixes.
  assert.ok(sites.length >= 3,
    `expected at least 3 API-base concatenations, found ${sites.length}. ` +
    "The pattern no longer matches how request URLs are built, so this file " +
    "is no longer checking anything.");
});

test("every API-base concatenation routes the path through apiPath()", () => {
  const bad = concatSites()
    .filter((s) => !/^apiPath\(/.test(s.expr))
    .map((s) => `${s.file}  ${s.text}`);
  assert.deepEqual(bad, [],
    'request URLs built without apiPath() -- a caller passing "/api/x" here ' +
    'gets "/api/api/x":\n  ' + bad.join("\n  "));
});

test("apiPath strips exactly one leading /api and leaves other paths alone", () => {
  // Extracted rather than imported: lib/api.ts pulls in "@/lib/env" and the
  // Supabase client, neither of which resolves under plain node:test.
  for (const lib of ["src/lib/api.ts", "../hr-web-employee/src/lib/api.ts"]) {
  const src = readFileSync(lib, "utf8");
  const m = src.match(/export function apiPath\(path: string\): string \{([\s\S]*?)\n\}/);
  assert.ok(m, `apiPath() is not declared in ${lib} the way this test extracts it`);
  const apiPath = new Function("path", m[1].replace(/: string/g, ""));

  assert.equal(apiPath("/api/equity/cap-table"), "/equity/cap-table");
  assert.equal(apiPath("/employees"), "/employees");
  assert.equal(apiPath("/api/api/x"), "/api/x", "strips one prefix, not all of them");
  // "/apiary" must not be mangled into "ary".
  assert.equal(apiPath("/apiary/keepers"), "/apiary/keepers");
  }
});
