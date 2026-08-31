/**
 * No screen passes a hard-coded number to a prop that claims to have computed it.
 *
 * WHY THIS IS A TEST
 * Both interview screens rendered `matchScore={78}`. Every interview, every
 * candidate, every role: a Senior Accountant was shown a confident two-digit
 * "AI MATCH" that was a literal, next to a summary describing a Python backend
 * engineer who did not exist. An AI match score is a claim about a person, and
 * a constant presented as one is the single worst thing that can be on a
 * hiring screen.
 *
 * It is not a mistake anyone makes deliberately — it is what a placeholder
 * becomes when the real value never gets wired and nothing complains. So this
 * fails the build instead.
 *
 * A number that is genuinely a CONSTANT of the product (a threshold, a page
 * size, a default) is fine; the rule is only about props whose NAME asserts a
 * derived value — score, match, confidence, accuracy, risk, rating, prediction,
 * forecast, percent.
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

const DERIVED =
  "score|match|confidence|accuracy|risk|rating|prediction|forecast|percent";
const PROP = new RegExp(
  String.raw`\b(\w*(?:${DERIVED})\w*)\s*=\s*\{\s*(-?\d+(?:\.\d+)?)\s*\}`,
  "gi");

function offenders(files) {
  const out = [];
  for (const file of files) {
    const src = stripComments(readFileSync(file, "utf8"));
    for (const m of src.matchAll(PROP)) {
      out.push(`${file}:${src.slice(0, m.index).split("\n").length}  ${m[1]}={${m[2]}}`);
    }
  }
  return out;
}

test("the pattern still matches the defect it was written for (control)", () => {
  // Exactly what was on both interview screens.
  const sample = "<CandidateContextCard interview={iv} matchScore={78} />";
  assert.ok(PROP.test(sample), "the scan no longer recognises matchScore={78}");
  PROP.lastIndex = 0;

  // ...and does not fire on a number that is not claiming to be derived.
  const fine = "<Chart height={240} pageSize={25} maxItems={10} />";
  assert.ok(!PROP.test(fine), `the scan fires on ordinary layout numbers: ${fine}`);
  PROP.lastIndex = 0;
});

test("no screen invents a score, match, confidence or risk number", () => {
  const found = offenders(walk("src"));
  assert.deepEqual(found, [],
    "hard-coded values passed as computed metrics — these render as an " +
    "assessment of whatever the user is looking at:\n  " + found.join("\n  "));
});
