"use client";
import { useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch, apiPost } from "@/lib/api";

import { PageHeader, Surface, SectionTitle, Pill, Action, EmptyState, Divider, KeyValue } from "@/components/ds";

type Integration = { key: string; name: string; category: string; connected: boolean; note?: string };
type Automation = { id: string; label: string; description: string; trigger: string; agent: string; enabled: boolean; requires_approval: boolean };
type Settings = {
  org: { legal_name: string; display_name: string; domain: string; timezone: string; fiscal_year_start: string; primary_locale: string; headquarters: string };
  brand: { accent: string; canvas: string; wordmark: string; tone_of_voice: string };
  integrations: Integration[];
  automations: Automation[];
  security: { sso_provider: string; mfa_required: boolean; audit_retention_years: number; data_residency: string; soc2_status: string; last_security_review: string };
  categories: string[];
};

type Tab = "org" | "brand" | "integrations" | "automations" | "security";

const TABS: { id: Tab; label: string; eyebrow: string }[] = [
  { id: "org",          label: "Company",     eyebrow: "Workspace" },
  { id: "brand",        label: "Brand",       eyebrow: "Workspace" },
  { id: "integrations", label: "Integrations", eyebrow: "Connect" },
  { id: "automations",  label: "Automations", eyebrow: "AI Ops" },
  { id: "security",     label: "Security",    eyebrow: "Posture" },
];

