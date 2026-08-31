"use client";
import { useEffect, useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch, apiPatch, apiPost } from "@/lib/api";

import { PageHeader, Surface, SectionTitle, Pill, Action, EmptyState, Avatar, Divider, KeyValue } from "@/components/ds";
import { IconArrowUpRight, IconSparkle } from "@/components/icons";

type Pipeline = { id: string; label: string; statuses: string[] };
type Contact = {
  id: string; name: string; pipeline: string; status: string;
  role_target?: string | null; department?: string | null;
  location?: string | null; email?: string | null; linkedin?: string | null;
  source?: string | null; referred_by?: string | null;
  last_touch_at?: string | null; next_touch_at?: string | null;
  owner?: string | null; rating?: number | null;
  ai_signal?: string | null;
  tags: string[]; notes_count: number;
  created_at: string; updated_at: string;
  notes?: { id: string; body: string; author: string; created_at: string }[];
};
type Summary = {
  total_contacts: number;
  pipelines: Record<string, number>;
  overdue_touch: number;
  high_rating: number;
  ready_succession: number;
  active_offers: number;
  provenance?: { all_sample: boolean; note: string | null };
};

const PIPELINE_LABEL: Record<string, string> = {
  candidates: "Candidates",
  alumni: "Alumni",
  referrals: "Referrals",
  boomerangs: "Boomerangs",
  succession: "Succession",
};

const PIPELINE_TONE: Record<string, "info" | "neutral" | "warn" | "success"> = {
  candidates: "info",
  alumni: "neutral",
  referrals: "info",
  boomerangs: "warn",
  succession: "success",
};

const STATUS_TONE: Record<string, "info" | "warn" | "success" | "danger" | "neutral"> = {
  new: "info", screening: "info", interview: "warn", offer: "success", hired: "success", rejected: "danger", nurture: "neutral",
  in_touch: "success", lost_touch: "warn", do_not_contact: "danger",
  watching: "neutral", warm: "warn", engaged: "info", rehired: "success",
  groom: "warn", ready_now: "success", promoted: "success",
  thanked: "neutral",
};

function daysSince(iso?: string | null): string {
  if (!iso) return "—";
  const d = (Date.now() - new Date(iso).getTime()) / (1000 * 60 * 60 * 24);
  if (d < 1) return "today";
  if (d < 2) return "1d";
  return `${Math.round(d)}d`;
}

