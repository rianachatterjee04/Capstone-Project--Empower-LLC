"use client";
/**
 * Candidate-facing adaptive interview.
 *
 * Design goals (vs. the #1 Mercor complaints):
 *   - ZERO friction: open a link → one calm consent → start. No dense form.
 *   - ONE question at a time in a warm chat. The AI acknowledges + reacts,
 *     shows a typing indicator, and a CALM progress indicator (competencies
 *     covered, not a scary countdown).
 *   - ANTI-BLACK-BOX: a visible "AI-assisted · human-reviewed" badge + an
 *     "ask for clarification" affordance.
 *   - VOICE-READY + VOICE-REAL: Web Speech STT/TTS with capability detection;
 *     text is ALWAYS available (accessibility) and captions/transcript stay on
 *     screen at all times.
 *   - Mobile-first, matches the Foundry design system.
 */
import { useEffect, useRef, useState } from "react";
import { apiFetch, apiPost } from "@/lib/api";
import { useSpeech, prefersReducedMotion } from "@/hooks/useSpeech";

type Question = { id: string; competency: string; question: string; rationale?: string };
type CoverageItem = { competency: string; label: string; signal_strength: number; probes: number; covered: boolean };
type CoverageMap = { competencies: CoverageItem[]; n_covered: number; n_total: number; pct_covered: number };
type Analysis = { quality: string; competency: string; score: number };
type NextMove = {
  done?: boolean;
  reason?: string;
  move?: string;
  acknowledgement?: string;
  question?: Question;
  source?: string;
};
type AnswerResponse = { analysis: Analysis; coverage_map: CoverageMap; next: NextMove };
type StateResponse = {
  session_id: string;
  rubric: string[];
  coverage_map: CoverageMap;
  asked_count: number;
  current_question: Question | null;
  transcript: { question: string; answer: string; competency: string }[];
  done: boolean;
  status: string;
};

type ChatMsg = { id: string; role: "ai" | "candidate" | "system"; text: string; competency?: string };

const human = (c: string) => (c || "").replace(/_/g, " ");

/* ------------------------------------------------------------------ badge */
function ReviewBadge() {
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full border border-line bg-surface px-2.5 py-1 text-[11px] font-medium text-body">
      <span className="h-1.5 w-1.5 rounded-full bg-accent" />
      AI-assisted · human-reviewed
    </span>
  );
}

/* -------------------------------------------------------------- progress */
function Progress({ cov }: { cov: CoverageMap | null }) {
  if (!cov) return null;
  return (
    <div className="w-full">
      <div className="mb-2 flex items-center justify-between text-[11px] uppercase tracking-wide text-muted">
        <span>Topics covered</span>
        <span className="tabular-nums">{cov.n_covered} / {cov.n_total}</span>
      </div>
      <div className="flex flex-wrap gap-1.5">
        {cov.competencies.map((c) => {
          const pct = Math.round(c.signal_strength * 100);
          return (
            <div
              key={c.competency}
              title={`${human(c.label)} — ${pct}% signal`}
              className={[
                "flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] transition-colors",
                c.covered
                  ? "border-accent/30 bg-accent-soft text-accent-softFg"
                  : "border-line bg-surface text-body",
              ].join(" ")}
            >
              <span
                className={[
                  "h-1.5 w-1.5 rounded-full",
                  c.covered ? "bg-accent" : pct > 5 ? "bg-warn" : "bg-line",
                ].join(" ")}
              />
              {human(c.label)}
            </div>
          );
        })}
      </div>
    </div>
  );
}

/* ---------------------------------------------------------- typing dots */
function Typing() {
  return (
    <div className="flex items-center gap-1 px-1 py-2" aria-label="Interviewer is thinking">
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className="h-2 w-2 rounded-full bg-muted/60"
          style={{ animation: `fp-fade-in 900ms ${i * 160}ms infinite alternate` }}
        />
      ))}
    </div>
  );
}

/* --------------------------------------------------------------- bubbles */
function Bubble({ msg }: { msg: ChatMsg }) {
  if (msg.role === "system") {
    return <div className="my-2 text-center text-xs text-muted">{msg.text}</div>;
  }
  const isAi = msg.role === "ai";
  return (
    <div className={`flex ${isAi ? "justify-start" : "justify-end"} fp-fade-in`}>
      <div className={`max-w-[85%] ${isAi ? "" : "text-right"}`}>
        {isAi && msg.competency && (
          <div className="mb-1 text-[10px] uppercase tracking-wide text-faint">{human(msg.competency)}</div>
        )}
        <div
          className={[
            "rounded-2xl px-4 py-2.5 text-[15px] leading-relaxed",
            isAi ? "bg-surface border border-line text-ink" : "bg-accent text-accent-fg",
          ].join(" ")}
        >
          {msg.text}
        </div>
      </div>
    </div>
  );
}

