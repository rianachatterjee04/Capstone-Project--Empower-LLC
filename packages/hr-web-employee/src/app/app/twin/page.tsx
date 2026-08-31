"use client";
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch, apiPost, apiPatch } from "@/lib/api";

type MyRecord = {
  id: string;
  legal_name: string;
  preferred_name: string | null;
  email: string;
  job_title: string | null;
  department: string | null;
  location: string | null;
  status: string;
  start_date: string | null;
};

type EmergencyContact = {
  id: string;
  full_name: string;
  relationship: string | null;
  phone: string;
  email: string | null;
  is_primary: boolean;
};

type Twin = {
  employee_id: string; name: string;
  job_title: string | null; department: string | null;
  tenure_years: number;
  skills: string[]; performance_rating: number;
  growth_signals: string[];
  nearest_roles: { role: string; coverage_percent: number; matched_skills: string[]; missing_skills: string[] }[];
  marketplace_matches: { role: any; score: number; matched_skills: string[]; missing_skills: string[]; learning_hint: string }[];
  skill_gap_to_next: { target_role: string; gap: string[]; coverage_percent: number };
};

export default function MyTwinPage() {
  const q = useQuery({ queryKey: ["my-twin"], queryFn: () => apiFetch<Twin>("/digital-twin/me") });
  const t = q.data;

  return (
    <div className="space-y-6">
      <div>
        <div className="text-2xl font-semibold">My Career Profile</div>
        <div className="text-sm text-black/60">What Foundry People sees about your skills, performance, and growth.</div>
      </div>

      {!t ? (
        <div className="rounded-2xl border border-black/10 p-6 text-sm text-black/40 text-center">Loading…</div>
      ) : (
        <div className="space-y-4">
          <div className="rounded-2xl border-2 border-black/10 p-5 bg-gradient-to-br from-cyan-50 to-indigo-50">
            <div className="text-2xl font-bold">{t.name}</div>
            <div className="text-sm text-black/60">{t.job_title} · {t.department} · {t.tenure_years}y</div>
            {t.growth_signals.length > 0 && (
              <ul className="text-sm mt-3 space-y-0.5">
                {t.growth_signals.map((g, i) => <li key={i}>• {g}</li>)}
              </ul>
            )}
          </div>

          <div className="rounded-2xl border border-black/10 p-4">
            <div className="text-sm font-semibold mb-2">My skills</div>
            <div className="flex flex-wrap gap-1">
              {t.skills.length === 0
                ? <span className="text-xs text-black/40">No skills documented yet. Visit /learning to map them.</span>
                : t.skills.map((s) => <span key={s} className="rounded-full bg-emerald-50 border border-emerald-200 px-2 py-0.5 text-xs text-emerald-800">{s}</span>)}
            </div>
          </div>

          <div className="rounded-2xl border border-black/10 p-4">
            <div className="text-sm font-semibold mb-2">Next-level coverage ({t.skill_gap_to_next.target_role || "—"})</div>
            <div className="h-2 rounded-full bg-black/[0.05] overflow-hidden mb-2">
              <div className="h-full bg-indigo-500" style={{ width: `${t.skill_gap_to_next.coverage_percent}%` }} />
            </div>
            <div className="text-xs text-black/60">{t.skill_gap_to_next.coverage_percent}% coverage. Close: {t.skill_gap_to_next.gap.join(", ") || "ready"}</div>
          </div>

          {t.marketplace_matches.length > 0 && (
            <div className="rounded-2xl border border-black/10 p-4">
              <div className="text-sm font-semibold mb-2">Internal roles that fit you</div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                {t.marketplace_matches.map((m, i) => (
                  <div key={i} className="rounded-xl border border-black/10 p-3">
                    <div className="flex items-center justify-between">
                      <div className="text-sm font-semibold">{m.role.title}</div>
                      <span className="text-xs font-mono">{m.score}</span>
                    </div>
                    <div className="text-xs text-emerald-700">+ {m.matched_skills.join(", ") || "—"}</div>
                    <div className="text-xs text-rose-700">↑ {m.missing_skills.join(", ") || "ready"}</div>
                    <div className="text-xs text-black/60 mt-1">{m.learning_hint}</div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      <MyDetailsSection />
      <EmergencyContactsSection />
    </div>
  );
}

/** Self-service profile edits (preferred name + location). Every change is
 * audited server-side (employee.profile_self_edited). */
function MyDetailsSection() {
  const qc = useQueryClient();
  const meQ = useQuery({
    queryKey: ["my-employee-record"],
    queryFn: () => apiFetch<MyRecord>("/employee-records/me"),
    retry: false,
  });
  const [preferredName, setPreferredName] = useState<string | null>(null);
  const [location, setLocation] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  const save = useMutation({
    mutationFn: () =>
      apiPatch<{ updated: boolean }>("/employee-records/me/profile", {
        ...(preferredName !== null ? { preferred_name: preferredName } : {}),
        ...(location !== null ? { location } : {}),
      }),
    onSuccess: async (r) => {
      setMsg(r.updated ? "Saved. Changes are recorded in the audit log." : "No changes to save.");
      await qc.invalidateQueries({ queryKey: ["my-employee-record"] });
    },
    onError: (e) => setMsg((e as Error).message),
  });

  if (meQ.isError) return null; // no employee record linked yet
  const me = meQ.data;

  return (
    <div className="rounded-2xl border border-black/10 p-4">
      <div className="text-sm font-semibold mb-1">My details</div>
      <div className="text-xs text-black/50 mb-3">
        You can update your preferred name and location. Legal name, title and department are managed by HR.
      </div>
      {!me ? (
        <div className="text-sm text-black/40">Loading…</div>
      ) : (
        <div className="space-y-3">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <label className="block">
              <div className="mb-1 text-xs text-black/60">Preferred name</div>
              <input
                className="w-full rounded-xl border border-black/15 px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-black/20"
                value={preferredName ?? me.preferred_name ?? ""}
                onChange={(e) => setPreferredName(e.target.value)}
              />
            </label>
            <label className="block">
              <div className="mb-1 text-xs text-black/60">Location</div>
              <input
                className="w-full rounded-xl border border-black/15 px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-black/20"
                value={location ?? me.location ?? ""}
                onChange={(e) => setLocation(e.target.value)}
              />
            </label>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-xs text-black/60">
            <div><span className="text-black/40">Legal name:</span> {me.legal_name}</div>
            <div><span className="text-black/40">Title:</span> {me.job_title ?? "—"}</div>
            <div><span className="text-black/40">Department:</span> {me.department ?? "—"}</div>
            <div><span className="text-black/40">Start date:</span> {me.start_date ?? "—"}</div>
          </div>
          <div className="flex items-center gap-3">
            <button
              className="rounded-lg bg-black px-3 py-2 text-sm font-medium text-white disabled:opacity-40"
              disabled={save.isPending || (preferredName === null && location === null)}
              onClick={() => save.mutate()}
            >
              {save.isPending ? "Saving…" : "Save changes"}
            </button>
            {msg && <span className="text-xs text-black/60">{msg}</span>}
          </div>
        </div>
      )}
    </div>
  );
}

function EmergencyContactsSection() {
  const qc = useQueryClient();
  const meQ = useQuery({
    queryKey: ["my-employee-record"],
    queryFn: () => apiFetch<MyRecord>("/employee-records/me"),
    retry: false,
  });
  const empId = meQ.data?.id;
  const contactsQ = useQuery({
    queryKey: ["my-emergency-contacts", empId],
    queryFn: () => apiFetch<EmergencyContact[]>(`/employee-records/${empId}/emergency-contacts`),
    enabled: !!empId,
  });
  const [form, setForm] = useState({ full_name: "", relationship: "", phone: "", email: "" });
  const [err, setErr] = useState<string | null>(null);

  const add = useMutation({
    mutationFn: () =>
      apiPost(`/employee-records/${empId}/emergency-contacts`, {
        full_name: form.full_name.trim(),
        relationship: form.relationship.trim() || null,
        phone: form.phone.trim(),
        email: form.email.trim() || null,
        is_primary: (contactsQ.data ?? []).length === 0,
      }),
    onSuccess: async () => {
      setForm({ full_name: "", relationship: "", phone: "", email: "" });
      setErr(null);
      await qc.invalidateQueries({ queryKey: ["my-emergency-contacts", empId] });
    },
    onError: (e) => setErr((e as Error).message),
  });

  const remove = useMutation({
    mutationFn: (id: string) => apiFetch(`/employee-records/emergency-contacts/${id}`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["my-emergency-contacts", empId] }),
  });

  if (meQ.isError || !empId) return null;
  const contacts = contactsQ.data ?? [];

  return (
    <div className="rounded-2xl border border-black/10 p-4">
      <div className="text-sm font-semibold mb-1">Emergency contacts</div>
      <div className="text-xs text-black/50 mb-3">Who should we reach in an emergency?</div>

      <div className="space-y-2">
        {contacts.length === 0 && <div className="text-sm text-black/40">No contacts on file yet.</div>}
        {contacts.map((c) => (
          <div key={c.id} className="flex items-center justify-between rounded-xl border border-black/10 p-3">
            <div>
              <div className="text-sm font-medium">
                {c.full_name}
                {c.is_primary && (
                  <span className="ml-2 rounded-full bg-indigo-50 border border-indigo-200 px-2 py-0.5 text-xs text-indigo-700">primary</span>
                )}
              </div>
              <div className="text-xs text-black/60">
                {c.relationship ?? "—"} · {c.phone}
                {c.email ? ` · ${c.email}` : ""}
              </div>
            </div>
            <button
              className="text-xs text-red-600 hover:underline disabled:opacity-40"
              disabled={remove.isPending}
              onClick={() => remove.mutate(c.id)}
            >
              Remove
            </button>
          </div>
        ))}
      </div>

      <div className="mt-4 grid grid-cols-1 md:grid-cols-4 gap-2">
        <input
          className="rounded-xl border border-black/15 px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-black/20"
          placeholder="Full name"
          value={form.full_name}
          onChange={(e) => setForm({ ...form, full_name: e.target.value })}
        />
        <input
          className="rounded-xl border border-black/15 px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-black/20"
          placeholder="Relationship"
          value={form.relationship}
          onChange={(e) => setForm({ ...form, relationship: e.target.value })}
        />
        <input
          className="rounded-xl border border-black/15 px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-black/20"
          placeholder="Phone"
          value={form.phone}
          onChange={(e) => setForm({ ...form, phone: e.target.value })}
        />
        <input
          className="rounded-xl border border-black/15 px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-black/20"
          placeholder="Email (optional)"
          value={form.email}
          onChange={(e) => setForm({ ...form, email: e.target.value })}
        />
      </div>
      <div className="mt-2 flex items-center gap-3">
        <button
          className="rounded-lg bg-black px-3 py-2 text-sm font-medium text-white disabled:opacity-40"
          disabled={add.isPending || !form.full_name.trim() || !form.phone.trim()}
          onClick={() => add.mutate()}
        >
          {add.isPending ? "Adding…" : "Add contact"}
        </button>
        {err && <span className="text-xs text-red-600">{err}</span>}
      </div>
    </div>
  );
}