export default function CRMPage() {
  const qc = useQueryClient();
  const [pipeline, setPipeline] = useState<string>("candidates");
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<string>("");
  const [noteText, setNoteText] = useState("");

  const sumQ = useQuery({ queryKey: ["crm-summary"], queryFn: () => apiFetch<Summary>("/crm/summary") });
  const pipQ = useQuery({ queryKey: ["crm-pipelines"], queryFn: () => apiFetch<{ items: Pipeline[] }>("/crm/pipelines") });
  const contactsQ = useQuery({
    queryKey: ["crm-contacts", pipeline, search],
    queryFn: () =>
      apiFetch<{ items: Contact[] }>(`/crm/contacts?pipeline=${pipeline}${search ? `&q=${encodeURIComponent(search)}` : ""}`),
  });

  const contacts = contactsQ.data?.items ?? [];
  useEffect(() => {
    if (contacts.length === 0) { setSelected(""); return; }
    if (!contacts.some((c) => c.id === selected)) setSelected(contacts[0].id);
  }, [contacts, selected]);

  const detailQ = useQuery({
    queryKey: ["crm-contact", selected],
    queryFn: () => apiFetch<Contact>(`/crm/contacts/${selected}`),
    enabled: !!selected,
  });
  const detail = detailQ.data;

  async function addNote() {
    if (!noteText.trim() || !selected) return;
    await apiPost(`/crm/contacts/${selected}/notes`, { body: noteText, author: "Recruiter" });
    setNoteText("");
    await qc.invalidateQueries({ queryKey: ["crm-contact", selected] });
    await qc.invalidateQueries({ queryKey: ["crm-contacts", pipeline, search] });
    await qc.invalidateQueries({ queryKey: ["crm-summary"] });
  }

  // Add contact composer state
  const [composeOpen, setComposeOpen] = useState(false);
  const [newName, setNewName] = useState("");
  const [newEmail, setNewEmail] = useState("");
  const [newRole, setNewRole] = useState("");
  const [newOwner, setNewOwner] = useState("");
  const [newSource, setNewSource] = useState("");
  const [creating, setCreating] = useState(false);

  async function createContact() {
    if (!newName.trim()) return;
    setCreating(true);
    try {
      const created = await apiPost<Contact>("/crm/contacts", {
        name: newName,
        email: newEmail || null,
        role_target: newRole || null,
        owner: newOwner || null,
        source: newSource || null,
        pipeline,
      });
      setNewName(""); setNewEmail(""); setNewRole(""); setNewOwner(""); setNewSource("");
      setComposeOpen(false);
      await qc.invalidateQueries({ queryKey: ["crm-contacts", pipeline, search] });
      await qc.invalidateQueries({ queryKey: ["crm-summary"] });
      setSelected(created.id);
    } finally {
      setCreating(false);
    }
  }

  async function setStatus(status: string) {
    if (!selected) return;
    await apiPatch(`/crm/contacts/${selected}`, { status });
    await qc.invalidateQueries({ queryKey: ["crm-contact", selected] });
    await qc.invalidateQueries({ queryKey: ["crm-contacts", pipeline, search] });
  }

  const pipelines = pipQ.data?.items ?? [];
  const activePipeline = pipelines.find((p) => p.id === pipeline);

  return (
    <div className="space-y-7 fp-fade-in">
      <PageHeader
        eyebrow="Talent"
        title="People CRM"
        subtitle="Long-term relationships with candidates, alumni, referrals, boomerangs, and internal succession."
        actions={
          <Action variant="primary" onClick={() => setComposeOpen((v) => !v)}>
            <IconSparkle /> {composeOpen ? "Cancel" : "Add contact"}
          </Action>
        }
      />

      {/* "Total contacts 12 · Overdue touch 4" for a book seeded with twelve
          invented people. "Overdue touch 4" reads as four relationships the
          reader has neglected. */}
      {sumQ.data?.provenance?.all_sample && sumQ.data.provenance.note && (
        <Surface pad="md">
          <div className="fp-eyebrow">Example relationships</div>
          <p className="mt-1 text-sm text-body">{sumQ.data.provenance.note}</p>
        </Surface>
      )}

      {composeOpen && (
        <Surface pad="sm">
          <SectionTitle eyebrow="Compose" title={`New ${PIPELINE_LABEL[pipeline]?.toLowerCase() ?? "contact"}`} description={`Added to the ${PIPELINE_LABEL[pipeline]} pipeline.`} />
          <div className="mt-3 grid grid-cols-1 md:grid-cols-5 gap-2">
            <input
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              placeholder="Full name"
              className="md:col-span-2 h-9 rounded-md border border-line bg-canvas px-3 text-sm text-ink outline-none focus:bg-surface"
            />
            <input
              value={newEmail}
              onChange={(e) => setNewEmail(e.target.value)}
              placeholder="Email"
              className="md:col-span-2 h-9 rounded-md border border-line bg-canvas px-3 text-sm text-ink outline-none focus:bg-surface"
            />
            <input
              value={newRole}
              onChange={(e) => setNewRole(e.target.value)}
              placeholder="Role target"
              className="h-9 rounded-md border border-line bg-canvas px-3 text-sm text-ink outline-none focus:bg-surface"
            />
            <input
              value={newOwner}
              onChange={(e) => setNewOwner(e.target.value)}
              placeholder="Owner"
              className="h-9 rounded-md border border-line bg-canvas px-3 text-sm text-ink outline-none focus:bg-surface"
            />
            <input
              value={newSource}
              onChange={(e) => setNewSource(e.target.value)}
              placeholder="Source (referral · inbound · event…)"
              className="md:col-span-3 h-9 rounded-md border border-line bg-canvas px-3 text-sm text-ink outline-none focus:bg-surface"
            />
            <Action variant="primary" onClick={createContact} disabled={!newName.trim() || creating}>
              {creating ? "Saving…" : "Create"}
            </Action>
          </div>
        </Surface>
      )}

      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        <Stat label="Total contacts" value={sumQ.data?.total_contacts ?? "—"} />
        <Stat label="Active offers" value={sumQ.data?.active_offers ?? "—"} tone={(sumQ.data?.active_offers ?? 0) > 0 ? "warn" : "neutral"} />
        <Stat label="Overdue touch" value={sumQ.data?.overdue_touch ?? "—"} tone={(sumQ.data?.overdue_touch ?? 0) > 0 ? "warn" : "neutral"} />
        <Stat label="High rating ≥ 85" value={sumQ.data?.high_rating ?? "—"} tone="success" />
        <Stat label="Succession ready" value={sumQ.data?.ready_succession ?? "—"} tone="success" />
      </div>

      {/* Pipeline tabs */}
      <div className="flex flex-wrap gap-2">
        {pipelines.map((p) => (
          <button
            key={p.id}
            onClick={() => setPipeline(p.id)}
            className={`text-sm rounded-md px-3 py-1.5 border transition-colors duration-150 ease-calm ${
              pipeline === p.id ? "bg-accent text-accent-fg border-accent" : "bg-surface border-line text-body hover:bg-sunken hover:text-ink"
            }`}
          >
            {p.label}
            <span className="ml-1.5 text-2xs uppercase tracking-eyebrow opacity-70">
              {sumQ.data?.pipelines?.[p.id] ?? 0}
            </span>
          </button>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[1fr_400px] gap-5">
        {/* Contact list */}
        <Surface pad="sm">
          <div className="flex items-center gap-2 mb-3">
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder={`Search ${PIPELINE_LABEL[pipeline]?.toLowerCase()}…`}
              className="flex-1 h-9 rounded-md border border-line bg-canvas px-3 text-sm text-ink outline-none focus:bg-surface placeholder:text-muted"
            />
            {search && <button onClick={() => setSearch("")} className="text-xs text-muted hover:text-ink">clear</button>}
          </div>

          {contactsQ.isLoading ? (
            <div className="text-sm text-muted py-6 text-center">Loading…</div>
          ) : contacts.length === 0 ? (
            <EmptyState title="No contacts yet" description="Add someone to start the pipeline." />
          ) : (
            <ul className="divide-y divide-rule">
              {contacts.map((c) => {
                const isActive = c.id === selected;
                return (
                  <li key={c.id}>
                    <button
                      onClick={() => setSelected(c.id)}
                      className={`w-full text-left -mx-2 px-2 py-3 rounded-md transition-colors duration-150 ease-calm ${
                        isActive ? "bg-canvas" : "hover:bg-sunken/60"
                      }`}
                    >
                      <div className="flex items-start gap-3">
                        <Avatar name={c.name} size={32} />
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 flex-wrap">
                            <span className="text-sm font-semibold text-ink">{c.name}</span>
                            <Pill tone={STATUS_TONE[c.status] ?? "neutral"}>{c.status.replace(/_/g, " ")}</Pill>
                            {c.rating != null && <Pill tone={c.rating >= 85 ? "success" : c.rating >= 70 ? "warn" : "neutral"}>{c.rating}</Pill>}
                          </div>
                          <div className="text-2xs uppercase tracking-eyebrow text-muted mt-0.5">
                            {c.role_target ?? "—"} {c.department ? `· ${c.department}` : ""}
                          </div>
                          {c.ai_signal && (
                            <div className="text-xs text-muted mt-1 line-clamp-2 italic">{c.ai_signal}</div>
                          )}
                        </div>
                        <div className="shrink-0 text-right">
                          <div className="text-2xs uppercase tracking-eyebrow text-muted">last</div>
                          <div className="text-sm text-ink tabular-nums">{daysSince(c.last_touch_at)}</div>
                        </div>
                      </div>
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </Surface>

        {/* Detail drawer */}
        <Surface>
          {!detail ? (
            <EmptyState title="Pick a contact" description="Read AI signals, notes timeline, and move the record forward." />
          ) : (
            <>
              <div className="flex items-start gap-3">
                <Avatar name={detail.name} size={44} />
                <div className="min-w-0">
                  <div className="fp-eyebrow">{PIPELINE_LABEL[detail.pipeline] ?? detail.pipeline}</div>
                  <div className="text-xl font-semibold tracking-tight text-ink">{detail.name}</div>
                  <div className="text-sm text-muted">{detail.role_target ?? "—"}</div>
                </div>
              </div>

              <Divider className="my-3" />

              {detail.ai_signal && (
                <div className="rounded-md border border-info-line bg-info-bg text-info-fg p-3 text-sm">
                  <div className="text-2xs uppercase tracking-eyebrow opacity-80 mb-1">AI signal</div>
                  {detail.ai_signal}
                </div>
              )}

              <div className="mt-3 grid grid-cols-1 gap-y-0">
                <KeyValue label="Status" value={
                  <select
                    value={detail.status}
                    onChange={(e) => setStatus(e.target.value)}
                    className="h-7 rounded-md border border-line bg-surface px-2 text-xs"
                  >
                    {(activePipeline?.statuses ?? [detail.status]).map((s) => (
                      <option key={s}>{s}</option>
                    ))}
                  </select>
                } />
                <KeyValue label="Owner" value={detail.owner ?? "—"} />
                <KeyValue label="Department" value={detail.department ?? "—"} />
                <KeyValue label="Source" value={detail.source ?? "—"} />
                {detail.referred_by && <KeyValue label="Referred by" value={detail.referred_by} />}
                <KeyValue label="Email" value={detail.email ?? "—"} mono />
                <KeyValue label="Last touch" value={daysSince(detail.last_touch_at)} />
                <KeyValue label="Next touch" value={daysSince(detail.next_touch_at)} />
                {detail.rating != null && <KeyValue label="Rating" value={`${detail.rating}/100`} />}
              </div>

              {(detail.tags ?? []).length > 0 && (
                <>
                  <Divider className="my-3" />
                  <div className="flex flex-wrap gap-1">
                    {detail.tags.map((t) => <Pill key={t} tone="neutral">{t}</Pill>)}
                  </div>
                </>
              )}

              <Divider className="my-3" />

              <div className="fp-eyebrow mb-2">Notes</div>
              <div className="space-y-2 max-h-56 overflow-auto -mx-1 px-1">
                {(detail.notes ?? []).length === 0 ? (
                  <div className="text-xs text-muted">No notes yet.</div>
                ) : (
                  (detail.notes ?? []).map((n) => (
                    <div key={n.id} className="rounded-md border border-line bg-canvas px-3 py-2">
                      <div className="flex items-center justify-between gap-2">
                        <div className="text-2xs uppercase tracking-eyebrow text-muted">{n.author}</div>
                        <div className="text-2xs uppercase tracking-eyebrow text-muted">{new Date(n.created_at).toLocaleString()}</div>
                      </div>
                      <div className="text-sm text-body mt-1 whitespace-pre-line">{n.body}</div>
                    </div>
                  ))
                )}
              </div>

              <div className="mt-3 flex items-end gap-2">
                <textarea
                  value={noteText}
                  onChange={(e) => setNoteText(e.target.value)}
                  placeholder="Add a note…"
                  rows={2}
                  className="flex-1 rounded-md border border-line bg-canvas px-3 py-2 text-sm text-ink outline-none focus:bg-surface"
                />
                <Action variant="primary" onClick={addNote} disabled={!noteText.trim()}>Add</Action>
              </div>
            </>
          )}
        </Surface>
      </div>
    </div>
  );
}

function Stat({ label, value, tone = "neutral" }: { label: string; value: React.ReactNode; tone?: "neutral" | "success" | "warn" | "info" }) {
  const ring: Record<string, string> = {
    neutral: "",
    success: "ring-1 ring-success-line",
    warn: "ring-1 ring-warn-line",
    info: "ring-1 ring-info-line",
  };
  return (
    <div className={`rounded-md border border-line bg-surface p-4 ${ring[tone]}`}>
      <div className="fp-eyebrow">{label}</div>
      <div className="mt-1 text-2xl font-semibold tracking-tight text-ink tabular-nums">{value}</div>
    </div>
  );
}
