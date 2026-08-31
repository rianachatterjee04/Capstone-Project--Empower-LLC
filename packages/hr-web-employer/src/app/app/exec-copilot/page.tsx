"use client";
import { useState } from "react";
import { apiPost } from "@/lib/api";
import { Button } from "@/components/Button";

type Reply = {
  question: string;
  answer: string;
  facts: { headline?: string; risk_score?: number; priority_count?: number; high_risk_alerts?: number };
  citations: { id: string; title: string; category: string }[];
  disclaimer: string;
};

const SUGGESTIONS = [
  "How healthy is the company this week?",
  "Where are we exposed on hiring?",
  "Which employees are at the highest attrition risk?",
  "Any compensation issues I should know about?",
  "Are there compliance gaps to address?",
  "What should I focus on as CEO this week?",
];

export default function ExecCopilotPage() {
  const [question, setQuestion] = useState("");
  const [history, setHistory] = useState<Reply[]>([]);
  const [busy, setBusy] = useState(false);

  async function ask(q?: string) {
    const final = (q ?? question).trim();
    if (!final) return;
    setBusy(true);
    setQuestion("");
    try {
      const r = await apiPost<Reply>("/exec-copilot/ask", { question: final });
      setHistory((prev) => [r, ...prev]);
    } catch (e: any) {
      setHistory((prev) => [{ question: final, answer: e?.message ?? "Error", facts: {}, citations: [], disclaimer: "" }, ...prev]);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <div className="rounded-2xl border-2 border-black/10 p-5 bg-gradient-to-br from-purple-50 to-cyan-50">
        <div className="text-xs uppercase tracking-wide text-black/40">Executive AI Copilot</div>
        <div className="text-2xl font-bold mt-1">Ask anything about the company.</div>
        <div className="text-sm text-black/60 mt-1">Grounded in your live HR data, policy library, and workforce risk signal.</div>
      </div>

      <div className="rounded-2xl border border-black/10 p-4 space-y-3">
        <div className="flex flex-wrap gap-1">
          {SUGGESTIONS.map((s) => (
            <button key={s} onClick={() => ask(s)} disabled={busy}
              className="rounded-full border border-black/15 px-3 py-1 text-xs hover:bg-black/5">
              {s}
            </button>
          ))}
        </div>
        <div className="flex gap-2">
          <input
            className="flex-1 rounded-xl border border-black/15 px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-black/20"
            placeholder="Ask about hiring, retention, comp, risk…"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); ask(); }}}
          />
          <Button onClick={() => ask()} disabled={!question.trim() || busy}>{busy ? "Thinking…" : "Ask"}</Button>
        </div>
      </div>

      <div className="space-y-3">
        {history.length === 0 ? (
          <div className="rounded-2xl border border-black/10 p-6 text-center text-sm text-black/40">
            Try a suggestion above to start.
          </div>
        ) : history.map((r, i) => (
          <div key={i} className="rounded-2xl border border-black/10 p-4 space-y-2">
            <div className="text-xs uppercase tracking-wide text-black/40">Question</div>
            <div className="text-sm font-medium">{r.question}</div>
            <div className="text-xs uppercase tracking-wide text-black/40 pt-2">Answer</div>
            <div className="text-sm whitespace-pre-line">{r.answer}</div>
            <div className="flex flex-wrap gap-2 pt-2 text-xs">
              {r.facts.headline && <span className="rounded-full bg-black/[0.04] px-2 py-0.5">headline: {r.facts.headline}</span>}
              {r.facts.risk_score != null && <span className="rounded-full bg-rose-50 border border-rose-200 px-2 py-0.5">risk score: {r.facts.risk_score}/100</span>}
              {r.facts.priority_count != null && <span className="rounded-full bg-amber-50 border border-amber-200 px-2 py-0.5">priorities: {r.facts.priority_count}</span>}
            </div>
            {r.citations.length > 0 && (
              <div className="flex flex-wrap gap-1 pt-1">
                {r.citations.map((c) => <span key={c.id} className="rounded-full bg-white border border-black/15 px-2 py-0.5 text-xs">📎 {c.title}</span>)}
              </div>
            )}
            {r.disclaimer && <div className="text-[10px] text-black/40 italic">{r.disclaimer}</div>}
          </div>
        ))}
      </div>
    </div>
  );
}
