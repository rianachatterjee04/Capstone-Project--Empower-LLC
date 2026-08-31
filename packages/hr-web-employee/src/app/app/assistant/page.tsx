"use client";
import { useState } from "react";
import { apiPost } from "@/lib/api";
import { Button } from "@/components/Button";

type Answer = {
  question: string; answer: string; audience: string;
  citations: { id: string; title: string; category: string }[];
  needs_escalation: boolean; disclaimer: string;
};

const SUGGESTIONS = [
  "How many PTO days do I get?",
  "What's the 401(k) match?",
  "How does parental leave work?",
  "How do I report a workplace concern?",
  "When do benefits start?",
];

export default function AssistantPage() {
  const [question, setQuestion] = useState("");
  const [chat, setChat] = useState<{ role: "user" | "assistant"; q?: string; a?: Answer }[]>([]);
  const [busy, setBusy] = useState(false);

  async function ask(q?: string) {
    const final = (q ?? question).trim();
    if (!final) return;
    setBusy(true);
    setChat((c) => [...c, { role: "user", q: final }]);
    setQuestion("");
    try {
      const a = await apiPost<Answer>("/ai-helpdesk/ask", { question: final });
      setChat((c) => [...c, { role: "assistant", a }]);
    } catch (e: any) {
      setChat((c) => [...c, { role: "assistant", a: { question: final, answer: e?.message ?? "Error", audience: "employee", citations: [], needs_escalation: true, disclaimer: "" } }]);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <div className="text-2xl font-semibold">Ask HR</div>
        <div className="text-sm text-black/60">AI-grounded answers from our policy library. Cited and confidential.</div>
      </div>

      <div className="rounded-2xl border border-black/10 p-4 space-y-3">
        <div className="space-y-3 min-h-[280px] max-h-[60vh] overflow-y-auto">
          {chat.length === 0 ? (
            <div className="text-sm text-black/40 py-6 text-center">Ask a question to get started.</div>
          ) : chat.map((m, i) => m.role === "user" ? (
            <div key={i} className="flex justify-end"><div className="rounded-2xl bg-black text-white px-4 py-2 text-sm max-w-[80%]">{m.q}</div></div>
          ) : (
            <div key={i} className="space-y-2">
              <div className="rounded-2xl bg-black/[0.04] px-4 py-3 text-sm">{m.a!.answer}</div>
              {m.a!.citations.length > 0 && (
                <div className="flex flex-wrap gap-1 text-xs">
                  {m.a!.citations.map((c) => <span key={c.id} className="rounded-full bg-white border border-black/15 px-2 py-0.5">📎 {c.title}</span>)}
                </div>
              )}
              {m.a!.needs_escalation && <div className="rounded-xl bg-amber-50 border border-amber-200 p-2 text-xs text-amber-900">Not in the policy library — your HR partner has been notified.</div>}
            </div>
          ))}
        </div>
        <div className="flex flex-wrap gap-1">
          {SUGGESTIONS.map((s) => (
            <button key={s} onClick={() => ask(s)} disabled={busy} className="rounded-full border border-black/15 px-3 py-1 text-xs hover:bg-black/5">{s}</button>
          ))}
        </div>
        <div className="flex gap-2">
          <input
            className="flex-1 rounded-xl border border-black/15 px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-black/20"
            placeholder="Ask anything…"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); ask(); }}}
          />
          <Button onClick={() => ask()} disabled={!question.trim() || busy}>{busy ? "…" : "Ask"}</Button>
        </div>
      </div>
    </div>
  );
}