/* ================================================================= page */
export default function CandidateInterviewPage({ params }: { params: { sessionId: string } }) {
  const { sessionId } = params;

  const [phase, setPhase] = useState<"loading" | "consent" | "live" | "done" | "error">("loading");
  const [errorMsg, setErrorMsg] = useState("");
  const [jobTitle, setJobTitle] = useState("");
  const [candidateName, setCandidateName] = useState("");
  const [messages, setMessages] = useState<ChatMsg[]>([]);
  const [current, setCurrent] = useState<Question | null>(null);
  const [coverage, setCoverage] = useState<CoverageMap | null>(null);
  const [draft, setDraft] = useState("");
  const [thinking, setThinking] = useState(false);
  const [voiceOn, setVoiceOn] = useState(false);
  const [startedAt, setStartedAt] = useState(0);

  const scrollRef = useRef<HTMLDivElement>(null);
  const lastSpokenRef = useRef<string>("");

  const speech = useSpeech({
    onFinal: (t) => setDraft((d) => (d ? d + " " : "") + t),
  });

  // persisted voice preference
  useEffect(() => {
    const saved = typeof window !== "undefined" ? window.localStorage.getItem("fp_voice_on") : null;
    if (saved === "1" && !prefersReducedMotion()) setVoiceOn(true);
  }, []);
  useEffect(() => {
    if (typeof window !== "undefined") window.localStorage.setItem("fp_voice_on", voiceOn ? "1" : "0");
  }, [voiceOn]);

  // load session
  useEffect(() => {
    (async () => {
      try {
        const st = await apiFetch<StateResponse>(`/ai-interview/sessions/${sessionId}/state`);
        const full = await apiFetch<any>(`/ai-interview/sessions/${sessionId}`).catch(() => null);
        setJobTitle(full?.job_title || "the role");
        setCandidateName(full?.candidate_name || "");
        setCoverage(st.coverage_map);
        setCurrent(st.current_question);
        if (st.status === "completed" || st.done) setPhase("done");
        else setPhase("consent");
      } catch (e: any) {
        setErrorMsg(e?.message || "Could not load this interview.");
        setPhase("error");
      }
    })();
  }, [sessionId]);

  // autoscroll
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, thinking]);

  // speak the latest AI question when voice is on
  useEffect(() => {
    if (!voiceOn || phase !== "live") return;
    const lastAi = [...messages].reverse().find((m) => m.role === "ai");
    if (lastAi && lastAi.text !== lastSpokenRef.current) {
      lastSpokenRef.current = lastAi.text;
      speech.speak(lastAi.text);
    }
  }, [messages, voiceOn, phase, speech]);

  function pushAi(text: string, competency?: string) {
    setMessages((m) => [...m, { id: crypto.randomUUID(), role: "ai", text, competency }]);
  }

  function begin() {
    setPhase("live");
    setStartedAt(Date.now());
    const opener = current?.question || "Thanks for joining. Tell me a little about yourself to get us started.";
    setThinking(true);
    setTimeout(() => {
      setThinking(false);
      pushAi(opener, current?.competency);
    }, 600);
  }

  async function submitAnswer() {
    const answer = draft.trim();
    if (!answer || !current || thinking) return;
    if (speech.listening) speech.stopListening();

    setMessages((m) => [...m, { id: crypto.randomUUID(), role: "candidate", text: answer }]);
    setDraft("");
    const durationSec = startedAt ? Math.max(1, Math.round((Date.now() - startedAt) / 1000)) : 0;
    setThinking(true);

    try {
      const res = await apiPost<AnswerResponse>(`/ai-interview/sessions/${sessionId}/answer`, {
        question_id: current.id,
        answer,
        mode: voiceOn ? "audio" : "written",
        duration_sec: durationSec,
      });
      setCoverage(res.coverage_map);
      const next = res.next;

      // small human pause so it feels considered, not instant
      await new Promise((r) => setTimeout(r, 550));
      setThinking(false);

      if (next.done) {
        setCurrent(null);
        await complete();
        return;
      }
      if (next.acknowledgement) pushAi(next.acknowledgement);
      if (next.question) {
        setCurrent(next.question);
        setStartedAt(Date.now());
        // let the ack land, then ask
        setTimeout(() => pushAi(next.question!.question, next.question!.competency), 500);
      }
    } catch (e: any) {
      setThinking(false);
      pushAi("Sorry — something hiccupped on our side. Take your time; you can send that again.");
    }
  }

  async function complete() {
    setThinking(true);
    try {
      await apiPost(`/ai-interview/sessions/${sessionId}/complete`, {});
    } catch { /* best-effort */ }
    setThinking(false);
    speech.cancelSpeaking();
    setPhase("done");
  }

  function askClarification() {
    if (!current) return;
    setMessages((m) => [
      ...m,
      { id: crypto.randomUUID(), role: "candidate", text: "Could you clarify what you're looking for?" },
    ]);
    setThinking(true);
    setTimeout(() => {
      setThinking(false);
      pushAi(
        `Of course — I'm listening for a concrete example from your own experience on ${human(
          current.competency
        )}. A specific situation, what you did, and how it turned out is perfect. There's no single right answer.`,
        current.competency
      );
    }, 700);
  }

  /* ----------------------------------------------------------- render */
  if (phase === "loading") {
    return (
      <Shell>
        <div className="flex h-[60vh] items-center justify-center text-muted">Preparing your interview…</div>
      </Shell>
    );
  }

  if (phase === "error") {
    return (
      <Shell>
        <div className="mx-auto max-w-md py-20 text-center">
          <h1 className="text-xl font-semibold text-ink">We couldn't open this interview</h1>
          <p className="mt-2 text-sm text-body">{errorMsg}</p>
          <p className="mt-4 text-xs text-muted">If you were given a link, try opening it again or contact the recruiter.</p>
        </div>
      </Shell>
    );
  }

  if (phase === "consent") {
    return (
      <Shell>
        <div className="mx-auto max-w-lg py-12 fp-fade-in">
          <div className="mb-6 flex justify-center"><ReviewBadge /></div>
          <h1 className="text-center text-3xl font-semibold tracking-tight text-ink">
            {candidateName ? `Hi ${candidateName.split(" ")[0]} — ` : "Hi — "}ready when you are.
          </h1>
          <p className="mt-4 text-center text-[15px] leading-relaxed text-body">
            This is a short, conversational interview for the <span className="font-medium text-ink">{jobTitle}</span>{" "}
            role. It's just a few questions, one at a time. Take your time — there's no timer, and you can answer by
            typing or by voice.
          </p>
          <div className="mt-6 rounded-2xl border border-line bg-surface p-4 text-sm text-body">
            <p className="font-medium text-ink">A few things to know</p>
            <ul className="mt-2 space-y-1.5 text-[13px]">
              <li>• Your answers are analysed by AI to help the hiring team, and <span className="font-medium text-ink">a human reviews the result</span>.</li>
              <li>• You'll see the topics we cover as we go — no hidden scoring bar.</li>
              <li>• You can ask for clarification on any question at any time.</li>
            </ul>
          </div>
          <button
            onClick={begin}
            className="mt-6 w-full rounded-xl bg-accent px-4 py-3 text-[15px] font-medium text-accent-fg transition hover:opacity-90"
          >
            I understand — let's begin
          </button>
          <p className="mt-3 text-center text-xs text-muted">By continuing you consent to AI-assisted analysis of your responses.</p>
        </div>
      </Shell>
    );
  }

  if (phase === "done") {
    return (
      <Shell>
        <div className="mx-auto max-w-md py-20 text-center fp-fade-in">
          <div className="mx-auto mb-5 flex h-14 w-14 items-center justify-center rounded-full bg-accent-soft text-accent-softFg">
            <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
              <path d="M5 13l4 4L19 7" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </div>
          <h1 className="text-2xl font-semibold text-ink">Thank you{candidateName ? `, ${candidateName.split(" ")[0]}` : ""}.</h1>
          <p className="mt-3 text-[15px] leading-relaxed text-body">
            That's everything. Your responses have been shared with the hiring team, who will review them and follow up
            with next steps. We appreciate the time you took today.
          </p>
          <div className="mt-6 flex justify-center"><ReviewBadge /></div>
        </div>
      </Shell>
    );
  }

  // live
  return (
    <Shell>
      <div className="flex h-[100dvh] flex-col">
        {/* header */}
        <header className="border-b border-line bg-surface/80 px-4 py-3 backdrop-blur">
          <div className="mx-auto flex max-w-2xl items-center justify-between gap-3">
            <div className="min-w-0">
              <div className="truncate text-sm font-semibold text-ink">{jobTitle} · interview</div>
              <div className="text-[11px] text-muted">Take your time — there's no timer.</div>
            </div>
            <div className="flex items-center gap-2">
              {speech.ttsSupported && (
                <button
                  onClick={() => {
                    const nv = !voiceOn;
                    setVoiceOn(nv);
                    if (!nv) speech.cancelSpeaking();
                  }}
                  aria-pressed={voiceOn}
                  title={voiceOn ? "Voice on — AI reads questions aloud" : "Voice off"}
                  className={[
                    "inline-flex h-9 items-center gap-1.5 rounded-full border px-3 text-xs font-medium transition",
                    voiceOn ? "border-accent/30 bg-accent-soft text-accent-softFg" : "border-line bg-surface text-body",
                  ].join(" ")}
                >
                  <SpeakerIcon on={voiceOn} />
                  Voice
                </button>
              )}
              <ReviewBadge />
            </div>
          </div>
        </header>

        {/* progress */}
        <div className="border-b border-line bg-canvas px-4 py-3">
          <div className="mx-auto max-w-2xl"><Progress cov={coverage} /></div>
        </div>

        {/* chat */}
        <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-5">
          <div className="mx-auto flex max-w-2xl flex-col gap-3">
            {messages.map((m) => <Bubble key={m.id} msg={m} />)}
            {thinking && (
              <div className="flex justify-start">
                <div className="rounded-2xl border border-line bg-surface px-2"><Typing /></div>
              </div>
            )}
          </div>
        </div>

        {/* composer */}
        <div className="border-t border-line bg-surface px-4 py-3">
          <div className="mx-auto max-w-2xl">
            {speech.listening && (
              <div className="mb-2 flex items-center gap-2 text-xs text-accent-softFg">
                <span className="flex h-2 w-2"><span className="h-2 w-2 animate-ping rounded-full bg-accent/60" /></span>
                Listening… {speech.interim && <span className="italic text-muted">"{speech.interim}"</span>}
              </div>
            )}
            <div className="flex items-end gap-2">
              {speech.sttSupported && (
                <button
                  onClick={() => (speech.listening ? speech.stopListening() : speech.startListening())}
                  aria-pressed={speech.listening}
                  title={speech.listening ? "Stop microphone" : "Answer with your voice"}
                  className={[
                    "flex h-11 w-11 flex-none items-center justify-center rounded-xl border transition",
                    speech.listening ? "border-danger/40 bg-danger-bg text-danger" : "border-line bg-canvas text-body hover:bg-sunken",
                  ].join(" ")}
                >
                  <MicIcon active={speech.listening} />
                </button>
              )}
              <textarea
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) { e.preventDefault(); submitAnswer(); }
                }}
                rows={2}
                placeholder="Type your answer… (or use the mic)"
                className="min-h-[44px] flex-1 resize-none rounded-xl border border-line bg-canvas px-3 py-2.5 text-[15px] text-ink outline-none focus:border-accent/40 focus:ring-2 focus:ring-accent/15"
              />
              <button
                onClick={submitAnswer}
                disabled={!draft.trim() || thinking}
                className="flex h-11 flex-none items-center justify-center rounded-xl bg-accent px-4 text-sm font-medium text-accent-fg transition hover:opacity-90 disabled:opacity-40"
              >
                Send
              </button>
            </div>
            <div className="mt-2 flex items-center justify-between">
              <button onClick={askClarification} className="text-xs text-muted underline-offset-2 hover:text-accent hover:underline">
                Ask for clarification
              </button>
              <span className="text-[11px] text-faint">⌘/Ctrl + Enter to send</span>
            </div>
          </div>
        </div>
      </div>
    </Shell>
  );
}

/* ------------------------------------------------------------ chrome */
function Shell({ children }: { children: React.ReactNode }) {
  return <div className="min-h-[100dvh] bg-canvas text-ink">{children}</div>;
}

function SpeakerIcon({ on }: { on: boolean }) {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M11 5L6 9H2v6h4l5 4V5z" strokeLinejoin="round" />
      {on && <path d="M15.5 8.5a5 5 0 010 7M18.5 6a8 8 0 010 12" strokeLinecap="round" />}
      {!on && <path d="M17 9l4 6M21 9l-4 6" strokeLinecap="round" />}
    </svg>
  );
}

function MicIcon({ active }: { active: boolean }) {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill={active ? "currentColor" : "none"} stroke="currentColor" strokeWidth="2">
      <rect x="9" y="3" width="6" height="11" rx="3" />
      <path d="M5 11a7 7 0 0014 0M12 18v3" strokeLinecap="round" />
    </svg>
  );
}
