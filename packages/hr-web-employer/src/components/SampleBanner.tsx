"use client";

/**
 * Says, on the screen, that the people below are invented.
 *
 * WHY THIS EXISTS
 * Eight services emit the same cast of sample people -- Avery Chen, Sam Rivera,
 * Jordan Patel and the rest -- and until recently none of them said so. A card
 * carrying a name, a title, an attrition band and a succession rating is
 * indistinguishable from a real colleague once it is on screen.
 *
 * The API now marks them (`is_sample` per record, `all_sample` on the
 * envelope). A marker nobody renders is not a disclosure, so this is the other
 * half: the same wording everywhere, so a reader learns the convention once.
 */
import { Surface } from "@/components/ds";

export function SampleBanner({
  what,
  note,
}: {
  /** Plural noun for what is being shown: "people", "matches", "tasks". */
  what: string;
  /** Optional sentence from the API's own provenance field. */
  note?: string | null;
}) {
  return (
    <Surface pad="md">
      <div className="fp-eyebrow">Sample {what}</div>
      <p className="mt-1 text-sm text-body">
        {note ??
          `These ${what} are illustrative examples, not ${what} from your own records.`}
      </p>
    </Surface>
  );
}
