"use client";
import { useState } from "react";
import { apiPost } from "@/lib/api";
import { Button } from "@/components/Button";
import { Input } from "@/components/Input";

const DEFAULT = `# Example policy DSL
SLA: harassment_report.review <= 48h
ESCALATE: to=hr,legal when severity>=high
NOTIFY: to=exec when severity>=critical
`;

export default function PolicyExecPage() {
  const [name, setName] = useState("Harassment SLA Policy");
  const [policyText, setPolicyText] = useState(DEFAULT);
  const [rules, setRules] = useState<any[]>([]);
  const [dry, setDry] = useState<any[]>([]);

  async function parse() {
    const r = await apiPost("/policies2/parse", { policy_text: policyText });
    setRules(r.rules || []);
  }

  async function create() {
    const r = await apiPost("/policies2/create", { name, policy_text: policyText, scope: "org" });
    return r;
  }

  async function dryRun() {
    const r = await apiPost("/policies2/dry-run", { policy_text: policyText, context: { severity: "high" } });
    setDry(r.results || []);
  }

  return (
    <div className="space-y-6">
      <div>
        <div className="text-2xl font-semibold">Policy DSL → Execution</div>
        <div className="text-sm text-black/60">This is the demo that beats Workday: policies become executable SLAs + escalations.</div>
      </div>

      <div className="rounded-2xl border border-black/10 p-4 space-y-3">
        <Input label="Policy name" value={name} onChange={(e) => setName(e.target.value)} />
        <label className="block text-sm font-medium">Policy DSL</label>
        <textarea className="w-full rounded-xl border border-black/10 p-3 font-mono text-xs min-h-[200px]"
          value={policyText} onChange={(e) => setPolicyText(e.target.value)} />
        <div className="flex gap-2">
          <Button onClick={parse}>Parse</Button>
          <Button onClick={dryRun}>Dry run</Button>
          <Button onClick={create}>Create + Version</Button>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="rounded-2xl border border-black/10 p-4">
          <div className="text-sm font-semibold">Parsed rules</div>
          <pre className="mt-3 text-xs bg-black/5 rounded-xl p-3 overflow-auto">{JSON.stringify(rules, null, 2)}</pre>
        </div>
        <div className="rounded-2xl border border-black/10 p-4">
          <div className="text-sm font-semibold">Dry run output</div>
          <pre className="mt-3 text-xs bg-black/5 rounded-xl p-3 overflow-auto">{JSON.stringify(dry, null, 2)}</pre>
        </div>
      </div>
    </div>
  );
}
