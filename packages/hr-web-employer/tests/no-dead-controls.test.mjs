/**
 * No control on any page may look interactive and do nothing.
 *
 * WHY THIS IS A TEST AND NOT A REVIEW NOTE
 * Three of them shipped: "Export evidence", "Re-run scan", "Export coaching
 * plan" -- all rendered as real buttons in page headers, all inert. A
 * decorative control is worse than a missing one, because whoever clicks it
 * learns that the other controls might also be decorative, and that doubt does
 * not stay contained to the button they tried.
 *
 * Run with:  node --test tests/
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
    else if (p.endsWith(".tsx")) out.push(p);
  }
  return out;
}

const BUTTON = /<(button|Action|Button)\b((?:[^>]|\n)*?)>/gs;

test("every button either does something or says why it cannot", () => {
  const offenders = [];
  for (const file of walk("src/app")) {
    const raw = readFileSync(file, "utf8");
    const src = stripComments(raw);
    for (const m of src.matchAll(BUTTON)) {
      const attrs = m[2];
      const interactive =
        attrs.includes("onClick") ||
        attrs.includes('type="submit"') ||
        attrs.includes("type='submit'") ||
        attrs.includes("disabled");
      if (interactive) continue;
      const line = src.slice(0, m.index).split("\n").length;
      const label = raw.slice(m.index + m[0].length).split("<")[0].trim();
      offenders.push(`${file}:${line} — ${label.slice(0, 50) || "(no label)"}`);
    }
  }
  assert.deepEqual(
    offenders,
    [],
    "controls that render as buttons and do nothing:\n  " +
      offenders.join("\n  "),
  );
});


test("the comment stripper does not hide a real dead control", () => {
  // A guard that skips comments could skip too much. This proves the scan
  // still sees code on the same line as, and after, a comment.
  const sample = [
    'const a = 1; // <button>not a control</button>',
    '/* <button>also not one</button> */',
    '<button>REAL AND DEAD</button>',
  ].join("\n");
  const stripped = stripComments(sample);
  const found = [...stripped.matchAll(BUTTON)];
  assert.equal(found.length, 1, "expected exactly the one real button");
  assert.equal(
    stripped.split("\n").length,
    sample.split("\n").length,
    "stripping changed the line count, so reported line numbers would be wrong",
  );
});


test("every capture state the recorder can report has UI wording", () => {
  // The recorder can end in five states. The page named three of them and let
  // DEVICE_LOST and ERROR fall through to a bare "not recording" -- so a
  // candidate whose camera was unplugged mid-answer, or whose recorder threw,
  // was told nothing about either, while the app knew exactly what happened.
  const capture = readFileSync("src/lib/interviewCapture.ts", "utf8");
  const page = readFileSync(
    "src/app/app/interview-live/[id]/page.tsx", "utf8");

  const union = capture.slice(
    capture.indexOf("export type CaptureState"),
    capture.indexOf(";", capture.indexOf("export type CaptureState")));
  const states = [...union.matchAll(/"([A-Z_]+)"/g)].map((m) => m[1]);

  assert.ok(states.length >= 5, `only parsed ${states.length} capture states`);

  const unhandled = states.filter(
    (s) => !["IDLE", "REQUESTING_PERMISSION", "RECORDING", "STOPPED"].includes(s)
           && !page.includes(`"${s}"`));
  assert.deepEqual(
    unhandled, [],
    `these capture states have no wording on the interview page: ${unhandled}`,
  );
});


