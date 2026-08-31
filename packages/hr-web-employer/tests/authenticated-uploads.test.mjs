/**
 * Every request that leaves the browser carries credentials.
 *
 * WHY THIS IS A TEST
 * `interviewCapture.uploadPart` takes a `headers` option and the candidate
 * page passed none. Every recorded part was POSTed unauthenticated and refused
 * with "422: header authorization Field required" — proven against the live
 * endpoint, 422 without and 200 with.
 *
 * That single missing header is why the recording pipeline read as
 * NOT_CONNECTED end to end. It was invisible in review because reaching the
 * code needs a working camera, and invisible in tests because nothing asserted
 * on it. The same shape appeared twice more in one session: a <video src>
 * pointed at a protected URL, and a media element that cannot send a header.
 *
 * So the rule is checked mechanically: a fetch to the API base, or a helper
 * that posts to it, has to send an Authorization header or say why not.
 *
 * Run with:  npm run test:ui
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";

function walk(dir) {
  const out = [];
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) out.push(...walk(p));
    else if (p.endsWith(".ts") || p.endsWith(".tsx")) out.push(p);
  }
  return out;
}

const FILES = walk("src");

test("every uploadPart call sends credentials", () => {
  const offenders = [];
  for (const file of FILES) {
    const src = readFileSync(file, "utf8");
    // Skip the helper's own definition.
    if (src.includes("export async function uploadPart")) continue;
    let idx = src.indexOf("uploadPart(");
    while (idx !== -1) {
      // The argument object ends at the closing brace of the options literal.
      const call = src.slice(idx, idx + 700);
      const end = call.indexOf("});");
      const args = end === -1 ? call : call.slice(0, end);
      if (!args.includes("headers")) {
        offenders.push(`${file}:${src.slice(0, idx).split("\n").length}`);
      }
      idx = src.indexOf("uploadPart(", idx + 1);
    }
  }
  assert.deepEqual(offenders, [],
    "uploadPart called without an Authorization header — the upload will be " +
      "refused 422 and the failure only shows up with a real camera:\n  " +
      offenders.join("\n  "));
});

test("a media element is never pointed straight at a protected API url", () => {
  const offenders = [];
  for (const file of FILES) {
    const src = readFileSync(file, "utf8");
    for (const m of src.matchAll(/<(video|audio)\b[^>]*?src=\{`?\$\{env\.apiBaseUrl\}/gs)) {
      offenders.push(`${file}:${src.slice(0, m.index).split("\n").length}`);
    }
  }
  assert.deepEqual(offenders, [],
    "a <video>/<audio> src pointing at the API sends no Authorization " +
      "header, so it 401s and the only symptom is duration === NaN. Fetch " +
      "with `apiObjectUrl` and hand the element a blob:\n  " +
      offenders.join("\n  "));
});


test("the last recorded part is waited for before the interview looks finished", () => {
  /*
   * `MediaRecorder.stop()` flushes its final buffer asynchronously, and the
   * upload that follows is async too. The page called `cap.current?.stop()`
   * without awaiting it and moved straight to the finished screen, so a
   * candidate who closed the tab lost their answer to the FINAL question with
   * no sign anything had gone wrong.
   */
  const page = readFileSync("src/app/app/interview-live/[id]/page.tsx", "utf8");
  assert.match(page, /await cap\.current\?\.stop\(\)/,
    "the capture's stop() must be awaited — it resolves once the final part " +
      "has uploaded");
  assert.match(page, /setPhase\("saving"\)/,
    "the candidate has to be told the recording is still uploading, not " +
      "shown a finished page over an unfinished upload");
  assert.match(page, /beforeunload/,
    "closing the tab mid-upload loses that part; the browser's own prompt is " +
      "the only thing that can stop it");

  const capture = readFileSync("src/lib/interviewCapture.ts", "utf8");
  assert.match(capture, /async stop\(\): Promise<void>/,
    "stop() must be awaitable");
  assert.match(capture, /get pendingUploads\(\)/,
    "the page needs to know whether anything is still in flight");
});
