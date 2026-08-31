/**
 * The hiring funnel counts candidates where they actually are.
 *
 * WHY THIS IS A TEST
 * The stage funnel read NEW 4 · 100% while three of those four candidates'
 * own cards, on the same screen, read "interviewing". The page contradicted
 * itself about the same four people.
 *
 * Candidate status has three vocabularies in this codebase and they disagree:
 *
 *   this page      new · screened · interview · offer · hired · rejected
 *   POST /stage    applied · interview · committee · offer · hired · rejected
 *   what is stored new · screened · hired · rejected · interviewing
 *
 * "interviewing" is in none of the first two, and the funnel's fallback sent
 * anything it did not recognise to "new" — so an unknown status did not look
 * unknown, it looked like fresh applicants at the top of the funnel. That is
 * the worst possible place to put it: a hiring manager reads a full top of
 * funnel as healthy.
 *
 * Synonyms map. Anything still unrecognised lands in "other" and is DRAWN.
 *
 * Run with:  npm run test:ui
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const LIB = "src/lib/pipelineStages.ts";
const PAGES = ["src/app/app/hiring/page.tsx", "src/app/app/talent/page.tsx"];
const raw = readFileSync(LIB, "utf8") + PAGES.map((f) => readFileSync(f, "utf8")).join("\n");

/**
 * Comments blanked, line numbers preserved.
 *
 * The last assertion below first failed against the comment that EXPLAINS the
 * old sort, because that comment quotes it. Third time this session a guard
 * has fired on the prose describing the thing it guards; strip first.
 */
const src = raw
  .replace(/\/\*[\s\S]*?\*\//g, (m) => m.replace(/[^\n]/g, " "))
  .replace(/(^|[^:])\/\/[^\n]*/g, (m, pre) => pre + " ".repeat(m.length - pre.length));

/** Extract toStage() and its table so the real logic is what gets tested. */
function loadToStage() {
  const lib = readFileSync(LIB, "utf8");
  const stages = lib.match(/export const PIPELINE_STAGES = \[([\s\S]*?)\] as const;/);
  const table = lib.match(/export const STAGE_SYNONYM[^=]*=\s*(\{[\s\S]*?\});/);
  const fn = lib.match(/export function toStage\(status: string\): Stage \| null \{([\s\S]*?)\n\}/);
  assert.ok(stages && table && fn,
    "toStage / PIPELINE_STAGES / STAGE_SYNONYM are no longer declared the way " +
    "this test extracts them");
  const body = fn[1].replace(/ as Stage/g, "").replace(/ as readonly string\[\]/g, "");
  return new Function(
    "status",
    `const PIPELINE_STAGES = [${stages[1]}];
     const STAGE_SYNONYM = ${table[1].replace(/:\s*Stage/g, "")};
     ${body}`,
  );
}

test("a stored status maps to the stage a reader would expect", () => {
  const toStage = loadToStage();
  assert.equal(toStage("interviewing"), "interview", "the exact defect: 3 of 4 candidates");
  assert.equal(toStage("applied"), "new");
  assert.equal(toStage("committee"), "interview");
  assert.equal(toStage("new"), "new");
  assert.equal(toStage("hired"), "hired");
  assert.equal(toStage("REJECTED"), "rejected", "status casing must not change the count");
});

test("an unrecognised status is not counted as a new applicant", () => {
  const toStage = loadToStage();
  for (const unknown of ["sourced", "on-hold", "withdrawn", "", "banana"]) {
    assert.equal(toStage(unknown), null,
      `${unknown || "(empty)"} was bucketed as ${toStage(unknown)}; an unknown ` +
      "stage must be surfaced, not folded into the top of the funnel");
  }
});

test("both boards agree with the API's list", () => {
  // The API declares the same six in
  // packages/hr-api/app/api/routers/recruiting.py. If these drift apart, a
  // move button offers a stage the server answers with 400 — which is exactly
  // what "-> screened" did.
  const api = readFileSync(
    "../hr-api/app/api/routers/recruiting.py", "utf8");
  const m = api.match(/CANDIDATE_STAGES = \(([^)]*)\)/);
  assert.ok(m, "the API no longer declares CANDIDATE_STAGES");
  const apiStages = [...m[1].matchAll(/"([a-z]+)"/g)].map((x) => x[1]);
  const lib = readFileSync(LIB, "utf8");
  const libStages = [...lib
    .match(/export const PIPELINE_STAGES = \[([\s\S]*?)\] as const;/)[1]
    .matchAll(/"([a-z]+)"/g)].map((x) => x[1]);
  assert.deepEqual(libStages, apiStages,
    "the UI and the API disagree about the pipeline stages; a move button " +
    "will offer a stage the server rejects");
});

test("neither board silently buckets an unknown status as new", () => {
  assert.ok(!/includes\(c\.status\)\s*\?\s*\(c\.status as Stage\)\s*:\s*"new"/.test(src),
    "a board is silently bucketing unknown statuses as new again");
});

test("unscored candidates do not rank as if they scored zero", () => {
  assert.ok(!/\(b\.ai_score \?\? 0\) - \(a\.ai_score \?\? 0\)/.test(src),
    "candidates with no AI score are being sorted as zeros, which ranks an " +
    "unscreened person below everyone rather than outside the ranking");
});
