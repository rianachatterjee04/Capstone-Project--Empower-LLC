"use client";
import { useState } from "react";
import { apiFetch, apiPost } from "@/lib/api";
import { useQuery } from "@tanstack/react-query";
import { Button } from "@/components/Button";
import { Input } from "@/components/Input";

export default function IntegrationsPage() {
  const providersQ = useQuery({ queryKey: ["int_providers"], queryFn: () => apiFetch<{ providers: string[] }>("/integrations/providers") });

  const [ghKey, setGhKey] = useState("");
  const [gh, setGh] = useState<any | null>(null);

  const [leverUrl, setLeverUrl] = useState<string | null>(null);

  async function connectGreenhouse() {
    const r = await apiPost("/integrations/connect/greenhouse", { api_key: ghKey });
    setGh(r);
  }

  async function connectLever() {
    const r = await apiPost("/integrations/connect/lever", {});
    setLeverUrl(r.oauth_url);
  }

  return (
    <div className="space-y-6">
      <div>
        <div className="text-2xl font-semibold">Integrations</div>
        <div className="text-sm text-black/60">Greenhouse + Lever are now webhook-driven (no /run) with Temporal workflows.</div>
        <div className="text-xs text-black/50 mt-1">Supported: {(providersQ.data?.providers ?? []).join(", ")}</div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="rounded-2xl border border-black/10 p-4 space-y-3">
          <div className="text-sm font-semibold">Greenhouse (Harvest)</div>
          <Input label="Harvest API Key" value={ghKey} onChange={(e) => setGhKey(e.target.value)} />
          <Button onClick={connectGreenhouse}>Connect Greenhouse</Button>
          {gh && (
            <div className="text-xs text-black/60 space-y-1">
              <div>Webhook secret: <span className="font-mono">{gh.webhook_secret}</span></div>
              <div>Webhook URL: <span className="font-mono">{gh.webhook_url}</span></div>
            </div>
          )}
        </div>

        <div className="rounded-2xl border border-black/10 p-4 space-y-3">
          <div className="text-sm font-semibold">Lever (OAuth)</div>
          <Button onClick={connectLever}>Generate OAuth URL</Button>
          {leverUrl && (
            <div className="text-xs">
              <div>Open OAuth URL:</div>
              <a className="underline break-all" href={leverUrl} target="_blank" rel="noreferrer">{leverUrl}</a>
              <div className="mt-2 text-black/50">After OAuth, callback returns webhook URL + secret.</div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
