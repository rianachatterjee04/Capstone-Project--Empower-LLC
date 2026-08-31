"use client";
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch, apiPost } from "@/lib/api";
import { Button } from "@/components/Button";
import { Input } from "@/components/Input";
import { Textarea } from "@/components/Textarea";

type Doc = { id: string; title: string; category: string; source: string; preview: string };
type Citation = { id: string; title: string; category: string };
type Answer = {
  question: string;
  answer: string;
  audience: string;
  citations: Citation[];
  needs_escalation: boolean;
  disclaimer: string;
};

type ChatItem = { role: "user" | "assistant"; question?: string; answer?: Answer };

const SUGGESTIONS = [
  "How many PTO days do I get per year?",
  "Walk me through 401(k) matching.",
  "What does parental leave look like?",
  "How do I report a workplace concern?",
  "What benefits start on day one?",
];

export default function AssistantPage() {
  const qc = useQueryClient();
  const [question, setQuestion] = useState("");
  const [chat, setChat] = useState<ChatItem[]>([]);
  const [busy, setBusy] = useState(false);

  const [docTitle, setDocTitle] = useState("");
  const [docBody, setDocBody] = useState("");
  const [docCategory, setDocCategory] = useState("policy");

  const docsQ = useQuery({ queryKey: ["helpdesk-docs"], queryFn: () => apiFetch<{ items: Doc[] }>("/ai-helpdesk/documents") });
  const docs = docsQ.data?.items ?? [];

  async function ask(q?: string) {
    const final = (q ?? question).trim();
    if (!final) return;
    setBusy(true);
    setChat((prev) => [...prev, { role: "user", question: final }]);
    setQuestion("");
    try {
      const ans = await apiPost<Answer>("/ai-helpdesk/ask", { question: final });
      setChat((prev) => [...prev, { role: "assistant", answer: ans }]);
    } catch (e: any) {
      setChat((prev) => [...prev, { role: "assistant", answer: { question: final, answer: e?.message ?? "Error", audience: "employee", citations: [], needs_escalation: true, disclaimer: "" } }]);
    } finally {
      setBusy(false);
    }
  }

  async function uploadDoc() {
    if (!docTitle.trim() || !docBody.trim()) return;
    await apiPost("/ai-helpdesk/documents", { title: docTitle, body: docBody, category: docCategory });
    setDocTitle("");
    setDocBody("");
    await qc.invalidateQueries({ queryKey: ["helpdesk-docs"] });
  }

  return (
    <div className="space-y-6">
      <div>
        <div className="text-2xl font-semibold">AI Helpdesk</div>
        <div className="text-sm text-black/60">
          Ask anything about benefits, PTO, payroll, policies. Answers are grounded in your policy library with citations.
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2 rounded-2xl border border-black/10 p-5 space-y-4">
          <div className="space-y-3 min-h-[320px] max-h-[60vh] overflow-y-auto">
            {chat.length === 0 ? (
              <div className="text-sm text-black/40 py-6 text-center">Ask a question to get started.</div>
            ) : (
              chat.map((item, i) => {
                if (item.role === "user") {
                  return (
                    <div key={i} className="flex justify-end">
                      <div className="rounded-2xl bg-black text-white px-4 py-2 text-sm max-w-[80%]">{item.question}</div>
                    </div>
                  );
                }
                const a = item.answer!;
                return (
                  <div key={i} className="space-y-2">
                    <div className="rounded-2xl bg-black/[0.04] px-4 py-3 text-sm">{a.answer}</div>
                    {a.citations.length > 0 && (
                      <div className="flex flex-wrap gap-1 text-xs">
                        {a.citations.map((c) => (
                          <span key={c.id} className="rounded-full bg-white border border-black/15 px-2 py-0.5">
                            📎 {c.title}
                          </span>
                        ))}
                      </div>
                    )}
                    {a.needs_escalation && (
                      <div className="rounded-xl bg-amber-50 border border-amber-200 p-2 text-xs text-amber-900">
                        Not found in policy library. Consider routing this to a human HR partner.
                      </div>
                    )}
                  </div>
                );
              })
            )}
          </div>
          <div className="flex flex-wrap gap-1">
            {SUGGESTIONS.map((s) => (
              <button key={s} onClick={() => ask(s)} disabled={busy} className="rounded-full border border-black/15 px-3 py-1 text-xs hover:bg-black/5">
                {s}
              </button>
            ))}
          </div>
          <div className="flex gap-2">
            <input
              className="flex-1 rounded-xl border border-black/15 px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-black/20"
              placeholder="Ask a question…"
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); ask(); }}}
            />
            <Button onClick={() => ask()} disabled={!question.trim() || busy}>{busy ? "Thinking…" : "Send"}</Button>
          </div>
        </div>

        <div className="rounded-2xl border border-black/10 p-5 space-y-3">
          <div className="text-sm font-semibold">Knowledge library</div>
          <div className="text-xs text-black/60">
            Add internal policies, benefit summaries, payroll notes — the assistant grounds answers in these documents.
          </div>
          <div className="space-y-2">
            <Input label="Title" value={docTitle} onChange={(e) => setDocTitle(e.target.value)} />
            <label className="block">
              <div className="mb-1 text-sm font-medium">Category</div>
              <select className="w-full rounded-xl border border-black/15 px-3 py-2 text-sm" value={docCategory} onChange={(e) => setDocCategory(e.target.value)}>
                {["policy","benefits","time_off","payroll","onboarding","security","ethics"].map((c) => <option key={c}>{c}</option>)}
              </select>
            </label>
            <Textarea label="Body" rows={5} value={docBody} onChange={(e) => setDocBody(e.target.value)} />
            <Button onClick={uploadDoc} disabled={!docTitle.trim() || !docBody.trim()}>Add document</Button>
          </div>
          <div className="border-t border-black/5 pt-3">
            <div className="text-xs uppercase tracking-wide text-black/40 mb-2">Documents ({docs.length})</div>
            <div className="space-y-2 max-h-72 overflow-y-auto">
              {docs.map((d) => (
                <div key={d.id} className="rounded-lg border border-black/10 p-2">
                  <div className="flex items-center justify-between">
                    <div className="text-sm font-medium">{d.title}</div>
                    <span className="text-[10px] text-black/40 uppercase">{d.category}</span>
                  </div>
                  <div className="text-xs text-black/60 mt-1 line-clamp-3">{d.preview}</div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
