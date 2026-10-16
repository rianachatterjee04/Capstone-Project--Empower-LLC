/**
 * The HR document upload page and the server agree, and the upload is sent
 * the way a file has to be sent.
 *
 * WHY THIS IS A TEST
 * Two facts about uploading live in two languages. The page decides which files
 * to offer and refuses oversized ones before sending; the server decides which
 * it will accept. If they drift, a person picks a file the page offers and the
 * server refuses it, or the page blocks a file the server would have taken.
 * Neither shows up in a type check.
 *
 * And a file upload has one way to go wrong silently: setting Content-Type by
 * hand. A multipart body needs the boundary the browser writes itself, so a
 * hand written header sends a body the server cannot read.
 *
 * Run with:  npm run test:ui
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { readCode } from "./_source.mjs";

const PAGE = "src/app/app/hr-knowledge/page.tsx";
const API = "src/lib/api.ts";
const SERVER = "../hr-api/app/services/hr_documents_service.py";

function pageList() {
  const m = readCode(PAGE).match(/ACCEPTED_EXTENSIONS\s*=\s*\[([^\]]*)\]/);
  assert.ok(m, "ACCEPTED_EXTENSIONS not found in the page");
  return [...m[1].matchAll(/"([^"]+)"/g)].map((x) => x[1]);
}

function serverList() {
  const m = readFileSync(SERVER, "utf8").match(/ALLOWED_EXTENSIONS\s*=\s*\(([^)]*)\)/);
  assert.ok(m, "ALLOWED_EXTENSIONS not found in the server");
  return [...m[1].matchAll(/"([^"]+)"/g)].map((x) => x[1]);
}

test("the page offers exactly the file types the server accepts", () => {
  assert.deepEqual([...pageList()].sort(), [...serverList()].sort());
});

test("the page and the server use the same size limit", () => {
  const page = readCode(PAGE).match(/MAX_FILE_BYTES\s*=\s*(\d+)\s*\*\s*1024\s*\*\s*1024/);
  const server = readFileSync(SERVER, "utf8").match(/MAX_FILE_BYTES\s*=\s*(\d+)\s*\*\s*1024\s*\*\s*1024/);
  assert.ok(page && server, "size limit not found on one side");
  assert.equal(page[1], server[1]);
});

test("the upload helper sends credentials and leaves Content-Type to the browser", () => {
  const src = readCode(API);
  const start = src.indexOf("export async function apiUpload");
  assert.ok(start !== -1, "apiUpload is missing");
  const body = src.slice(start, src.indexOf("\n}\n", start));
  assert.match(body, /Authorization/, "the upload sends no Authorization header");
  assert.doesNotMatch(body, /Content-Type/i, "a hand set Content-Type breaks the multipart boundary");
  assert.match(body, /apiPath\(/, "the path must go through apiPath() like every other request");
});

test("the page sends the file through apiUpload, not as JSON", () => {
  const src = readCode(PAGE);
  assert.match(src, /apiUpload</);
  assert.doesNotMatch(src, /JSON\.stringify\([^)]*file/i);
  assert.doesNotMatch(src, /apiPost\([^)]*documents\/upload/);
});

test("the page is linked from the navigation", () => {
  assert.ok(existsSync(PAGE));
  const nav = readFileSync("src/components/nav-config.ts", "utf8");
  assert.ok(nav.includes('"/app/hr-knowledge"'));
});
