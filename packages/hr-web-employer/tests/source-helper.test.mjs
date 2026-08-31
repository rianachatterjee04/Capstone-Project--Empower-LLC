/**
 * The comment stripper does not hide real code, and does hide comments.
 *
 * Both halves matter. A stripper that is too eager blinds every guard that
 * depends on it — which would turn five failing tests into five silently
 * passing ones, the worst possible outcome for a suite whose whole job is to
 * notice things.
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { stripComments } from "./_source.mjs";

test("comments are blanked", () => {
  assert.ok(!stripComments('// matchScore={78}\n').includes("matchScore"));
  assert.ok(!stripComments('/* maximumFractionDigits: 0 */').includes("maximumFractionDigits"));
  assert.ok(!stripComments('/**\n * Top retention concern\n */').includes("retention"));
});

test("real code survives", () => {
  const src = 'const x = { matchScore: 78 };\nconst url = "https://a.example/b";';
  const out = stripComments(src);
  assert.ok(out.includes("matchScore: 78"), "stripped real code");
  assert.ok(out.includes("https://a.example/b"),
    "a URL's // was treated as a line comment, which would blank the rest of the line");
});

test("line numbers are preserved", () => {
  const src = "a\n// comment\nb";
  assert.equal(stripComments(src).split("\n").length, src.split("\n").length);
  assert.equal(stripComments(src).split("\n")[2], "b");
});
