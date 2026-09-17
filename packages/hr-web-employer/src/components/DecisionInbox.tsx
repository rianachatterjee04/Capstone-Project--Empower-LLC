"use client";

import { useEffect, useState } from "react";
import { apiPost, detailMessage } from "@/lib/api";
import { useToast } from "./Toast";

export default function DecisionInbox() {
  const [events, setEvents] = useState<any[]>([]);
  const toast = useToast();

  useEffect(() => {
    function handler(e: any) {
      if (e.detail?.type === "decision_required") {
        setEvents(prev => [e.detail, ...prev]);
      }
    }

    window.addEventListener("org-event", handler);
    return () => window.removeEventListener("org-event", handler);
  }, []);

  if (!events.length) return null;

  return (
    <div className="fixed bottom-6 right-6 w-96 space-y-3 z-50">
      {events.map((e, i) => (
        <div key={i} className="bg-white border rounded-xl shadow-xl p-4">
          <h3 className="font-bold text-lg">{e.title}</h3>
          <p className="text-gray-600">{e.message}</p>

          <div className="flex gap-2 mt-4">
            {e.actions?.map((a: any) => (
              <button
                key={a.id}
                className="px-3 py-2 bg-black text-white rounded-lg"
                onClick={() =>
                  // Route to the HR backend via apiPost (env base + demo token),
                  // not a bare /api path that the proxy would send elsewhere.
                  apiPost("/decisions/respond", { id: e.id, action: a.id })
                    .then(() => {
                      toast.success(`${a.label} recorded for "${e.title}"`);
                      setEvents((prev) => prev.filter((ev) => ev !== e));
                    })
                    .catch((err) => {
                      toast.error(`Couldn't record "${a.label}": ${detailMessage(err)}`);
                    })
                }
              >
                {a.label}
              </button>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

