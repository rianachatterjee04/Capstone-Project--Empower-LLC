"use client";

import { useState } from "react";
import { apiPost } from "@/lib/api";

type Provider = {
  provider: string;
  connected: boolean;
};

type GreenhouseConnectResponse = {
  ok: boolean;
  provider: string;
  webhook_secret?: string;
  sync_started?: boolean;
};

type LeverConnectResponse = {
  ok: boolean;
  provider: string;
  oauth_url: string;
};

export default function IntegrationsPage() {
  const [greenhouseMessage, setGreenhouseMessage] = useState("");
  const [leverUrl, setLeverUrl] = useState("");
  const [providers, setProviders] = useState<Provider[]>([]);

  async function loadProviders() {
    const r = await fetch("http://localhost:8000/api/integrations/providers", {
      headers: {
        "x-org-id": "11111111-1111-1111-1111-111111111111",
        "x-user-id": "22222222-2222-2222-2222-222222222222",
        "x-role": "owner",
      },
      cache: "no-store",
    });

    const data: { items?: Provider[] } = await r.json();
    setProviders(data.items || []);
  }

  async function connectGreenhouse() {
    const r = await apiPost<GreenhouseConnectResponse>("/integrations/connect/greenhouse", {
      api_key: "demo-greenhouse-api-key",
    });

    setGreenhouseMessage(
      r.sync_started
        ? "Greenhouse connected and initial sync started."
        : "Greenhouse connected, but Temporal sync did not start locally."
    );
  }

  async function connectLever() {
    const r = await apiPost<LeverConnectResponse>("/integrations/connect/lever", {});
    setLeverUrl(r.oauth_url);
  }

  return (
    <div className="space-y-6">
      <div className="text-2xl font-semibold">Integrations</div>

      <div className="flex gap-3">
        <button className="border rounded px-4 py-2" onClick={loadProviders}>
          Load providers
        </button>
        <button className="border rounded px-4 py-2" onClick={connectGreenhouse}>
          Connect Greenhouse
        </button>
        <button className="border rounded px-4 py-2" onClick={connectLever}>
          Connect Lever
        </button>
      </div>

      {greenhouseMessage && (
        <div className="rounded border p-3 text-sm">{greenhouseMessage}</div>
      )}

      {leverUrl && (
        <div className="rounded border p-3 text-sm break-all">
          <div className="font-medium mb-1">Lever OAuth URL</div>
          <a className="underline" href={leverUrl} target="_blank" rel="noreferrer">
            {leverUrl}
          </a>
        </div>
      )}

      <div className="rounded border p-4">
        <div className="font-medium mb-2">Providers</div>
        <div className="space-y-2">
          {providers.length === 0 ? (
            <div className="text-sm text-black/60">No providers loaded yet.</div>
          ) : (
            providers.map((p) => (
              <div key={p.provider} className="flex items-center justify-between">
                <span>{p.provider}</span>
                <span>{p.connected ? "Connected" : "Not connected"}</span>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
