/**
 * Every candidate appears somewhere on the recruiting board.
 *
 * WHY THIS IS A TEST
 * Three of four candidates were invisible. The board's columns were the five
 * names the page happened to know — new, screened, interview, rejected, hired —
 * and it bucketed by the raw stored status:
 *
 *     const k = cand.status ?? "new";
 *     by.set(k, [...(by.get(k) ?? []), cand]);
 *
 * Three candidates are stored as "interviewing". That is not one of the five,
 * so `by.set("interviewing", ...)` created a bucket nothing renders, and they
 * disappeared from the recruiter's screen while sitting in the database. There
 * was no "offer" column at all, so anyone at offer stage vanished the same way.
 *
 * src/lib/pipelineStages.ts already held the vocabulary AND the synonyms,
 * agreed with the API, and says in its own header that this is what goes wrong.
 * The board just never imported it.
 *
 * A recruiter counts their pipeline on this screen. Silently omitting people is
 * worse than showing them in the wrong column, and putting an unknown into
 * "new" is worse still — a full top of funnel reads as a healthy pipeline.
 *
 * Run with:  npm run test:ui
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { PIPELINE_STAGES, STAGE_SYNONYM, toStage } from "../src/lib/pipelineStages.ts";

const BOARD = "src/app/app/recruiting/page.tsx";

test("every status the API can store is placed in a column", () => {
  const stored = [...PIPELINE_STAGES, ...Object.keys(STAGE_SYNONYM)];
  const unplaced = stored.filter((s) => toStage(s) === null);
  assert.deepEqual(unplaced, [],
    `these stored statuses map to no column, so those candidates vanish: ${unplaced}`);
});

test("interviewing lands in interview, not new", () => {
  // The exact three-candidate case.
  assert.equal(toStage("interviewing"), "interview");
  assert.notEqual(toStage("interviewing"), "new",
    "an unknown stage counted as 'new' makes the top of funnel look healthy");
});

test("the board groups through toStage, not the raw status", () => {
  const src = readFileSync(BOARD, "utf8");
  assert.ok(src.includes("toStage("),
    "the board is bucketing by raw status again; any value the page does not " +
    "recognise creates a bucket nothing renders");
  assert.ok(!/const cols = \[\s*"new"/.test(src),
    "the board has its own hard-coded column list again, separate from " +
    "PIPELINE_STAGES — that is how 'offer' came to have no column");
});

test("a candidate whose stage cannot be placed is shown, not dropped", () => {
  const src = readFileSync(BOARD, "utf8");
  assert.ok(src.includes("unplaced"),
    "there is no path for a candidate whose stage is unrecognised, so they are " +
    "silently absent from the board");
  assert.ok(/not shown in a column/i.test(src),
    "unplaced candidates are collected but never rendered");
});

test("an unrecognised stage really is unrecognised", () => {
  // CONTROL. If toStage() accepted anything, the guard above would be vacuous.
  assert.equal(toStage("banana"), null);
  assert.equal(toStage(""), null);
});
