/**
 * Turn what is on screen into a file the user can keep.
 *
 * WHY THIS EXISTS
 * Three header buttons -- "Export evidence", "Export coaching plan",
 * "Re-run scan" -- rendered as real controls and did nothing at all. A
 * decorative control is worse than a missing one: it teaches whoever clicked
 * it that the other controls might also be decorative, and that doubt does not
 * stay contained to the button they tried.
 *
 * The export is of the rows the page is CURRENTLY showing, including whether
 * those rows came from the API or from the sample data, because a CSV that
 * does not say which it was is a spreadsheet somebody will later quote.
 */

function csvCell(v: unknown): string {
  if (v === null || v === undefined) return "";
  const s = typeof v === "object" ? JSON.stringify(v) : String(v);
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

export function toCsv(rows: Record<string, unknown>[]): string {
  if (!rows.length) return "";
  const cols = Array.from(
    rows.reduce((set, r) => {
      Object.keys(r).forEach((k) => set.add(k));
      return set;
    }, new Set<string>()),
  );
  return [
    cols.join(","),
    ...rows.map((r) => cols.map((c) => csvCell(r[c])).join(",")),
  ].join("\n");
}

/** Download `rows` as CSV, with a provenance line the reader cannot miss. */
export function downloadCsv(
  filename: string,
  rows: Record<string, unknown>[],
  opts: { live?: boolean; note?: string } = {},
): void {
  const stamp = new Date().toISOString();
  const provenance =
    `# exported ${stamp}\n` +
    `# source: ${opts.live ? "live API data" : "SAMPLE DATA — not from this organisation's records"}\n` +
    (opts.note ? `# ${opts.note}\n` : "");
  const blob = new Blob([provenance + toCsv(rows)], {
    type: "text/csv;charset=utf-8",
  });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
