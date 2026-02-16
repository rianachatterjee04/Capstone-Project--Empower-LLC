"use client";
import { useEffect, useState } from "react";
import { getUserContext } from "@/lib/auth";

export default function Dashboard() {
  const [ctx, setCtx] = useState<{role:string; orgId:string|null; email:string|null} | null>(null);
  useEffect(() => { getUserContext().then(setCtx); }, []);

  return (
    <div className="space-y-6">
      <div>
        <div className="text-2xl font-semibold">Dashboard</div>
        <div className="text-sm text-black/60">Employee view • {ctx?.orgId ? `Org: ${ctx.orgId}` : "No org_id in token yet"}</div>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="rounded-2xl border border-black/10 p-4">
          <div className="text-sm text-black/60">Role</div>
          <div className="text-lg font-semibold">{ctx?.role ?? "—"}</div>
        </div>
        <div className="rounded-2xl border border-black/10 p-4">
          <div className="text-sm text-black/60">Signed in</div>
          <div className="truncate text-lg font-semibold">{ctx?.email ?? "—"}</div>
        </div>
        <div className="rounded-2xl border border-black/10 p-4">
          <div className="text-sm text-black/60">Next</div>
          <div className="text-lg font-semibold">Complete onboarding</div>
        </div>
      </div>
    </div>
  );
}
