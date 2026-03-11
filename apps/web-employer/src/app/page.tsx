"use client";

import { Button } from "@/components/Button";

export default function LoginPage() {
  function enterPortal() {
    window.location.href = "/app";
  }

  return (
    <div className="min-h-screen flex items-center justify-center p-6">
      <div className="w-full max-w-md rounded-2xl border border-black/10 p-6 shadow-sm">
        <div className="text-xl font-semibold">Foundry People</div>
        <div className="mt-1 text-sm text-black/60">
          Employer portal local development mode
        </div>

        <div className="mt-6 space-y-3">
          <Button onClick={enterPortal}>Enter employer portal</Button>
        </div>

        <div className="mt-6 text-xs text-black/50">
          Authentication is temporarily disabled for local development.
        </div>
      </div>
    </div>
  );
}
