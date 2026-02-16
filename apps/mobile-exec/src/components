import { respondToDecision } from "../services/decisions";

export default function DecisionCard({ event }) {

  async function respond(action: string) {
    await respondToDecision(event.id, action);
  }

  return (
    <div className="card shadow-lg p-4 bg-white rounded-xl">
      <h3 className="text-lg font-bold">{event.title}</h3>
      <p className="text-gray-600 mb-4">{event.message}</p>

      <div className="flex gap-2">
        {event.actions.map(a => (
          <button
            key={a.id}
            className={`btn ${a.style}`}
            onClick={() => respond(a.id)}
          >
            {a.label}
          </button>
        ))}
      </div>
    </div>
  );
}

