"use client";
import { respondToDecision } from "@/services/decisions";

interface Action {
  id: string;
  label: string;
  style?: string;
}

interface DecisionEvent {
  id: string;
  title: string;
  message: string;
  actions: Action[];
}

export default function DecisionCard({ event }: { event: DecisionEvent }) {
  async function respond(action: string) {
    await respondToDecision(event.id, action);
  }

  return (
    <div className="bg-white border border-black/10 shadow-lg p-4 rounded-xl">
      <h3 className="text-lg font-bold">{event.title}</h3>
      <p className="text-gray-600 mb-4">{event.message}</p>
      <div className="flex gap-2">
        {event.actions.map(a => (
          <button
            key={a.id}
            className="px-3 py-2 bg-black text-white rounded-lg text-sm hover:opacity-90"
            onClick={() => respond(a.id)}
          >
            {a.label}
          </button>
        ))}
      </div>
    </div>
  );
}
