/**
 * The candidate pipeline vocabulary, in one place.
 *
 * There were three of them and none agreed:
 *
 *   hiring page    new · screened · interview · offer · hired · rejected
 *   POST /stage    applied · interview · committee · offer · hired · rejected
 *   what is stored new · screened · hired · rejected · interviewing
 *
 * Both pages bucketed anything they did not recognise into "new", so three
 * candidates stored as "interviewing" were drawn as fresh applicants at the top
 * of the funnel — the worst place to put an unknown, because a full top of
 * funnel reads as a healthy pipeline. And the talent board offered a
 * "→ screened" move that the API answered with 400, on a value the API itself
 * writes when it scores a resume.
 *
 * The API now accepts these six and maps the same synonyms
 * (packages/hr-api/app/api/routers/recruiting.py). This file is the other half
 * of that agreement; keep them equal.
 */
export const PIPELINE_STAGES = [
  "new",
  "screened",
  "interview",
  "offer",
  "hired",
  "rejected",
] as const;

export type Stage = (typeof PIPELINE_STAGES)[number];

/** Older rows and older callers naming the same stages. */
export const STAGE_SYNONYM: Record<string, Stage> = {
  applied: "new",
  interviewing: "interview",
  committee: "interview",
  offered: "offer",
  declined: "rejected",
};

/** The bucket a stored status belongs in. `null` means we do not recognise it. */
export function toStage(status: string): Stage | null {
  const s = (status || "").trim().toLowerCase();
  if ((PIPELINE_STAGES as readonly string[]).includes(s)) return s as Stage;
  return STAGE_SYNONYM[s] ?? null;
}
