/**
 * Controls for the recorded-part upload retry and its lost-part accounting.
 *
 * These are the two mechanisms standing between "a part failed to upload" and
 * "the candidate is shown a finished interview the server does not fully have".
 * Both are invisible when they work, so each gets a positive control (it fires
 * on real loss), a negative control (it stays quiet on success AND on a blip it
 * recovered from), and a wiring control (the caller does not swallow the
 * rejection the retry is driven by -- the exact bug that made both dead code).
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import ts from "typescript";

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC = join(HERE, "..", "src", "lib", "interviewCapture.ts");
const PAGE = join(HERE, "..", "src", "app", "app", "interview-live", "[id]", "page.tsx");

/** Compile the real module and load it. Not a copy of the logic — the logic. */
async function loadCapture() {
  const js = ts.transpileModule(readFileSync(SRC, "utf8"), {
    compilerOptions: {
      target: ts.ScriptTarget.ES2022,
      module: ts.ModuleKind.ESNext,
      experimentalDecorators: false,
    },
  }).outputText;
  const url =
    "data:text/javascript;base64," + Buffer.from(js, "utf8").toString("base64");
  return import(url);
}

function makeCapture(mod, onPart) {
  return new mod.InterviewCapture({
    onState: () => {},
    onPart,
    onTranscript: () => {},
  });
}

// ── negative control: a clean upload is sent once and is not "lost" ─────────
test("a successful upload is attempted once and recorded as no loss", async () => {
  const mod = await loadCapture();
  let calls = 0;
  const cap = makeCapture(mod, async () => { calls += 1; });

  await cap.sendPartWithRetry(new Blob(["x"]), 1, 0, 1000);

  assert.equal(calls, 1, "a working upload must not be retried");
  assert.deepEqual(cap.lostParts, [], "a delivered part is not a lost part");
});

// ── negative control: the blip case — retried, recovered, NOT lost ──────────
test("a transient failure is retried and, once it lands, is not reported lost", async () => {
  const mod = await loadCapture();
  let calls = 0;
  const cap = makeCapture(mod, async () => {
    calls += 1;
    if (calls < 3) throw new Error("network blip");
  });

  await cap.sendPartWithRetry(new Blob(["x"]), 4, 0, 1000);

  assert.equal(calls, 3, "should have retried until it succeeded");
  assert.deepEqual(
    cap.lostParts, [],
    "a part that eventually uploaded is NOT lost — reporting it would make " +
    "every flaky network look like data loss and train recruiters to ignore " +
    "the warning",
  );
});

// ── positive control: a genuinely lost part is retried, then reported ───────
test("an upload that never succeeds is bounded and reported as lost", async () => {
  const mod = await loadCapture();
  let calls = 0;
  const cap = makeCapture(mod, async () => {
    calls += 1;
    throw new Error("server down");
  });

  await cap.sendPartWithRetry(new Blob(["x"]), 7, 0, 1000);

  assert.equal(calls, 3, "retries must be bounded, not infinite");
  assert.deepEqual(
    cap.lostParts, [7],
    "the part number that never landed must be reported by number",
  );
});

// ── positive control: losses accumulate rather than overwrite ───────────────
test("multiple lost parts are all reported", async () => {
  const mod = await loadCapture();
  const cap = makeCapture(mod, async () => { throw new Error("down"); });
  await cap.sendPartWithRetry(new Blob(["x"]), 2, 0, 10);
  await cap.sendPartWithRetry(new Blob(["x"]), 5, 0, 10);
  assert.deepEqual(cap.lostParts, [2, 5]);
});

// ── control: flush() waits for the retries, it does not race them ───────────
test("flush() does not return while a part is still retrying", async () => {
  const mod = await loadCapture();
  let settled = false;
  let calls = 0;
  const cap = makeCapture(mod, async () => {
    calls += 1;
    if (calls < 3) throw new Error("blip");
    await new Promise((r) => setTimeout(r, 30));
    settled = true;
  });

  void cap.sendPartWithRetry(new Blob(["x"]), 1, 0, 10);
  await cap.flush();
  assert.equal(
    settled, true,
    "flush() returned while an upload was still in flight — this is what let " +
    "a finished screen appear over an unfinished upload",
  );
});

// ── wiring control: the caller must not swallow the rejection ───────────────
test("the live interview page lets an upload rejection reach the capture layer", () => {
  const src = readFileSync(PAGE, "utf8");
  const start = src.indexOf("onPart:");
  assert.ok(start > 0, "onPart handler not found — this guard needs updating");
  const body = src.slice(start, src.indexOf("onTranscript:", start));

  assert.ok(
    body.includes("await uploadPart("),
    "the page must await the upload",
  );
  assert.ok(
    !/catch\s*(\([^)]*\))?\s*\{/.test(body),
    "onPart must NOT catch the upload error. Catching it here resolves the " +
    "promise the retry and the lost-part accounting are driven by, silently " +
    "disabling both while every test that does not check delivery still passes.",
  );
});

// ── wiring control: the lost count actually reaches the candidate ───────────
test("lost parts are surfaced in the UI, not just counted", () => {
  const src = readFileSync(PAGE, "utf8");
  assert.ok(
    src.includes("lostParts"),
    "the page never reads lostParts — an accounting nobody displays is not " +
    "an accounting",
  );
  const idx = src.indexOf("lostParts");
  assert.ok(
    src.slice(idx, idx + 700).includes("setCaptureNote"),
    "reading lostParts must lead to something the candidate can see",
  );
});
