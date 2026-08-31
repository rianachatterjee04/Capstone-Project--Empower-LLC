/**
 * Seek accuracy: does clicking evidence land on the moment the candidate said it?
 *
 * A wrong answer here does not throw. It plays a DIFFERENT moment, and the
 * recruiter believes they are watching the evidence they clicked -- which is
 * worse than an error, because a decision gets made on it.
 *
 * The measurement below is requested-timecode vs landed-position, computed the
 * way the page computes it. Tolerance is ZERO: the arithmetic is exact, and the
 * only fuzziness in the real player is the container's own keyframe spacing,
 * which is downstream of this and not something this code may absorb.
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import ts from "typescript";

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC = join(HERE, "..", "src", "lib", "timeline.ts");
const PAGE = join(HERE, "..", "src", "app", "app", "interview-review", "[id]", "page.tsx");

async function load() {
  const js = ts.transpileModule(readFileSync(SRC, "utf8"), {
    compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext },
  }).outputText;
  return import("data:text/javascript;base64," + Buffer.from(js).toString("base64"));
}

const P = (part, offset, duration) => ({
  part, timeline_offset_ms: offset, duration_ms: duration,
});
/** Three contiguous 30s parts: 0-30s, 30-60s, 60-90s. */
const CONTIGUOUS = [P(1, 0, 30_000), P(2, 30_000, 30_000), P(3, 60_000, 30_000)];

// ── the measurement ────────────────────────────────────────────────────────

test("every timecode lands exactly where it was asked to", async () => {
  const { locateSeek } = await load();
  const asked = [0, 1, 999, 15_000, 29_999, 30_000, 45_500, 59_999, 60_000, 89_999];

  for (const ms of asked) {
    const got = locateSeek(CONTIGUOUS, ms);
    assert.ok(got, `${ms}ms is inside the recording and must resolve`);
    // Where the player would actually be, on the assembled timeline.
    const landed = got.part.timeline_offset_ms + got.withinSeconds * 1000;
    assert.equal(landed, ms, `asked ${ms}ms, would land at ${landed}ms`);
  }
});

test("a boundary timecode belongs to the later part, never to both", async () => {
  const { locateSeek } = await load();
  assert.equal(locateSeek(CONTIGUOUS, 30_000).part.part, 2);
  assert.equal(locateSeek(CONTIGUOUS, 29_999).part.part, 1);
  assert.equal(locateSeek(CONTIGUOUS, 60_000).part.part, 3);
  // and no timecode matches two parts
  for (const ms of [0, 30_000, 60_000, 89_999]) {
    const matches = CONTIGUOUS.filter((p) => {
      const end = p.timeline_offset_ms + p.duration_ms;
      return ms >= p.timeline_offset_ms && ms < end;
    });
    assert.equal(matches.length, 1, `${ms}ms matched ${matches.length} parts`);
  }
});

test("withinSeconds is relative to the part, not the timeline", async () => {
  const { locateSeek } = await load();
  const got = locateSeek(CONTIGUOUS, 45_500);
  assert.equal(got.part.part, 2);
  assert.equal(got.withinSeconds, 15.5,
    "seeking part 2 to 45.5s instead of 15.5s would play the wrong moment " +
    "and, on a 30s part, would silently clamp to the end");
});

test("parts arriving out of order still resolve correctly", async () => {
  const { locateSeek } = await load();
  const shuffled = [CONTIGUOUS[2], CONTIGUOUS[0], CONTIGUOUS[1]];
  assert.equal(locateSeek(shuffled, 45_500).part.part, 2);
  assert.equal(locateSeek(shuffled, 5_000).part.part, 1);
  assert.equal(locateSeek(shuffled, 70_000).part.part, 3);
});

// ── refusals: the cases where playing SOMETHING would be the bug ───────────

test("a timecode inside a gap left by a lost part is refused", async () => {
  const { locateSeek } = await load();
  // Part 2 never uploaded. Its 30 seconds are missing from the middle.
  const withHole = [P(1, 0, 30_000), P(3, 60_000, 30_000)];

  assert.equal(
    locateSeek(withHole, 45_000), null,
    "evidence timed inside the missing part must refuse. Falling through to " +
    "part 3 would play a completely different answer, and the recruiter would " +
    "have no way to know",
  );
  // the surviving parts still work
  assert.equal(locateSeek(withHole, 10_000).part.part, 1);
  assert.equal(locateSeek(withHole, 70_000).part.part, 3);
});

test("a timecode past the end is refused rather than clamped", async () => {
  const { locateSeek } = await load();
  assert.equal(locateSeek(CONTIGUOUS, 90_000), null);
  assert.equal(locateSeek(CONTIGUOUS, 10_000_000), null);
});

test("a negative or non-finite timecode is refused", async () => {
  const { locateSeek } = await load();
  for (const bad of [-1, -30_000, NaN, Infinity, -Infinity]) {
    assert.equal(locateSeek(CONTIGUOUS, bad), null, `${bad} must not resolve`);
  }
});

test("no parts at all resolves to nothing", async () => {
  const { locateSeek, timelineEndMs } = await load();
  assert.equal(locateSeek([], 0), null);
  assert.equal(timelineEndMs([]), 0);
});

test("a part with an unknown duration covers nothing rather than everything", async () => {
  const { locateSeek } = await load();
  // duration_ms null means the recorder never reported one. Treating that as
  // "unbounded" would make this part swallow every later timecode.
  const unknown = [P(1, 0, null), P(2, 0, 30_000)];
  assert.equal(locateSeek(unknown, 0).part.part, 2,
    "the part with a known duration must win over one with none");
});

// ── timeline end ───────────────────────────────────────────────────────────

test("the timeline ends at the furthest part end, not the part count", async () => {
  const { timelineEndMs } = await load();
  assert.equal(timelineEndMs(CONTIGUOUS), 90_000);
  assert.equal(timelineEndMs([P(1, 0, 30_000), P(3, 60_000, 30_000)]), 90_000,
    "a missing middle part does not shorten the recording's span");
  assert.equal(timelineEndMs([P(3, 60_000, 30_000), P(1, 0, 30_000)]), 90_000);
});

// ── wiring control ─────────────────────────────────────────────────────────

test("the review page uses this module rather than its own copy", () => {
  const src = readFileSync(PAGE, "utf8");
  assert.ok(
    src.includes('from "@/lib/timeline"') && src.includes("locateSeek("),
    "the page must call locateSeek — a tested function the page does not use " +
    "proves nothing about what a recruiter clicks",
  );
  assert.ok(
    !/const\s+partFor\s*=/.test(src),
    "the page must not keep a second copy of the arithmetic",
  );
});
