/**
 * No screen describes a candidate from a constant.
 *
 * WHY THIS IS A TEST
 * The interview prep page hard-coded one engineer's profile — the summary
 * "5 years building async Python backends", the skills python / fastapi /
 * postgres / asyncio, and an AI MATCH of 78 — and rendered it for every
 * interview. A Senior Accountant was shown a backend engineer's background
 * above a confident-looking score that was a constant.
 *
 * It also POSTed those same invented strings to generate-plan and
 * generate-questions, so the AI output a buyer judges us on was derived from a
 * profile belonging to nobody.
 *
 * This is a worse failure than a crash. A page that fails to load is obviously
 * broken; a polished page describing the wrong person reads as what our product
 * believes about a real candidate.
 *
 * The literals are gone. This guard exists so their absence is a property of
 * the codebase rather than a fact about one commit: candidate-specific context
 * has to come from fetched data, and "we have not screened them yet" is a state
 * to render, not a gap to fill with something plausible.
 *
 * Run with:  npm run test:ui
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { stripComments } from "./_source.mjs";

function walk(dir) {
  const out = [];
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) out.push(...walk(p));
    else if (/\.tsx?$/.test(p)) out.push(p);
  }
  return out;
}

/** A candidate-context field assigned a literal string, array or number. */
const HARDCODED = new RegExp(
  String.raw`\b(candidate_?summary|candidateSummary|extracted_?skills|` +
  String.raw`extractedSkills|skill_?gaps|skillGaps|match_?score|matchScore|` +
  String.raw`ai_?summary|aiSummary|ai_?score|aiScore)\s*[:=]\s*` +
  String.raw`(?:"[^"]{8,}"|'[^']{8,}'|` + "`[^`]{8,}`" + String.raw`|\[\s*["'\`]|[0-9]{1,3}\s*[,;\n])`,
  "g",
);

function offenders(root) {
  const found = [];
  for (const file of walk(root)) {
    const src = stripComments(readFileSync(file, "utf8"));
    for (const m of src.matchAll(HARDCODED)) {
      const line = src.slice(0, m.index).split("\n").length;
      found.push(`${file}:${line}  ${m[0].replace(/\s+/g, " ").slice(0, 70)}`);
    }
  }
  return found;
}

test("no page fills candidate context with a literal", () => {
  const bad = [...offenders("src/app"), ...offenders("../hr-web-employee/src/app")];
  assert.deepEqual(bad, [],
    "these assign a candidate-specific field from a constant. Whatever it says " +
    "will be shown for every candidate, including ones it does not describe:\n  " +
    bad.join("\n  "));
});

test("the detector finds the original defect", () => {
  // CONTROL. The literals as they actually appeared on the prep page.
  const planted = `
    const candidateSummary = "5 years building async Python backends";
    const extractedSkills = ["python", "fastapi", "postgres", "asyncio"];
    const matchScore = 78,
  `;
  const hits = [...planted.matchAll(HARDCODED)].map((m) => m[0]);
  assert.equal(hits.length, 3,
    `expected all three hard-coded fields to be flagged, got ${hits.length}: ${JSON.stringify(hits)}`);
});

test("the detector accepts context read from fetched data", () => {
  // CONTROL, the other direction. This is the corrected shape — over-flagging
  // it would push someone back toward inventing a default.
  const fine = `
    const candidateSummary = candidate?.ai_summary || undefined;
    const matchScore = typeof candidate?.ai_score === "number" ? candidate.ai_score : undefined;
    const summary = candidateSummary || candidate?.resume_text?.slice(0, 600) || "";
    await apiPost(\`/interviews/\${id}/generate-plan\`, { candidate_summary: summary, extracted_skills: [] });
  `;
  assert.deepEqual([...fine.matchAll(HARDCODED)].map((m) => m[0]), []);
});
