/**
 * Reading source in a test, without tripping over the comment that explains it.
 *
 * WHY THIS EXISTS
 * Five guards in this suite scan source for a pattern that must not come back.
 * Every one of them failed, on its first run, against the comment written to
 * explain the fix — because that comment quotes the very string being banned:
 *
 *   no-dead-controls     a comment explaining why something is not a <button>
 *   api-url              the doc comment describing the ${base}${path} concat
 *   money-reconciles     the comment quoting the old rounded formatter
 *   pipeline-stages      the comment quoting the old (b.ai_score ?? 0) sort
 *   (hr-api) exec-brief  the comment quoting "Top retention concern: ..."
 *
 * A guard that fires on the prose describing it teaches people to reword their
 * comments around the test, which is the first step to deleting the test. So
 * strip first, and strip in one place.
 *
 * Whitespace is substituted rather than removed so every reported line number
 * still points at the real line.
 */
import { readFileSync } from "node:fs";
import { readdirSync, statSync } from "node:fs";
import { join } from "node:path";

export function stripComments(src) {
  return src
    .replace(/\/\*[\s\S]*?\*\//g, (m) => m.replace(/[^\n]/g, " "))
    .replace(/(^|[^:])\/\/[^\n]*/g, (m, pre) => pre + " ".repeat(m.length - pre.length));
}

/** File contents with comments blanked. */
export function readCode(path) {
  return stripComments(readFileSync(path, "utf8"));
}

/** Every .ts/.tsx file under `dir`, recursively. */
export function walkSources(dir) {
  const out = [];
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) out.push(...walkSources(p));
    else if (/\.tsx?$/.test(p)) out.push(p);
  }
  return out;
}
