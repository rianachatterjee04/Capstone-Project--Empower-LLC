/**
 * Where a timecode lands in a multi-part recording.
 *
 * This is the arithmetic behind "click any assessment and the recording plays
 * the moment the candidate said it". It is small, and it is the calculation
 * most able to be quietly wrong: a bad offset does not throw, it plays a
 * DIFFERENT moment, and the recruiter believes they are watching the evidence.
 *
 * It lives here rather than inside the review page so it can be tested. A pure
 * function nobody can call is a pure function nobody has checked.
 *
 * TWO CLOCKS
 * An evidence timecode comes from the answer boundary the application recorded.
 * A part's offset and duration come from the recorder. When they disagree --
 * a part that never uploaded, a recorder that stopped early -- a timecode can
 * fall in a GAP between parts or past the end. Both return null, because the
 * only alternatives are to clamp (play the wrong moment, confidently) or to
 * guess (the same thing with extra steps).
 */

export type TimelinePart = {
  part: number;
  timeline_offset_ms: number;
  duration_ms: number | null;
};

/** Where the assembled recording ends, in ms. Parts need not be ordered. */
export function timelineEndMs(parts: readonly TimelinePart[]): number {
  return parts.reduce(
    (end, p) => Math.max(end, p.timeline_offset_ms + (p.duration_ms ?? 0)),
    0,
  );
}

export type SeekTarget<P extends TimelinePart> = {
  part: P;
  /** Seconds INTO that part -- what `video.currentTime` takes. */
  withinSeconds: number;
};

/**
 * Locate `ms` on the assembled timeline.
 *
 * Intervals are half-open, [offset, offset + duration): a timecode exactly on a
 * boundary belongs to the LATER part, so no timecode matches two parts and none
 * falls between two adjacent ones.
 *
 * Returns null when the timecode is not covered -- before the start, past the
 * end, inside a gap left by a missing part, or when there are no parts at all.
 */
export function locateSeek<P extends TimelinePart>(
  parts: readonly P[], ms: number,
): SeekTarget<P> | null {
  if (!Number.isFinite(ms) || ms < 0) return null;
  for (const p of parts) {
    const start = p.timeline_offset_ms;
    const end = start + (p.duration_ms ?? 0);
    if (ms >= start && ms < end) {
      return { part: p, withinSeconds: (ms - start) / 1000 };
    }
  }
  return null;
}
