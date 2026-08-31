/**
 * No component calls a hook after an early return.
 *
 * WHY THIS IS A TEST
 * /app/equity rendered the word "Not Found" under a header promising a
 * fully-diluted cap table, 409A and ASC 718 expense posting straight to the
 * ledger. The cause was a doubled "/api/api/" prefix (see api-url.test.mjs).
 *
 * Fixing the URL did not fix the page. It revealed a SECOND defect the first
 * one had been hiding: CapTableView called useState, then `if (!cap) return
 * null`, then useMemo. While every request 404'd, `cap` was always null, the
 * useMemo was never reached, and the hook order never varied. The moment real
 * data arrived React threw "Rendered more hooks than during the previous
 * render" and the screen went blank.
 *
 * That is the shape worth guarding: a latent crash that is unreachable, and
 * therefore invisible, until the day the feature starts working.
 *
 * eslint-plugin-react-hooks already detects this. The risk is not that the rule
 * is wrong -- it is that the rule silently stops running (parser swapped,
 * plugin dropped from the shared config, a new file type not linted) and this
 * test keeps reporting zero violations forever. So the test plants the exact
 * equity defect on every run and fails if the detector does NOT flag it.
 *
 * Run with:  npm run test:ui
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { writeFileSync, unlinkSync, mkdirSync, rmdirSync } from "node:fs";

const RULE = "react-hooks/rules-of-hooks";

/** eslint over `target`, returning only RULE messages. Never throws on lint findings. */
function violations(target) {
  let out;
  try {
    out = execFileSync("npx", ["eslint", target, "--ext", ".ts,.tsx", "-f", "json"], {
      encoding: "utf8",
      stdio: ["ignore", "pipe", "pipe"],
    });
  } catch (e) {
    // eslint exits non-zero when it finds errors; the JSON is still on stdout.
    out = e.stdout;
  }
  assert.ok(out && out.trim().startsWith("["),
    `eslint produced no JSON report for ${target} -- the linter itself is broken:\n${out}`);
  return JSON.parse(out).flatMap((f) =>
    f.messages
      .filter((m) => m.ruleId === RULE)
      .map((m) => `${f.filePath.replace(/.*hr-web-employer\//, "")}:${m.line} ${m.message}`),
  );
}

// CONTROL. Runs first: if the detector is dead, say so before reporting "clean".
// The planted control goes in tests/, NOT src/.
//
// It used to be written to src/__hooks_order_control__.tsx, and the full gate
// failed once with "no hook is called after an early return anywhere in src" —
// because a second run of this suite had planted ITS control file while the
// first run was sweeping src. The defect was real; it just belonged to the
// other process. A test that fails when run twice at once is a flaky test, and
// a flaky guard is worse than none: it teaches people that a red build here
// means nothing.
//
// The filename also carries the pid, so two runs cannot collide even here.
const CONTROL_DIR = "tests/__hooks_control__";

test("the rules-of-hooks detector actually fires (planted equity defect)", () => {
  mkdirSync(CONTROL_DIR, { recursive: true });
  const planted = `${CONTROL_DIR}/planted_${process.pid}.tsx`;
  writeFileSync(planted,
    '"use client";\n' +
    'import { useMemo, useState } from "react";\n' +
    "// The exact shape that blanked /app/equity: useState, early return, useMemo.\n" +
    "export function PlantedControl({ cap }: { cap: { rows: number[] } | null }) {\n" +
    "  const [fd, setFd] = useState(true);\n" +
    "  if (!cap) return null;\n" +
    "  const n = useMemo(() => cap.rows.length + (fd ? 1 : 0), [cap.rows, fd]);\n" +
    "  return <div onClick={() => setFd((v) => !v)}>{n}</div>;\n" +
    "}\n");
  try {
    const found = violations(planted);
    assert.ok(found.length > 0,
      "eslint-plugin-react-hooks did NOT flag a hook called after an early return.\n" +
      "The rule is not running, so the clean result below means nothing.");
  } finally {
    // Remove only THIS run's file, and the directory only if it is now empty.
    // A recursive rm here deleted the other runs' planted files mid-lint and
    // they failed with ENOENT — the first fix swapped one concurrency bug for
    // another. Each run owns exactly what it created.
    try {
      unlinkSync(planted);
    } catch {
      /* already gone */
    }
    try {
      rmdirSync(CONTROL_DIR);
    } catch {
      /* another run still has a file in here; it will remove the directory */
    }
  }
});

// A planted control is a deliberate defect. If one is ever found under src/ --
// left by a crashed pre-fix run, or by a future edit that moves the control back
// there -- the honest report is "the guard littered", NOT "the product is
// broken". The full gate once went red with exactly that confusion, and the
// person reading the log had no way to tell which it was. So: assert on it
// separately, in its own words, and keep it out of the product sweep.
const IS_CONTROL = (v) => /__hooks_(order_)?control__/.test(v);

test("no planted control file is left behind under src", () => {
  const strays = violations("src").filter(IS_CONTROL);
  assert.deepEqual(strays, [],
    "a planted rules-of-hooks control file is sitting in src/.\n" +
    "This is a leftover from this test suite, NOT a defect in the product:\n  " +
    strays.join("\n  ") + "\nDelete it; the sweep below deliberately ignores it.");
});

test("no hook is called after an early return anywhere in src", () => {
  const found = violations("src").filter((v) => !IS_CONTROL(v));
  assert.deepEqual(found, [],
    "hooks called conditionally -- these components crash with " +
    '"Rendered more hooks than during the previous render" the first time ' +
    "the early-return branch is not taken:\n  " + found.join("\n  "));
});
