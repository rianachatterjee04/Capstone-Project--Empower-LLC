/**
 * No real person's contact details ship in this repo.
 *
 * WHY THIS EXISTS
 * The employer demo login compared against a hardcoded `family032544@gmail.com`
 * -- a real personal mailbox. It worked, so nobody looked at it again, and it
 * rode along into every clone of the repo including the copy prepared for an
 * outside evaluator. A login hint only ever needed to be *a string*; that it
 * was somebody's actual address was an accident that persisted because no
 * control was watching for it.
 *
 * WHAT COUNTS AS A VIOLATION
 * An address at a real consumer mail provider, or a real phone number shape,
 * appearing in source. Addresses on reserved test TLDs (.test, .invalid,
 * .example, example.com) are exactly what a demo credential should be, so they
 * pass. Seeded demo people use @northwind.test for the same reason.
 *
 * This guard reads code with comments stripped, so the paragraph above -- which
 * necessarily quotes the banned address -- does not fire it.
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { join } from "node:path";
import { walkSources, readCode, stripComments } from "./_source.mjs";

const SRC = join(import.meta.dirname, "..", "src");

const CONSUMER_MAIL =
  /[A-Za-z0-9._%+-]+@(?:gmail|googlemail|yahoo|ymail|hotmail|outlook|live|msn|aol|icloud|me|mac|proton|protonmail|gmx|zoho|yandex|mail)\.[A-Za-z]{2,}/g;

/**
 * Fold `"a" + "b"` into `"ab"` before matching.
 *
 * The positive control below plants the address as a concatenation, and the
 * first version of this detector missed it -- the regex wants a contiguous
 * string and concatenation breaks it into three literals. Splitting a literal
 * is also the one-line move that gets a hardcoded address past a naive
 * scanner, so the detector folds the pieces back together first.
 */
function foldConcatenatedStrings(code) {
  let prev;
  do {
    prev = code;
    code = code.replace(/"([^"\n]*)"\s*\+\s*"([^"\n]*)"/g, (_m, a, b) => `"${a}${b}"`);
    code = code.replace(/'([^'\n]*)'\s*\+\s*'([^'\n]*)'/g, (_m, a, b) => `'${a}${b}'`);
  } while (code !== prev);
  return code;
}

function findPersonalEmails(code) {
  return [...foldConcatenatedStrings(code).matchAll(CONSUMER_MAIL)].map((m) => m[0]);
}

test("no consumer-provider email address appears anywhere in src", () => {
  const hits = [];
  for (const file of walkSources(SRC)) {
    for (const addr of findPersonalEmails(readCode(file))) {
      hits.push(`${file.slice(SRC.length + 1)}: ${addr}`);
    }
  }
  assert.deepEqual(
    hits,
    [],
    `personal email address(es) would ship to an outside evaluator:\n  ${hits.join("\n  ")}`,
  );
});

test("the demo credential is on a reserved test TLD", () => {
  const code = readCode(join(SRC, "lib", "session.ts"));
  const m = code.match(/DEMO_EMAIL\s*=\s*\([^)]*\|\|\s*"([^"]+)"/);
  assert.ok(m, "could not read the default DEMO_EMAIL out of session.ts");
  assert.match(
    m[1],
    /@(?:[A-Za-z0-9-]+\.)*(?:test|invalid|example)$|@example\.(?:com|org|net)$/,
    `default demo credential ${m[1]} is not on a reserved test TLD`,
  );
});

/* --- controls: the detector must fire on a real violation, and must not fire
   on the forms that are legitimately fine. ------------------------------- */

test("CONTROL positive: the detector catches an address it must catch", () => {
  const planted = 'const DEMO = "someone" + "@" + "gmail.com";';
  assert.equal(findPersonalEmails(planted).length, 1);
  assert.equal(findPersonalEmails('x = "a.person@yahoo.co.uk"').length, 1);
});

test("CONTROL negative: reserved-TLD and seed addresses are not flagged", () => {
  assert.deepEqual(findPersonalEmails('x = "demo@fintra-hr.test"'), []);
  assert.deepEqual(findPersonalEmails('x = "ada@northwind.test"'), []);
  assert.deepEqual(findPersonalEmails('x = "someone@example.com"'), []);
});

test("CONTROL: a banned address inside a comment does not fire the guard", () => {
  const inComment = '// we used to hardcode nobody@gmail.com here\nconst x = 1;';
  assert.deepEqual(findPersonalEmails(stripComments(inComment)), []);
  assert.equal(findPersonalEmails(inComment).length, 1, "and the raw text does contain one");
});
