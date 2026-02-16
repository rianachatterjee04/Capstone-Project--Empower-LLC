"use client";
import { useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch, apiPatch } from "@/lib/api";
import { Button } from "@/components/Button";
import { Input } from "@/components/Input";
import { Textarea } from "@/components/Textarea";

type Packet = {
  id: string;
  employee_id: string;
  status: string;
  requested_items: Record<string, boolean>;
  submitted_items: Record<string, any>;
  created_at: string;
};

const STEPS = [
  { key: "i9", title: "I-9 verification", fields: ["citizenship_status", "documents"] },
  { key: "w4", title: "W-4 withholding", fields: ["filing_status", "dependents", "additional_withholding"] },
  { key: "ssn", title: "Social Security", fields: ["ssn_last4"] },
  { key: "direct_deposit", title: "Direct deposit", fields: ["bank_name", "routing_number", "account_number"] },
] as const;

export default function OnboardingWizard() {
  const qc = useQueryClient();
  const { data, isLoading, error } = useQuery({
    queryKey: ["packets"],
    queryFn: () => apiFetch<Packet[]>("/onboarding/packets"),
  });

  const packet = useMemo(() => (data ?? [])[0] ?? null, [data]);
  const requested = packet?.requested_items ?? {};
  const availableSteps = STEPS.filter((s) => requested[s.key] !== false);

  const [stepIdx, setStepIdx] = useState(0);
  const step = availableSteps[stepIdx];
  const [form, setForm] = useState<Record<string, any>>({});

  async function saveStep() {
    if (!packet) return;
    const submitted_items = { ...(packet.submitted_items ?? {}), [step.key]: { ...form, saved_at: new Date().toISOString() } };
    await apiPatch<Packet>(`/onboarding/packets/${packet.id}`, { submitted_items });
    await qc.invalidateQueries({ queryKey: ["packets"] });
  }

  async function complete() {
    if (!packet) return;
    await apiPatch<Packet>(`/onboarding/packets/${packet.id}`, { status: "completed" });
    await qc.invalidateQueries({ queryKey: ["packets"] });
  }

  if (isLoading) return <div>Loading…</div>;
  if (error) return <div className="text-red-600">Failed: {(error as Error).message}</div>;

  return (
    <div className="space-y-6">
      <div>
        <div className="text-2xl font-semibold">Onboarding</div>
        <div className="text-sm text-black/60">Packet: {packet ? packet.status : "No packets found (HR must create one)."} </div>
      </div>

      {!packet ? (
        <div className="rounded-2xl border border-black/10 p-4 text-sm text-black/70">
          Ask HR to create an onboarding packet for your employee record.
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <div className="rounded-2xl border border-black/10 p-4">
            <div className="text-sm font-semibold">Steps</div>
            <div className="mt-3 space-y-2">
              {availableSteps.map((s, i) => (
                <button
                  key={s.key}
                  onClick={() => setStepIdx(i)}
                  className={`w-full text-left rounded-xl px-3 py-2 text-sm border ${i === stepIdx ? "border-black bg-black text-white" : "border-black/10 hover:bg-black/5"}`}
                >
                  {s.title}
                </button>
              ))}
            </div>
            <div className="mt-4 text-xs text-black/60">
              Saved data is stored in <code>submitted_items</code> (MVP). Next: file uploads via Supabase Storage + verification workflows.
            </div>
          </div>

          <div className="lg:col-span-2 rounded-2xl border border-black/10 p-4 space-y-4">
            <div className="flex items-center justify-between gap-2">
              <div>
                <div className="text-lg font-semibold">{step.title}</div>
                <div className="text-sm text-black/60">
                  Step {stepIdx + 1} of {availableSteps.length}
                </div>
              </div>
              <div className="flex gap-2">
                <Button variant="secondary" onClick={saveStep}>
                  Save
                </Button>
                <Button onClick={complete}>Mark complete</Button>
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {step.fields.includes("ssn_last4") ? (
                <Input label="SSN last 4" maxLength={4} value={form.ssn_last4 ?? ""} onChange={(e) => setForm({ ...form, ssn_last4: e.target.value })} />
              ) : null}
              {step.fields.includes("bank_name") ? (
                <Input label="Bank name" value={form.bank_name ?? ""} onChange={(e) => setForm({ ...form, bank_name: e.target.value })} />
              ) : null}
              {step.fields.includes("routing_number") ? (
                <Input label="Routing number" value={form.routing_number ?? ""} onChange={(e) => setForm({ ...form, routing_number: e.target.value })} />
              ) : null}
              {step.fields.includes("account_number") ? (
                <Input label="Account number" value={form.account_number ?? ""} onChange={(e) => setForm({ ...form, account_number: e.target.value })} />
              ) : null}
              {step.fields.includes("filing_status") ? (
                <Input label="Filing status" placeholder="Single / Married / HoH" value={form.filing_status ?? ""} onChange={(e) => setForm({ ...form, filing_status: e.target.value })} />
              ) : null}
              {step.fields.includes("dependents") ? (
                <Input label="Dependents" type="number" value={form.dependents ?? ""} onChange={(e) => setForm({ ...form, dependents: e.target.value })} />
              ) : null}
              {step.fields.includes("additional_withholding") ? (
                <Input label="Additional withholding ($)" type="number" value={form.additional_withholding ?? ""} onChange={(e) => setForm({ ...form, additional_withholding: e.target.value })} />
              ) : null}
              {step.fields.includes("citizenship_status") ? (
                <Input label="Citizenship / work authorization status" value={form.citizenship_status ?? ""} onChange={(e) => setForm({ ...form, citizenship_status: e.target.value })} />
              ) : null}
            </div>

            {step.fields.includes("documents") ? (
              <Textarea
                label="I-9 documents (MVP)"
                hint="Next: upload document images to Supabase Storage; AI + HR verification workflow."
                rows={5}
                value={form.documents ?? ""}
                onChange={(e) => setForm({ ...form, documents: e.target.value })}
                placeholder="List documents you will provide (e.g., Passport, Driver's license + SS card)."
              />
            ) : null}

            <div className="flex items-center justify-between">
              <Button variant="secondary" onClick={() => setStepIdx(Math.max(0, stepIdx - 1))} disabled={stepIdx === 0}>
                Back
              </Button>
              <Button onClick={() => setStepIdx(Math.min(availableSteps.length - 1, stepIdx + 1))} disabled={stepIdx === availableSteps.length - 1}>
                Next
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
