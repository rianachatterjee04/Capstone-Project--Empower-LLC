/**
 * Every transcript authority the API can emit has a label on the review page.
 *
 * WHY THIS IS A TEST
 * The interview review page tested for SERVER_DERIVED and CLIENT_REPORTED and
 * fell through to "Transcript: origin not recorded" for anything else.
 *
 * The seeded demo interview — the one the whole record → assess → click
 * evidence demo runs on — reports DEMO_FIXTURE. So the most important case
 * landed in the fallback, and the page's headline said the origin was NOT
 * recorded while the sentence directly beneath it explained, correctly, that
 * the transcript was seeded for a demonstration and "is not evidence of
 * anything a person said". The headline contradicted the disclosure.
 *
 * On a page whose job is to say where a claim about a candidate came from,
 * "origin not recorded" is the one label that must never be wrong.
 *
 * Run with:  npm run test:ui
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const PAGE = "src/app/app/interview-review/[id]/page.tsx";

// Only the files that build a TRANSCRIPT provenance. Scanning the whole API for
// `"authority": "X"` also picked up MODELED from the trucking cost authority --
// a different vocabulary for a different question, and a false positive that
// would have sent someone to add a nonsense label to this page.
const AUTHORITY_SOURCES = [
  "../hr-api/app/interview/media.py",
  "../hr-api/app/api/routers/interview_v2.py",
];

/** The authorities the backend actually assigns to a transcript. */
function backendAuthorities() {
  const found = new Set();
  for (const file of AUTHORITY_SOURCES) {
    const src = readFileSync(file, "utf8");
    for (const m of src.matchAll(/"authority"\s*:\s*"([A-Z_]+)"/g)) found.add(m[1]);
    for (const m of src.matchAll(/authority\s*=\s*"([A-Z_]+)"/g)) found.add(m[1]);
  }
  return found;
}

function labelledAuthorities() {
  const src = readFileSync(PAGE, "utf8");
  const block = src.slice(src.indexOf("const TRANSCRIPT_ORIGIN"));
  const body = block.slice(0, block.indexOf("};"));
  return new Set([...body.matchAll(/^\s*([A-Z_]+)\s*:/gm)].map((m) => m[1]));
}

test("the review page labels every authority the API can send", () => {
  const backend = backendAuthorities();
  assert.ok(backend.size > 0, "found no transcript authorities in the API; the scan is broken");
  const labelled = labelledAuthorities();
  const unlabelled = [...backend].filter((a) => !labelled.has(a)).sort();
  assert.deepEqual(unlabelled, [],
    "these authorities have no label, so the page shows 'origin not recorded' " +
    "for a transcript whose origin IS recorded:\n  " + unlabelled.join("\n  "));
});

test("DEMO_FIXTURE is labelled as a demonstration, not as unrecorded", () => {
  const src = readFileSync(PAGE, "utf8");
  const m = src.match(/DEMO_FIXTURE:\s*"([^"]+)"/);
  assert.ok(m, "DEMO_FIXTURE has no label");
  assert.ok(/demonstration|demo|seeded/i.test(m[1]),
    `DEMO_FIXTURE reads "${m[1]}", which does not tell a reader it is seeded`);
  assert.ok(!/not recorded/i.test(m[1]),
    "DEMO_FIXTURE is still described as unrecorded; its origin is recorded precisely");
});

test("an unrecognised authority still falls back honestly", () => {
  // CONTROL. The fallback is correct for an authority we genuinely do not know;
  // removing it would be worse than the bug.
  const src = readFileSync(PAGE, "utf8");
  assert.ok(/\?\?\s*"Transcript: origin not recorded"/.test(src),
    "the fallback is gone; an unknown authority would render nothing");
});
