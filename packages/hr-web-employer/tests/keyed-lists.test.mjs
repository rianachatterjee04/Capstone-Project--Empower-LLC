/**
 * A .map() never returns a bare fragment.
 *
 * WHY THIS IS A TEST
 * The 9-box calibration grid rendered every row as
 *
 *     {rows.map((r) => (
 *       <>
 *         <div key={`lbl-${r}`}>…</div>
 *         …
 *       </>
 *     ))}
 *
 * and React warned "Each child in a list should have a unique key prop" on
 * every render. The keys on the elements INSIDE the fragment do not satisfy
 * it: the keyed thing has to be what map() returns, and `<>` cannot take a
 * key. The fix is `<Fragment key={…}>`.
 *
 * This is the second key defect found in one pass through the app -- the
 * skills graph rendered two `postgres` rows under the same key, because a
 * skill can belong to two clusters. Both are the same class of bug: React
 * quietly reuses or drops a row, and what the reader sees is not what the data
 * says. Neither fails a build, neither throws, and both are invisible unless
 * someone happens to have the console open.
 *
 * Run with:  npm run test:ui
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { readCode, walkSources } from "./_source.mjs";

/** `.map(... => (` immediately followed by a bare `<>`. */
const BARE_FRAGMENT_IN_MAP =
  /\.map\s*\([^)]*\)\s*=>\s*\(\s*<>/g;

function offenders(source, file) {
  const found = [];
  for (const m of source.matchAll(BARE_FRAGMENT_IN_MAP)) {
    const line = source.slice(0, m.index).split("\n").length;
    found.push(`${file}:${line}`);
  }
  return found;
}

test("no .map() returns a bare fragment, which cannot carry a key", () => {
  const bad = [];
  for (const file of walkSources("src")) {
    bad.push(...offenders(readCode(file), file));
  }
  assert.deepEqual(bad, [],
    "these render a list whose top-level element is `<>`. React cannot key a " +
    "bare fragment, so it warns and may reuse or drop rows on re-render. Use " +
    "`<Fragment key={...}>`:\n  " + bad.join("\n  "));
});

test("the detector fires on the original calibration defect", () => {
  // CONTROL. The exact shape that was in calibration/page.tsx.
  const planted = `
    {rows.map((r) => (
      <>
        <div key={\`lbl-\${r}\`}>{r}</div>
      </>
    ))}
  `;
  assert.equal(offenders(planted, "planted.tsx").length, 1,
    "the scan did not flag a bare fragment returned from map()");
});

test("the detector accepts a keyed Fragment and a keyed element", () => {
  // CONTROL, the other direction. A guard that flags the correct form is worse
  // than none: it teaches people to skip the rule.
  const fine = `
    {rows.map((r) => (
      <Fragment key={r}>
        <div>{r}</div>
      </Fragment>
    ))}
    {cols.map((c) => (
      <div key={c}>{c}</div>
    ))}
  `;
  assert.deepEqual(offenders(fine, "fine.tsx"), []);
});
