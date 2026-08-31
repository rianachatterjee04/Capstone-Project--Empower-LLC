"use client";
/**
 * LiveTranscript — captures the interview transcript using the browser's
 * Web Speech API and streams it to the server (consent-gated).
 *
 * Ethical design:
 *  - Recording only starts after BOTH parties grant consent
 *  - A persistent visual "● LIVE TRANSCRIPT" banner is always visible
 *  - The interviewer can pause / stop at any time
 *  - The candidate's view in a real production wiring shows the same banner
 *  - Nothing is captured before the consent step
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { Action, Pill } from "@/components/ds";
import { apiPost } from "@/lib/api";
import type { TranscriptLine } from "./types";

declare global {
  interface Window {
    webkitSpeechRecognition?: any;
    SpeechRecognition?: any;
  }
}

function supportsSpeech(): boolean {
  if (typeof window === "undefined") return false;
  return Boolean(window.webkitSpeechRecognition || window.SpeechRecognition);
}

export function LiveTranscript({
  interviewId,
  canCapture,
  onAppend,
  speakerDefault = "candidate",
}: {
  interviewId: string;
  canCapture: boolean;
  onAppend?: (l: TranscriptLine) => void;
  speakerDefault?: "candidate" | "interviewer";
}) {
  const recRef = useRef<any>(null);
  const [running, setRunning] = useState(false);
  const [interim, setInterim] = useState("");
  const [lines, setLines] = useState<TranscriptLine[]>([]);
  const [speaker, setSpeaker] = useState<"candidate" | "interviewer">(speakerDefault);
  const [supported] = useState<boolean>(supportsSpeech());
  const [err, setErr] = useState<string | null>(null);

  const push = useCallback(async (text: string) => {
    text = text.trim();
    if (!text || !canCapture) return;
    try {
      const line = await apiPost<TranscriptLine>(`/interviews/${interviewId}/transcript`, {
        speaker,
        speaker_name: speaker === "candidate" ? "Candidate" : "Interviewer",
        text,
        confidence: 0.85,
      });
      setLines((prev) => [...prev, line]);
      onAppend?.(line);
    } catch (e: any) {
      // 403 = consent not granted
      setErr(e?.message ?? "Capture failed");
    }
  }, [canCapture, interviewId, speaker, onAppend]);

  const start = useCallback(() => {
    if (!supported || !canCapture) {
      setErr(!canCapture ? "Both parties must grant consent before capture." : "Browser does not support live transcript (Chrome / Edge).");
      return;
    }
    setErr(null);
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    const rec = new SR();
    rec.continuous = true;
    rec.interimResults = true;
    rec.lang = "en-US";
    rec.onresult = (event: any) => {
      let interimChunk = "";
      let finalChunk = "";
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const r = event.results[i];
        if (r.isFinal) finalChunk += r[0].transcript;
        else interimChunk += r[0].transcript;
      }
      setInterim(interimChunk);
      if (finalChunk) {
        void push(finalChunk);
        setInterim("");
      }
    };
    rec.onend = () => {
      if (running && recRef.current === rec) {
        // Auto-restart on silence
        try { rec.start(); } catch { /* noop */ }
      }
    };
    rec.onerror = () => undefined;
    try { rec.start(); } catch { /* noop */ }
    recRef.current = rec;
    setRunning(true);
  }, [canCapture, push, running, supported]);

  const stop = useCallback(() => {
    setRunning(false);
    try { recRef.current?.stop(); } catch { /* noop */ }
    recRef.current = null;
    setInterim("");
  }, []);

  useEffect(() => () => stop(), [stop]);

  return (
    <div className="flex flex-col h-full min-h-0">
      <div className="flex items-center gap-2 mb-2">
        {running && (
          <span className="inline-flex items-center gap-1.5 rounded-full bg-danger-bg text-danger-fg border border-danger-line px-2 py-0.5 text-2xs">
            <span className="block h-1.5 w-1.5 rounded-full bg-danger-fg animate-pulse" />
            ● LIVE TRANSCRIPT
          </span>
        )}
        <div className="flex items-center gap-1">
          {(["candidate", "interviewer"] as const).map((s) => (
            <Action key={s} size="sm" variant={speaker === s ? "primary" : "subtle"} onClick={() => setSpeaker(s)}>
              {s}
            </Action>
          ))}
        </div>
        <span className="flex-1" />
        {!running ? (
          <Action variant="primary" size="sm" onClick={start} disabled={!canCapture || !supported}>● Start</Action>
        ) : (
          <Action variant="subtle" size="sm" onClick={stop}>Stop</Action>
        )}
      </div>

      {!supported && (
        <Pill tone="warn">Browser does not support live transcript — Chrome / Edge recommended</Pill>
      )}
      {!canCapture && (
        <div className="mt-2 rounded-md border border-warn-line bg-warn-bg text-warn-fg text-xs px-3 py-2">
          Capture is blocked until both candidate and interviewer grant consent.
        </div>
      )}
      {err && (
        <div className="mt-2 rounded-md border border-danger-line bg-danger-bg text-danger-fg text-xs px-3 py-2">{err}</div>
      )}

      <div className="mt-3 flex-1 min-h-0 overflow-y-auto rounded-md border border-line bg-canvas p-3 text-sm leading-relaxed">
        {lines.length === 0 && !interim ? (
          <div className="text-muted">Waiting for speech…</div>
        ) : (
          <div className="space-y-1.5">
            {lines.map((l) => (
              <div key={l.id} className="text-ink">
                <span className="text-2xs uppercase tracking-eyebrow text-muted mr-2">{l.speaker}</span>
                {l.text}
              </div>
            ))}
            {interim && (
              <div className="text-muted italic">
                <span className="text-2xs uppercase tracking-eyebrow mr-2">{speaker}</span>
                {interim}…
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
