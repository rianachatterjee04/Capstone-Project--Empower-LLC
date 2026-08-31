"use client";

import { useState } from "react";
import { apiPost } from "@/lib/api";
import { useShellState } from "./ShellState";
import { Action, Pill } from "./ds";
import { IconClose, IconSparkle } from "./icons";

type Answer = {
  question: string;
  answer: string;
  audience: string;
  citations: { id: string; title: string; category: string }[];
  needs_escalation: boolean;
  disclaimer: string;
};

const PROMPTS = [
  "Where are we exposed on hiring?",
  "Summarise workforce risk this week",
  "Draft a balanced manager review for Avery Chen",
  "What's our parental leave policy?",
];

/**
 * Calm slide-over assistant. Embedded RAG helpdesk — no chatbot blob, no
 * floating button. Triggered from the topbar or Cmd+K.
 */
export function AssistantDock() {
  const { assistantOpen, closeAssistant } = useShellState();
  const [q, setQ] = useState("");
  const [chat, setChat] = useState<{ role: "user" | "assistant"; question?: string; answer?: Answer }[]>([]);
  const [busy, setBusy] = useState(false);

  async function ask(text?: string) {
    const question = (text ?? q).trim();
    if (!question || busy) return;
    setBusy(true);
    setChat((c) => [...c, { role: "user", question }]);
    setQ("");
    try {
      const a = await apiPost<Answer>("/ai-helpdesk/ask", { question });
      setChat((c) => [...c, { role: "assistant", answer: a }]);
    } catch (e: any) {
      setChat((c) => [...c, { role: "assistant", answer: { question, answer: e?.message ?? "Error", audience: "admin", citations: [], needs_escalation: true, disclaimer: "" } }]);
    } finally {
      setBusy(false);
    }
  }

  if (!assistantOpen) return null;

  return (
    <div className="fixed inset-0 z-40">
      <div className="absolute inset-0 bg-ink/10" onClick={closeAssistant} />
      <aside className="absolute right-0 top-0 h-full w-[420px] max-w-[90vw] bg-surface border-l border-line shadow-lift fp-slide-in flex flex-col">
        <header className="h-14 flex items-center justify-between px-5 border-b border-line">
          <div className="flex items-center gap-2 text-sm">
            <IconSparkle className="text-muted" />
            <span className="font-semibold text-ink">Assistant</span>
            <Pill tone="info">RAG · cited</Pill>
          </div>
          <button onClick={closeAssistant} className="text-muted hover:text-ink"><IconClose /></button>
        </header>

        <div className="flex-1 overflow-y-auto px-5 py-4 space-y-3">
          {chat.length === 0 ? (
            <div className="space-y-3">
              <div className="text-sm text-muted">Ask anything. Answers cite your policy library and live workforce signals.</div>
              <div className="space-y-1.5">
                {PROMPTS.map((p) => (
                  <button
                    key={p}
                    onClick={() => ask(p)}
                    className="w-full text-left text-sm text-ink bg-canvas border border-line rounded-md px-3 py-2 hover:bg-sunken transition-colors duration-150 ease-calm"
                  >
                    {p}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            chat.map((m, i) =>
              m.role === "user" ? (
                <div key={i} className="flex justify-end">
                  <div className="rounded-2xl bg-accent text-accent-fg px-3.5 py-2 text-sm max-w-[85%]">{m.question}</div>
                </div>
              ) : (
                <div key={i} className="space-y-2 max-w-[95%]">
                  <div className="rounded-2xl bg-canvas border border-line px-3.5 py-2.5 text-sm text-ink whitespace-pre-line">{m.answer!.answer}</div>
                  {m.answer!.citations.length > 0 && (
                    <div className="flex flex-wrap gap-1.5">
                      {m.answer!.citations.map((c) => (
                        <Pill key={c.id} tone="neutral">📎 {c.title}</Pill>
                      ))}
                    </div>
                  )}
                  {m.answer!.needs_escalation && (
                    <div className="rounded-md bg-warn-bg border border-warn-line text-warn-fg text-xs px-3 py-2">
                      Not in policy library — route to a human HR partner.
                    </div>
                  )}
                </div>
              )
            )
          )}
        </div>

        <div className="border-t border-line p-3 flex items-center gap-2">
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); ask(); } }}
            placeholder="Ask the assistant…"
            className="flex-1 h-9 rounded-md border border-line bg-canvas px-3 text-sm text-ink placeholder:text-muted outline-none focus:bg-surface"
          />
          <Action variant="primary" size="sm" onClick={() => ask()} disabled={!q.trim() || busy}>
            {busy ? "…" : "Ask"}
          </Action>
        </div>
      </aside>
    </div>
  );
}