test("no buyer-facing screen carries engineering jargon", () => {
  // "Pipeline + AI screening controls (MVP)." and a field labelled "Resume
  // text (MVP)" were on the recruiting page. A buyer reading MVP on the screen
  // they are being sold concludes the rest is provisional too, and they are not
  // wrong to.
  // "coming soon" is NOT on this list. As an inline label beside an item that
  // cannot be installed yet, or a footnote saying automatic progress feeding is
  // not wired, it is honest and useful. What is not acceptable is a whole SCREEN
  // that says it -- that is a dead nav destination, and it is caught by the next
  // test instead, which is a different problem needing a different answer.
  //
  // The second group is repo-and-process talk, which leaks the same way. The
  // Total comp panel carried "(Shown here since there's no standalone profile
  // page on this branch.)" -- a sentence about our git history, on the screen
  // where a buyer reads an employee's pay. Two more said feature wiring was
  // "stubbed". Each was HONEST, which is why it survived; the fix is to say the
  // same true thing in the reader's words ("the file itself has not been
  // uploaded"), not to delete the disclosure.
  const JARGON = [
    /\(MVP\)/,
    /\bTODO\b/,
    /\bFIXME\b/,
    /\bWIP\b/,
    /\blorem ipsum\b/i,
    /\bplaceholder text\b/i,
    /future sprint/i,
    /\bsprint\b/i,
    /\bthis branch\b/i,
    /\bmonorepo\b/i,
    /\bhard-?coded\b/i,
    /\bstubbed?\b/i,
    /\bnot implemented\b/i,
    /\bmock data\b/i,
    /\bdummy\b/i,
  ];

  // Route handlers under src/app/api are server code, not screens: a localhost
  // default or a "stub" comment there is never read by a buyer.
  const screens = walk("src/app").filter((f) => !f.startsWith("src/app/api/"));

  const offenders = [];
  for (const file of screens) {
    const src = stripComments(readFileSync(file, "utf8"));
    for (const pattern of JARGON) {
      const m = src.match(pattern);
      if (m) offenders.push(`${file}: ${m[0]}`);
    }
  }
  assert.deepEqual(offenders, [], `engineering jargon on a screen:\n  ${offenders.join("\n  ")}`);

  // CONTROL. Every pattern must still match the thing it was added for --
  // otherwise a rewritten regex reports a clean codebase forever.
  const SAMPLES = {
    "(MVP)": "Pipeline + AI screening controls (MVP).",
    TODO: "TODO: wire this",
    FIXME: "FIXME later",
    WIP: "WIP screen",
    "lorem ipsum": "lorem ipsum dolor",
    "placeholder text": "placeholder text here",
    "future sprint": "coming in a future sprint",
    sprint: "next sprint",
    "this branch": "no standalone profile page on this branch",
    monorepo: "lives in the monorepo",
    hardcoded: "the rate is hard-coded",
    stubbed: "upload wiring is stubbed",
    "not implemented": "not implemented yet",
    "mock data": "Showing sample mock data",
    dummy: "dummy value",
  };
  const dead = Object.entries(SAMPLES).filter(
    ([, sample]) => !JARGON.some((p) => p.test(sample)));
  assert.deepEqual(dead.map(([k]) => k), [],
    "these jargon patterns no longer match the copy they were written for");
});


test("a missing score is words, not a dash", () => {
  // "AI score: —" cannot be read. It might mean not screened, screened and
  // scored zero, or screening failed, and those are three different facts.
  const src = readFileSync("src/app/app/recruiting/page.tsx", "utf8");
  assert.ok(
    src.includes("Not screened yet"),
    "the recruiting pipeline does not say what an absent score means",
  );
  assert.ok(
    !/AI score:\s*<span[^>]*>\{c\.ai_score \?\? "—"\}/.test(src),
    "the bare em-dash score is back",
  );
});


test("no nav destination is a placeholder screen", () => {
  // /app/compliance was an emoji, the words "Coming Soon", and "will be
  // available in a future sprint". A buyer clicking Compliance in the sidebar
  // during a demo got that, and whoever sees it stops trusting the other nav
  // items -- a high price for one unwritten screen.
  const offenders = [];
  for (const file of walk("src/app")) {
    const src = stripComments(readFileSync(file, "utf8"));
    // Rough proxy for "there is nothing else on this page": a short file whose
    // visible content is dominated by a coming-soon message.
    const comingSoon = /coming\s+soon/i.test(src);
    if (!comingSoon) continue;
    const jsxText = (src.match(/>[^<>{}]{12,}</g) || []).join(" ");
    if (jsxText.length < 400) {
      offenders.push(`${file} (only ${jsxText.length} chars of visible text)`);
    }
  }
  assert.deepEqual(
    offenders, [],
    `these screens are little more than a coming-soon placeholder:\n  ` +
      offenders.join("\n  ") +
      `\nSay what DOES exist and link to it, and state plainly what does not.`,
  );
});
