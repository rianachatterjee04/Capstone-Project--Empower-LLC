"use client";
/**
 * useSpeech — browser-native voice for the candidate interview.
 *
 * v1 ships the **Web Speech API** path: zero external deps, CSP-safe, no keys.
 *   - STT: window.SpeechRecognition || webkitSpeechRecognition
 *   - TTS: window.speechSynthesis
 *
 * PRODUCTION PROVIDER-SWAP SEAM
 * -----------------------------
 * For higher-accuracy / cross-browser voice, swap the two primitives below for
 * a server-side provider (OpenAI Realtime / Whisper, or Deepgram) behind the
 * same {startListening/stopListening/onFinal} and {speak/cancel} interface —
 * the candidate UI never has to change. Firefox has no SpeechRecognition, so
 * server-side STT is the natural upgrade there. Everything here is capability-
 * detected: when a primitive is missing, its control is hidden and the UI
 * falls back to text cleanly (accessibility + anti-black-box: captions/text are
 * ALWAYS on screen, never audio-only).
 */
import { useCallback, useEffect, useRef, useState } from "react";

type SpeechState = {
  sttSupported: boolean;
  ttsSupported: boolean;
  listening: boolean;
  interim: string;
  speaking: boolean;
};

export function useSpeech(opts?: { onFinal?: (text: string) => void }) {
  const [state, setState] = useState<SpeechState>({
    sttSupported: false,
    ttsSupported: false,
    listening: false,
    interim: "",
    speaking: false,
  });

  const recognitionRef = useRef<any>(null);
  const onFinalRef = useRef(opts?.onFinal);
  onFinalRef.current = opts?.onFinal;
  const wantListeningRef = useRef(false);

  // ---- capability detection (runs once, client-only) ----
  useEffect(() => {
    if (typeof window === "undefined") return;
    // Accessibility / policy escape hatch: an org or user can force text-only,
    // which also exercises the exact same fallback path as a browser that
    // lacks the Web Speech API (e.g. Firefox STT).
    const forceText = window.localStorage.getItem("fp_force_text") === "1";
    const SR = forceText ? null : (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    const ttsSupported = !forceText && "speechSynthesis" in window && typeof window.SpeechSynthesisUtterance !== "undefined";
    setState((s) => ({ ...s, sttSupported: !!SR, ttsSupported }));

    if (SR) {
      const rec = new SR();
      rec.continuous = true;
      rec.interimResults = true;
      rec.lang = "en-US";
      rec.onresult = (e: any) => {
        let interim = "";
        for (let i = e.resultIndex; i < e.results.length; i++) {
          const res = e.results[i];
          const txt = res[0]?.transcript ?? "";
          if (res.isFinal) {
            if (txt.trim()) onFinalRef.current?.(txt.trim());
          } else {
            interim += txt;
          }
        }
        setState((s) => ({ ...s, interim }));
      };
      rec.onend = () => {
        // Chrome auto-stops after silence; restart if the user still wants to talk.
        if (wantListeningRef.current) {
          try { rec.start(); return; } catch { /* already started */ }
        }
        setState((s) => ({ ...s, listening: false, interim: "" }));
      };
      rec.onerror = () => {
        setState((s) => ({ ...s, listening: false }));
      };
      recognitionRef.current = rec;
    }

    return () => {
      wantListeningRef.current = false;
      try { recognitionRef.current?.stop(); } catch { /* noop */ }
      try { window.speechSynthesis?.cancel(); } catch { /* noop */ }
    };
  }, []);

  const startListening = useCallback(() => {
    const rec = recognitionRef.current;
    if (!rec) return;
    wantListeningRef.current = true;
    try {
      rec.start();
      setState((s) => ({ ...s, listening: true, interim: "" }));
    } catch { /* already running */ }
  }, []);

  const stopListening = useCallback(() => {
    wantListeningRef.current = false;
    try { recognitionRef.current?.stop(); } catch { /* noop */ }
    setState((s) => ({ ...s, listening: false, interim: "" }));
  }, []);

  // ---- TTS ----
  const pickVoice = useCallback((): SpeechSynthesisVoice | null => {
    if (typeof window === "undefined" || !("speechSynthesis" in window)) return null;
    const voices = window.speechSynthesis.getVoices() || [];
    // Prefer a natural en-US voice; fall back to any English voice.
    const preferred = ["Samantha", "Google US English", "Microsoft Aria", "Microsoft Jenny"];
    for (const name of preferred) {
      const v = voices.find((x) => x.name.includes(name));
      if (v) return v;
    }
    return voices.find((v) => v.lang?.startsWith("en")) || voices[0] || null;
  }, []);

  const speak = useCallback((text: string) => {
    if (typeof window === "undefined" || !("speechSynthesis" in window) || !text) return;
    try {
      window.speechSynthesis.cancel();
      const u = new SpeechSynthesisUtterance(text);
      const v = pickVoice();
      if (v) u.voice = v;
      u.rate = 1.0;
      u.pitch = 1.0;
      u.onstart = () => setState((s) => ({ ...s, speaking: true }));
      u.onend = () => setState((s) => ({ ...s, speaking: false }));
      u.onerror = () => setState((s) => ({ ...s, speaking: false }));
      window.speechSynthesis.speak(u);
    } catch { /* noop */ }
  }, [pickVoice]);

  const cancelSpeaking = useCallback(() => {
    if (typeof window === "undefined" || !("speechSynthesis" in window)) return;
    try { window.speechSynthesis.cancel(); } catch { /* noop */ }
    setState((s) => ({ ...s, speaking: false }));
  }, []);

  return { ...state, startListening, stopListening, speak, cancelSpeaking };
}

/** True when the user's OS asks for reduced motion (we default voice OFF then). */
export function prefersReducedMotion(): boolean {
  if (typeof window === "undefined" || !window.matchMedia) return false;
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}
