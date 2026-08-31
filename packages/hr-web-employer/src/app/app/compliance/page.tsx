import Link from "next/link";

/**
 * A NAV ITEM THAT LEADS NOWHERE IS WORSE THAN ONE THAT IS NOT THERE.
 *
 * This screen was an emoji, the words "Coming Soon", and "will be available in
 * a future sprint" -- a buyer clicking Compliance in the sidebar during a demo
 * got a placeholder and the word "sprint". Whoever sees that stops trusting the
 * other nav items, which is a high price for a screen nobody had written yet.
 *
 * What exists today genuinely IS compliance work; it is just filed under other
 * names. So this says what is real, links to it, and states plainly what is not
 * built -- which is the same thing the rest of the product does with evidence
 * it does not have.
 */
const AVAILABLE = [
  {
    href: "/app/trucking",
    title: "Driver and carrier eligibility",
    body: "Credentials are checked before dispatch, not after. An expired " +
      "medical card refuses the assignment, and a credential that expires " +
      "mid-load refuses it too — valid at pickup and expired at delivery is a " +
      "driver unlicensed on the road.",
  },
  {
    href: "/app/audit",
    title: "Audit evidence",
    body: "Decisions carry the evidence they were made on, and documents carry " +
      "a hash that is re-checked rather than trusted.",
  },
  {
    href: "/app/approvals",
    title: "Approvals and authority",
    body: "Who may approve what, and the record of who did.",
  },
  {
    href: "/app/ombudsman",
    title: "Employee relations",
    body: "A reporting channel where managers are excluded by default, because " +
      "the person a report is about is often the person who would read it.",
  },
];

export default function Compliance() {
  return (
    <div className="space-y-6">
      <div>
        <div className="text-2xl font-semibold">Compliance</div>
        <div className="mt-1 text-sm text-black/50">
          What Fintra checks, refuses and keeps evidence of.
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        {AVAILABLE.map((c) => (
          <Link
            key={c.href}
            href={c.href}
            className="rounded-2xl border border-black/10 bg-white p-5 shadow-sm hover:border-black/25"
          >
            <div className="font-semibold">{c.title}</div>
            <div className="mt-2 text-sm text-black/60">{c.body}</div>
          </Link>
        ))}
      </div>

      <div className="rounded-2xl border border-black/10 bg-white p-5 shadow-sm">
        <div className="font-semibold">Not built</div>
        <div className="mt-2 text-sm text-black/60">
          Packaged regulatory presets — HIPAA, SOC 2, GDPR and the rest — do not
          exist here. Nothing on this screen should be read as certifying
          anything against a named framework. The controls above are real and
          they are enforced; a preset that mapped them to a framework is a
          different piece of work and has not been done.
        </div>
      </div>
    </div>
  );
}
