"use client";

import { useState } from "react";
import { apiFetch, apiPost } from "@/lib/api";
import { Button } from "@/components/Button";

type Provider = { provider: string; connected: boolean };
type GreenhouseConnectResponse = { ok: boolean; provider: string; webhook_secret?: string; sync_started?: boolean };
type LeverConnectResponse = { ok: boolean; provider: string; oauth_url: string };

export default function IntegrationsPage() {
  const [greenhouseMessage, setGreenhouseMessage] = useState("");
  const [leverUrl, setLeverUrl] = useState("");
  const [providers, setProviders] = useState<Provider[]>([]);

  async function loadProviders() {
    const data = await apiFetch<{ items?: Provider[] }>("/integrations/providers");
    setProviders(data.items || []);
  }

  async function connectGreenhouse() {
    const r = await apiPost<GreenhouseConnectResponse>("/integrations/connect/greenhouse", { api_key: "demo-greenhouse-api-key" });
    setGreenhouseMessage(r.sync_started ? "Greenhouse connected and initial sync started." : "Greenhouse connected, but Temporal sync did not start locally.");
  }

  async function connectLever() {
    const r = await apiPost<LeverConnectResponse>("/integrations/connect/lever", {});
    setLeverUrl(r.oauth_url);
  }

  return (
    <div className="space-y-6">
      <div>
        <div className="text-2xl font-semibold">Integrations</div>
        <div className="mt-1 text-sm text-black/50">Connect your ATS and HR tools</div>
      </div>

      <div className="rounded-2xl border border-black/10 bg-white p-5 shadow-sm space-y-4">
        <div className="text-sm font-semibold">ATS Providers</div>
        <div className="flex gap-3 flex-wrap">
          <Button variant="secondary" onClick={loadProviders}>Load providers</Button>
          <Button variant="secondary" onClick={connectGreenhouse}>Connect Greenhouse</Button>
          <Button variant="secondary" onClick={connectLever}>Connect Lever</Button>
        </div>
        {greenhouseMessage && (
          <div className="rounded-xl border border-black/10 p-3 text-sm">{greenhouseMessage}</div>
        )}
        {leverUrl && (
          <div className="rounded-xl border border-black/10 p-3 text-sm break-all">
            <div className="font-medium mb-1">Lever OAuth URL</div>
            <a className="underline" href={leverUrl} target="_blank" rel="noreferrer">{leverUrl}</a>
          </div>
        )}
        <div className="divide-y divide-black/5">
          <div className="pb-2 text-sm font-medium">Providers</div>
          {providers.length === 0 ? (
            <div className="pt-3 text-sm text-black/40">No providers loaded yet.</div>
          ) : (
            providers.map((p) => (
              <div key={p.provider} className="flex items-center justify-between py-3">
                <span className="text-sm font-medium capitalize">{p.provider}</span>
                <span className={`text-xs font-medium px-2.5 py-0.5 rounded-full border ${p.connected ? "bg-emerald-50 text-emerald-700 border-emerald-200" : "bg-gray-50 text-gray-500 border-gray-200"}`}>
                  {p.connected ? "Connected" : "Not connected"}
                </span>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
