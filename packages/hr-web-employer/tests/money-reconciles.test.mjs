/**
 * The trucking board shows money at a precision where its figures reconcile.
 *
 * WHY THIS IS A TEST
 * The working-capital block read receivable $9,276, payable $5,174, gap
 * -$4,103. Every one of those roundings is correct on its own — the cents are
 * 927625, 517358 and -410267 — but they sit side by side and 9,276 - 5,174 is
 * 4,102. The two payable tiles above ($4,378 + $796) summed to $5,174 against a
 * block reading $5,173.58.
 *
 * Nothing was miscalculated. The API is exact in cents and
 * test_the_rows_reconcile_with_the_tile already proves every tile equals the
 * rows behind it. The page simply displayed a sum and its parts at a precision
 * that could not agree, on a screen whose entire promise is "every number
 * opens" — and a CFO who catches that stops trusting the tiles above it.
 *
 * So: on this board, no rounded currency formatter.
 *
 * Run with:  npm run test:ui
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { stripComments } from "./_source.mjs";

const PAGE = "src/app/app/trucking/page.tsx";

test("the trucking board defines no rounded currency formatter", () => {
  const src = stripComments(readFileSync(PAGE, "utf8"));
  const rounded = [...src.matchAll(/maximumFractionDigits:\s*0/g)].map(
    (m) => src.slice(0, m.index).split("\n").length);
  assert.deepEqual(rounded, [],
    `${PAGE} rounds currency to whole dollars at line(s) ${rounded.join(", ")}. ` +
    "Figures on this board are summed against each other and against their " +
    "drill rows; rounded, they disagree.");
});

test("every currency figure on the board goes through moneyExact", () => {
  const src = stripComments(readFileSync(PAGE, "utf8"));
  // Any call formatting a *_cents VALUE must be the exact formatter. The
  // argument has to start like an identifier: the first version of this also
  // matched key.endsWith("_cents") and a regex literal, which are string
  // handling, not currency formatting.
  const calls = [...src.matchAll(/\b(\w+)\(\s*[A-Za-z_$][\w.$]*_cents\b/g)].map((m) => m[1]);
  const wrong = [...new Set(calls)].filter((f) => f !== "moneyExact" && f !== "Number");
  assert.deepEqual(wrong, [],
    `these format a _cents value on the trucking board but are not moneyExact: ${wrong}`);

  // CONTROL: the scan must actually be finding the call sites.
  assert.ok(calls.length >= 5,
    `only ${calls.length} _cents formatting calls found — the scan has rotted ` +
    "and the assertion above proves nothing");
});
