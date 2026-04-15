"use client";
import { useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch, apiPatch, apiPost } from "@/lib/api";
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

type PacketRequest = {
  id: string;
  status: string;
  created_at: string;
  message?: string | null;
  requester_email?: string | null;
};

const STEPS = [
  { key: "i9", title: "I-9 verification", fields: ["citizenship_status", "documents"] as string[] },
  { key: "w4", title: "W-4 withholding", fields: ["filing_status", "dependents", "additional_withholding"] as string[] },
  { key: "ssn", title: "Social Security", fields: ["ssn_last4"] as string[] },
  { key: "direct_deposit", title: "Direct deposit", fields: ["bank_name", "routing_number", "account_number"] as string[] },
];

export default function OnboardingWizard() {
  const qc = useQueryClient();
  const { data, isLoading, error } = useQuery({
    queryKey: ["packets"],
    queryFn: () => apiFetch<Packet[]>("/onboarding/packets"),
  });

  const { data: myRequest, isLoading: reqLoading } = useQuery({
    queryKey: ["onboarding-packet-request-me"],
    queryFn: () => apiFetch<PacketRequest | null>("/onboarding/packet-requests/me"),
    enabled: !isLoading && (data ?? []).length === 0,
  });

  const packet = useMemo(() => (data ?? [])[0] ?? null, [data]);
  const requested = packet?.requested_items ?? {};
  const availableSteps = STEPS.filter((s) => requested[s.key] !== false);

  const [stepIdx, setStepIdx] = useState(0);
  const step = availableSteps[stepIdx];
  const [form, setForm] = useState<Record<string, any>>({});
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState<string | null>(null);
  const [requestNote, setRequestNote] = useState("");
  const [requestBusy, setRequestBusy] = useState(false);
  const [requestErr, setRequestErr] = useState<string | null>(null);

  const isLastStep = stepIdx === availableSteps.length - 1;

  async function saveStep() {
    if (!packet) return;
    setSaving(true);
    setSaveMsg(null);
    try {
      const submitted_items = {
        ...(packet.submitted_items ?? {}),
        [step.key]: { ...form, saved_at: new Date().toISOString() },
      };
      await apiPatch<Packet>(`/onboarding/packets/${packet.id}`, { submitted_items });
      await qc.invalidateQueries({ queryKey: ["packets"] });
      setSaveMsg("Saved!");
    } catch (e) {
      setSaveMsg("Error saving: " + (e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  async function saveAndNext() {
    await saveStep();
    setStepIdx((i) => Math.min(i + 1, availableSteps.length - 1));
    setForm({});
    setSaveMsg(null);
  }

  async function finish() {
    if (!packet) return;
    setSaving(true);
    setSaveMsg(null);
    try {
      // Save current step first
      const submitted_items = {
        ...(packet.submitted_items ?? {}),
        [step.key]: { ...form, saved_at: new Date().toISOString() },
      };
      await apiPatch<Packet>(`/onboarding/packets/${packet.id}`, { submitted_items });
      // Then mark as completed
      await apiPatch<Packet>(`/onboarding/packets/${packet.id}`, { status: "completed" });
      await qc.invalidateQueries({ queryKey: ["packets"] });
    } catch (e) {
      setSaveMsg("Error: " + (e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  async function sendHrRequest() {
    setRequestBusy(true);
    setRequestErr(null);
    try {
      await apiPost<PacketRequest>("/onboarding/packet-requests", {
        message: requestNote.trim() || undefined,
      });
      await qc.invalidateQueries({ queryKey: ["onboarding-packet-request-me"] });
      setRequestNote("");
    } catch (e) {
      setRequestErr((e as Error).message);
    } finally {
      setRequestBusy(false);
    }
  }

  if (isLoading) return <div className="p-8 text-sm text-black/40">Loading…</div>;
  if (error) return <div className="p-8 text-sm text-red-600">Failed: {(error as Error).message}</div>;

  // No packet
  if (!packet) {
    const sent = myRequest?.status === "pending";
    return (
      <div className="space-y-4">
        <div className="text-2xl font-semibold">Onboarding</div>
        <div className="rounded-2xl border border-black/10 p-6 text-sm text-black/70 space-y-4">
          <p>
            You do not have an onboarding packet yet. You can notify HR from here so they know to create one
            for your employee record.
          </p>
          {reqLoading ? (
            <div className="text-black/40">Checking request status…</div>
          ) : sent ? (
            <div className="rounded-xl border border-emerald-200 bg-emerald-50/80 px-4 py-3 text-emerald-900">
              <div className="font-medium">Request sent to HR</div>
              <div className="text-xs mt-1 text-emerald-800/90">
                Submitted {new Date(myRequest!.created_at).toLocaleString()}
                {myRequest?.message ? ` · Note: ${myRequest.message}` : ""}
              </div>
              <p className="text-xs mt-2 text-emerald-800/80">
                HR will see this in the employer portal. You can leave this page; refresh after they create your packet.
              </p>
            </div>
          ) : (
            <>
              <Textarea
                label="Optional message to HR"
                hint="e.g. start date, role, or anything that helps them match your record."
                rows={3}
                value={requestNote}
                onChange={(e) => setRequestNote(e.target.value)}
                placeholder="Optional"
              />
              {requestErr && <div className="text-sm text-red-600">{requestErr}</div>}
              <Button onClick={sendHrRequest} disabled={requestBusy}>
                {requestBusy ? "Sending…" : "Request onboarding packet from HR"}
              </Button>
            </>
          )}
        </div>
      </div>
    );
  }

  // Completed / verified / activated
  if (["completed", "verified", "activated"].includes(packet.status)) {
    return (
      <div className="space-y-4">
        <div className="text-2xl font-semibold">Onboarding</div>
        <div className="rounded-2xl border border-black/10 bg-white p-10 text-center shadow-sm space-y-3">
          <div className="text-4xl">
            {packet.status === "activated" ? "🎉" : packet.status === "verified" ? "✅" : "📋"}
          </div>
          <div className="text-lg font-semibold">
            {packet.status === "activated"
              ? "You're all set!"
              : packet.status === "verified"
              ? "Information verified"
              : "Onboarding submitted"}
          </div>
          <div className="text-sm text-black/50 max-w-sm mx-auto">
            {packet.status === "activated"
              ? "Your onboarding is complete and your account is active. Welcome to the team!"
              : packet.status === "verified"
              ? "HR has verified your information. You'll be activated shortly."
              : "Your onboarding packet has been submitted. HR will review and verify your information soon."}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <div className="text-2xl font-semibold">Onboarding</div>
        <div className="text-sm text-black/60">
          Packet: <span className="capitalize">{packet.status}</span>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Step sidebar */}
        <div className="rounded-2xl border border-black/10 p-4">
          <div className="text-sm font-semibold mb-3">Steps</div>
          <div className="space-y-2">
            {availableSteps.map((s, i) => {
              const isDone = !!(packet.submitted_items ?? {})[s.key];
              return (
                <button
                  key={s.key}
                  onClick={() => { setStepIdx(i); setForm({}); setSaveMsg(null); }}
                  className={`w-full text-left rounded-xl px-3 py-2 text-sm border flex items-center justify-between ${
                    i === stepIdx
                      ? "border-black bg-black text-white"
                      : "border-black/10 hover:bg-black/5"
                  }`}
                >
                  <span>{s.title}</span>
                  {isDone && i !== stepIdx && (
                    <span className="text-emerald-500 text-xs">✓</span>
                  )}
                </button>
              );
            })}
          </div>
          <div className="mt-4 text-xs text-black/40">
            {Object.keys(packet.submitted_items ?? {}).length}/{availableSteps.length} steps saved
          </div>
        </div>

        {/* Step form */}
        <div className="lg:col-span-2 rounded-2xl border border-black/10 p-4 space-y-4">
          <div>
            <div className="text-lg font-semibold">{step.title}</div>
            <div className="text-sm text-black/60">
              Step {stepIdx + 1} of {availableSteps.length}
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {step.fields.includes("ssn_last4") && (
              <Input label="SSN last 4" maxLength={4} value={form.ssn_last4 ?? ""} onChange={(e) => setForm({ ...form, ssn_last4: e.target.value })} />
            )}
            {step.fields.includes("bank_name") && (
              <Input label="Bank name" value={form.bank_name ?? ""} onChange={(e) => setForm({ ...form, bank_name: e.target.value })} />
            )}
            {step.fields.includes("routing_number") && (
              <Input label="Routing number" value={form.routing_number ?? ""} onChange={(e) => setForm({ ...form, routing_number: e.target.value })} />
            )}
            {step.fields.includes("account_number") && (
              <Input label="Account number" value={form.account_number ?? ""} onChange={(e) => setForm({ ...form, account_number: e.target.value })} />
            )}
            {step.fields.includes("filing_status") && (
              <Input label="Filing status" placeholder="Single / Married / HoH" value={form.filing_status ?? ""} onChange={(e) => setForm({ ...form, filing_status: e.target.value })} />
            )}
            {step.fields.includes("dependents") && (
              <Input label="Dependents" type="number" value={form.dependents ?? ""} onChange={(e) => setForm({ ...form, dependents: e.target.value })} />
            )}
            {step.fields.includes("additional_withholding") && (
              <Input label="Additional withholding ($)" type="number" value={form.additional_withholding ?? ""} onChange={(e) => setForm({ ...form, additional_withholding: e.target.value })} />
            )}
            {step.fields.includes("citizenship_status") && (
              <Input label="Citizenship / work authorization status" value={form.citizenship_status ?? ""} onChange={(e) => setForm({ ...form, citizenship_status: e.target.value })} />
            )}
          </div>

          {step.fields.includes("documents") && (
            <Textarea
              label="I-9 documents (MVP)"
              hint="Next: upload document images to Supabase Storage; AI + HR verification workflow."
              rows={4}
              value={form.documents ?? ""}
              onChange={(e) => setForm({ ...form, documents: e.target.value })}
              placeholder="List documents you will provide (e.g., Passport, Driver's license + SS card)."
            />
          )}

          {saveMsg && (
            <div className={`text-sm ${saveMsg.startsWith("Error") ? "text-red-500" : "text-emerald-600"}`}>
              {saveMsg}
            </div>
          )}

          <div className="flex items-center justify-between pt-2">
            <Button
              variant="secondary"
              onClick={() => { setStepIdx(Math.max(0, stepIdx - 1)); setForm({}); setSaveMsg(null); }}
              disabled={stepIdx === 0}
            >
              Back
            </Button>

            <div className="flex gap-2">
              <Button variant="secondary" onClick={saveStep} disabled={saving}>
                {saving ? "Saving…" : "Save"}
              </Button>

              {isLastStep ? (
                <Button onClick={finish} disabled={saving}>
                  {saving ? "Submitting…" : "Finish & submit"}
                </Button>
              ) : (
                <Button onClick={saveAndNext} disabled={saving}>
                  Save & next
                </Button>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}