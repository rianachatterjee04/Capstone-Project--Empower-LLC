/**
 * Every count on the inbox rail is a real thing to do.
 *
 * WHY THIS IS A TEST
 * The rail read "Approvals 3 · Agent actions 0 · Case triage 0 · My drafts 2".
 *
 * "My drafts 2" was two hardcoded rows — "Your Q2 self review" and "2 peer
 * reviews requested" — under a comment reading "no backend cycle table yet, but
 * show realistic placeholders ... Empty state is honest". The empty state was
 * never reached, because the array was never empty. Both CTAs opened
 * /app/performance, which correctly says "No review cycle is running yet".
 *
 * "Approvals 3" came from CPO priorities, while /app/approvals reads the
 * approvals queue and correctly said inbox zero. Two screens using the same
 * word for different questions, and disagreeing in front of the reader.
 *
 * An inbox is a list of things you have to do. A lane that counts work which
 * does not exist teaches people to ignore the number, including on the lanes
 * that are real.
 *
 * Run with:  npm run test:ui
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { stripComments } from "./_source.mjs";

const PAGE = "src/app/app/inbox/page.tsx";
const src = stripComments(readFileSync(PAGE, "utf8"));

test("the drafts lane invents no work", () => {
  for (const invented of ["Your Q2 self review", "peer reviews requested"]) {
    assert.ok(!src.includes(invented),
      `the inbox still hardcodes "${invented}" as a draft waiting on the reader`);
  }
});

test("a lane and the page it links to do not share a name for different data", () => {
  // The rail lane reading CPO priorities must not be called "Approvals", which
  // is the name of the queue on /app/approvals.
  assert.ok(!/label:\s*"Approvals"/.test(src),
    "a rail lane is called Approvals again while reading the CPO report; " +
    "/app/approvals reads a different source and the two counts disagree");
});

test("no lane promises a feature by naming an unbuilt table", () => {
  assert.ok(!/review cycle table lands/.test(src),
    "the inbox explains itself with our schema roadmap");
});

test("the scan is looking at the right file (control)", () => {
  assert.ok(src.includes("LANES") || src.includes("LaneId"),
    `${PAGE} no longer looks like the inbox page; these assertions prove nothing`);
});