export default function SettingsPage() {
  const qc = useQueryClient();
  const [tab, setTab] = useState<Tab>("org");
  const q = useQuery({ queryKey: ["settings"], queryFn: () => apiFetch<Settings>("/settings-hub") });
  const s = q.data;

  const groupedIntegrations = useMemo(() => {
    const m = new Map<string, Integration[]>();
    for (const i of s?.integrations ?? []) {
      m.set(i.category, [...(m.get(i.category) ?? []), i]);
    }
    return Array.from(m.entries()).sort((a, b) => a[0].localeCompare(b[0]));
  }, [s]);

  async function toggleIntegration(key: string) {
    await apiPost(`/settings-hub/integrations/${key}/toggle`, {});
    await qc.invalidateQueries({ queryKey: ["settings"] });
  }
  async function toggleAutomation(id: string) {
    await apiPost(`/settings-hub/automations/${id}/toggle`, {});
    await qc.invalidateQueries({ queryKey: ["settings"] });
  }

  const connectedCount = (s?.integrations ?? []).filter((i) => i.connected).length;
  const enabledAutomations = (s?.automations ?? []).filter((a) => a.enabled).length;

  return (
    <div className="space-y-7 fp-fade-in">
      <PageHeader
        eyebrow="System"
        title="Settings"
        subtitle="Company profile, brand, integrations, automation rules, and security posture. Everything that configures Foundry."
      />

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Stat label="Integrations connected" value={`${connectedCount} / ${s?.integrations.length ?? "—"}`} tone={connectedCount ? "success" : "neutral"} />
        <Stat label="Automations enabled" value={`${enabledAutomations} / ${s?.automations.length ?? "—"}`} tone={enabledAutomations ? "success" : "neutral"} />
        <Stat label="SSO" value={s?.security.sso_provider ?? "—"} />
        <Stat label="Audit retention" value={s ? `${s.security.audit_retention_years}y` : "—"} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[220px_1fr] gap-5">
        <Surface pad="sm">
          <div className="fp-eyebrow mb-2">Sections</div>
          <nav className="space-y-0.5">
            {TABS.map((t) => {
              const active = tab === t.id;
              return (
                <button
                  key={t.id}
                  onClick={() => setTab(t.id)}
                  className={`w-full text-left rounded-md px-2.5 py-2 text-sm ${active ? "bg-canvas text-ink" : "text-body hover:bg-sunken hover:text-ink"}`}
                >
                  <span className="block text-2xs uppercase tracking-eyebrow text-muted">{t.eyebrow}</span>
                  <span className="font-medium">{t.label}</span>
                </button>
              );
            })}
          </nav>
        </Surface>

        <div className="space-y-4">
          {!s ? (
            <Surface><EmptyState title="Loading…" /></Surface>
          ) : tab === "org" ? (
            <Surface>
              <SectionTitle eyebrow="Company" title="Profile" description="Used across every workflow + audit." />
              <div className="mt-3 grid grid-cols-1 md:grid-cols-2 gap-x-8">
                <div>
                  <KeyValue label="Legal name" value={s.org.legal_name} />
                  <KeyValue label="Display name" value={s.org.display_name} />
                  <KeyValue label="Domain" value={s.org.domain} mono />
                  <KeyValue label="Headquarters" value={s.org.headquarters} />
                </div>
                <div>
                  <KeyValue label="Timezone" value={s.org.timezone} />
                  <KeyValue label="Fiscal year start" value={s.org.fiscal_year_start} />
                  <KeyValue label="Primary locale" value={s.org.primary_locale} />
                </div>
              </div>
            </Surface>
          ) : tab === "brand" ? (
            <Surface>
              <SectionTitle eyebrow="Brand" title="Voice + identity" description="Keeps every email + document on-brand." />
              <div className="mt-3 grid grid-cols-1 md:grid-cols-2 gap-x-8">
                <div>
                  <KeyValue label="Wordmark" value={s.brand.wordmark} mono />
                  <KeyValue label="Accent" value={<span className="inline-flex items-center gap-2"><span className="inline-block h-4 w-4 rounded" style={{ background: s.brand.accent }} />{s.brand.accent}</span>} />
                  <KeyValue label="Canvas" value={<span className="inline-flex items-center gap-2"><span className="inline-block h-4 w-4 rounded border border-line" style={{ background: s.brand.canvas }} />{s.brand.canvas}</span>} />
                </div>
                <div>
                  <KeyValue label="Tone of voice" value={s.brand.tone_of_voice} />
                </div>
              </div>
            </Surface>
          ) : tab === "integrations" ? (
            <div className="space-y-3">
              {groupedIntegrations.map(([cat, items]) => (
                <Surface key={cat} pad="sm">
                  <div className="fp-eyebrow mb-2 capitalize">{cat}</div>
                  <ul className="divide-y divide-rule">
                    {items.map((i) => (
                      <li key={i.key} className="py-2.5 flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <div className="flex items-center gap-2 flex-wrap">
                            <span className="text-sm font-semibold text-ink">{i.name}</span>
                            {i.connected ? <Pill tone="success">connected</Pill> : <Pill tone="neutral">disconnected</Pill>}
                          </div>
                          {i.note && <div className="text-xs text-muted mt-0.5">{i.note}</div>}
                        </div>
                        <Action variant={i.connected ? "subtle" : "primary"} size="sm" onClick={() => toggleIntegration(i.key)}>
                          {i.connected ? "Disconnect" : "Connect"}
                        </Action>
                      </li>
                    ))}
                  </ul>
                </Surface>
              ))}
            </div>
          ) : tab === "automations" ? (
            <Surface>
              <SectionTitle eyebrow="AI Ops" title="Automation rules" description="What the agents auto-run on which triggers. Toggle individual rules — nothing here acts without your approval where required." />
              <ul className="mt-3 divide-y divide-rule">
                {s.automations.map((a) => (
                  <li key={a.id} className="py-3 flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="text-sm font-semibold text-ink">{a.label}</span>
                        <Pill tone="neutral">{a.agent.replace(/_/g, " ")}</Pill>
                        <Pill tone="info">{a.trigger}</Pill>
                        {a.requires_approval && <Pill tone="warn">approval required</Pill>}
                      </div>
                      <div className="text-xs text-muted mt-0.5">{a.description}</div>
                    </div>
                    <Action variant={a.enabled ? "subtle" : "primary"} size="sm" onClick={() => toggleAutomation(a.id)}>
                      {a.enabled ? "Disable" : "Enable"}
                    </Action>
                  </li>
                ))}
              </ul>
            </Surface>
          ) : tab === "security" ? (
            <Surface>
              <SectionTitle eyebrow="Posture" title="Security & compliance" />
              <div className="mt-3 grid grid-cols-1 md:grid-cols-2 gap-x-8">
                <div>
                  <KeyValue label="SSO provider" value={s.security.sso_provider} />
                  <KeyValue label="MFA required" value={s.security.mfa_required ? "Yes" : "No"} />
                  <KeyValue label="Data residency" value={s.security.data_residency} />
                </div>
                <div>
                  <KeyValue label="Audit retention" value={`${s.security.audit_retention_years} years`} />
                  <KeyValue label="SOC 2 status" value={s.security.soc2_status} />
                  <KeyValue label="Last review" value={s.security.last_security_review} />
                </div>
              </div>
              <Divider className="my-4" />
              <div className="text-xs text-muted">
                Permissions are enforced per role across every API: owner / admin / hr / manager / employee.
              </div>
            </Surface>
          ) : null}
        </div>
      </div>
    </div>
  );
}

function Stat({ label, value, tone = "neutral" }: { label: string; value: React.ReactNode; tone?: "neutral" | "success" }) {
  const ring: Record<string, string> = { neutral: "", success: "ring-1 ring-success-line" };
  return (
    <div className={`rounded-md border border-line bg-surface p-4 ${ring[tone]}`}>
      <div className="fp-eyebrow">{label}</div>
      <div className="mt-1 text-xl font-semibold tracking-tight text-ink truncate">{value}</div>
    </div>
  );
}
