"use client";
/**
 * VideoInterviewer — calm AI-driven interview surface.
 *
 * Capabilities:
 *  - AI reads the question aloud (Web Speech Synthesis)
 *  - Records video + audio via MediaRecorder (or audio-only)
 *  - Live transcript via Web Speech Recognition (Chrome / Edge)
 *  - Falls back to written input if the browser doesn't support the APIs
 *  - On stop, emits { transcript, duration_sec, words_per_minute, has_face, media_meta }
 *
 * Privacy notes are surfaced inline; nothing is uploaded by the component —
 * the parent decides whether to send the media blob anywhere. For the demo
 * the recording stays in-browser as a local blob URL the user can replay.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { Action, Pill } from "./ds";
import { IconSparkle, IconClose, IconCheck } from "./icons";

export type InterviewMode = "video" | "audio" | "written";

export type AnswerSubmission = {
  transcript: string;
  mode: InterviewMode;
  duration_sec: number;
  words_per_minute: number;
  has_face: boolean;
  media_meta: { kind: string; size_bytes?: number; mime_type?: string };
};

type Props = {
  mode: InterviewMode;
  question: string;
  rationale?: string;
  /** Called when the candidate clicks "Use this answer". */
  onSubmit: (a: AnswerSubmission) => void;
  /** Allow the parent to dismiss / cancel. */
  onCancel?: () => void;
};

declare global {
  interface Window {
    webkitSpeechRecognition?: any;
    SpeechRecognition?: any;
  }
}

function supportsSpeechRecognition(): boolean {
  if (typeof window === "undefined") return false;
  return Boolean(window.webkitSpeechRecognition || window.SpeechRecognition);
}

function supportsMediaRecorder(): boolean {
  if (typeof window === "undefined") return false;
  return Boolean(window.MediaRecorder && navigator?.mediaDevices?.getUserMedia);
}

function fmt(sec: number): string {
  const m = Math.floor(sec / 60).toString().padStart(2, "0");
  const s = Math.floor(sec % 60).toString().padStart(2, "0");
  return `${m}:${s}`;
}

export function VideoInterviewer({ mode, question, rationale, onSubmit, onCancel }: Props) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const recognitionRef = useRef<any>(null);
  const chunksRef = useRef<Blob[]>([]);
  const startTimestampRef = useRef<number>(0);
  const finalTranscriptRef = useRef<string>("");
  const interimTranscriptRef = useRef<string>("");
  const tickRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const hasFaceRef = useRef<boolean>(false);

  const [stream, setStream] = useState<MediaStream | null>(null);
  const [permissionState, setPermissionState] = useState<"idle" | "requesting" | "granted" | "denied">("idle");
  const [recording, setRecording] = useState(false);
  const [paused, setPaused] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [transcript, setTranscript] = useState("");
  const [interim, setInterim] = useState("");
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [mediaMeta, setMediaMeta] = useState<{ size_bytes?: number; mime_type?: string }>({});
  const [error, setError] = useState<string | null>(null);
  const [speaking, setSpeaking] = useState(false);
  const [sttSupported] = useState<boolean>(supportsSpeechRecognition());
  const [recorderSupported] = useState<boolean>(supportsMediaRecorder());

  // ------- Speak the question aloud (AI interviewer voice) -------
  const askAloud = useCallback(() => {
    if (typeof window === "undefined" || !window.speechSynthesis) {
      setError("Browser doesn't support text-to-speech. Read the question above.");
      return;
    }
    window.speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(question);
    u.rate = 0.98;
    u.pitch = 1.0;
    u.volume = 1.0;
    u.onstart = () => setSpeaking(true);
    u.onend = () => setSpeaking(false);
    u.onerror = () => setSpeaking(false);
    window.speechSynthesis.speak(u);
  }, [question]);

  // ------- Permissions + stream -------
  const requestStream = useCallback(async () => {
    if (mode === "written") return null;
    if (!recorderSupported) {
      setError("Browser doesn't support media capture. Switch to written mode.");
      return null;
    }
    setPermissionState("requesting");
    try {
      const constraints: MediaStreamConstraints =
        mode === "video"
          ? { video: { width: { ideal: 1280 }, height: { ideal: 720 } }, audio: true }
          : { audio: true };
      const s = await navigator.mediaDevices.getUserMedia(constraints);
      setStream(s);
      setPermissionState("granted");
      if (mode === "video" && videoRef.current) {
        videoRef.current.srcObject = s;
        videoRef.current.muted = true;
        await videoRef.current.play().catch(() => undefined);
        hasFaceRef.current = true;
      }
      return s;
    } catch (e) {
      setPermissionState("denied");
      setError("Permission denied. Switch to written mode or grant camera/mic access in your browser.");
      return null;
    }
  }, [mode, recorderSupported]);

  // Auto-request the stream when the component mounts for video/audio modes
  useEffect(() => {
    if (mode === "written") return;
    void requestStream();
    return () => {
      stopAll();
      stream?.getTracks().forEach((t) => t.stop());
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode]);

  // Clean up on unmount
  useEffect(() => {
    return () => {
      stopAll();
      stream?.getTracks().forEach((t) => t.stop());
      if (previewUrl) URL.revokeObjectURL(previewUrl);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ------- Speech recognition wiring -------
  const startSTT = useCallback(() => {
    if (!sttSupported) return;
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    const rec = new SR();
    rec.continuous = true;
    rec.interimResults = true;
    rec.lang = "en-US";
    rec.onresult = (event: any) => {
      let finalChunk = "";
      let interimChunk = "";
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const r = event.results[i];
        if (r.isFinal) finalChunk += r[0].transcript;
        else interimChunk += r[0].transcript;
      }
      if (finalChunk) {
        finalTranscriptRef.current = (finalTranscriptRef.current + " " + finalChunk).trim();
        setTranscript(finalTranscriptRef.current);
        setInterim("");
      } else {
        interimTranscriptRef.current = interimChunk;
        setInterim(interimChunk);
      }
    };
    rec.onerror = () => undefined; // soft-fail; transcript stays partial
    rec.onend = () => {
      // Auto-restart while we're still recording (some browsers stop on silence)
      if (recording && recorderRef.current?.state === "recording") {
        try { rec.start(); } catch { /* noop */ }
      }
    };
    recognitionRef.current = rec;
    try { rec.start(); } catch { /* noop */ }
  }, [recording, sttSupported]);

  const stopSTT = useCallback(() => {
    try { recognitionRef.current?.stop(); } catch { /* noop */ }
    recognitionRef.current = null;
  }, []);

  // ------- Recorder lifecycle -------
  const startRecording = useCallback(async () => {
    setError(null);
    setPreviewUrl(null);
    chunksRef.current = [];
    finalTranscriptRef.current = "";
    interimTranscriptRef.current = "";
    setTranscript("");
    setInterim("");

    let s = stream;
    if (!s && mode !== "written") {
      s = await requestStream();
      if (!s) return;
    }

    startTimestampRef.current = Date.now();
    setElapsed(0);
    tickRef.current = setInterval(() => {
      setElapsed((Date.now() - startTimestampRef.current) / 1000);
    }, 250);

    if (s && recorderSupported) {
      const mr = new MediaRecorder(s, { mimeType: pickMime(mode) });
      mr.ondataavailable = (e) => {
        if (e.data && e.data.size > 0) chunksRef.current.push(e.data);
      };
      mr.onstop = () => {
        const blob = new Blob(chunksRef.current, { type: mr.mimeType || "video/webm" });
        const url = URL.createObjectURL(blob);
        setPreviewUrl(url);
        setMediaMeta({ size_bytes: blob.size, mime_type: blob.type });
      };
      mr.start(500);
      recorderRef.current = mr;
    }

    setRecording(true);
    setPaused(false);

    if (sttSupported) startSTT();
  }, [mode, recorderSupported, requestStream, sttSupported, startSTT, stream]);

  const pauseRecording = useCallback(() => {
    try { recorderRef.current?.pause(); } catch { /* noop */ }
    if (tickRef.current) { clearInterval(tickRef.current); tickRef.current = null; }
    setPaused(true);
  }, []);

  const resumeRecording = useCallback(() => {
    try { recorderRef.current?.resume(); } catch { /* noop */ }
    const tStart = Date.now() - elapsed * 1000;
    startTimestampRef.current = tStart;
    tickRef.current = setInterval(() => {
      setElapsed((Date.now() - tStart) / 1000);
    }, 250);
    setPaused(false);
  }, [elapsed]);

  const stopAll = useCallback(() => {
    if (tickRef.current) { clearInterval(tickRef.current); tickRef.current = null; }
    try { recorderRef.current?.stop(); } catch { /* noop */ }
    stopSTT();
    setRecording(false);
    setPaused(false);
  }, [stopSTT]);

  const handleStop = useCallback(() => {
    stopAll();
  }, [stopAll]);

  // Final submission
  const finalText = useMemo(() => transcript || "", [transcript]);
  const wpm = useMemo(() => {
    const words = finalText.split(/\s+/).filter(Boolean).length;
    return elapsed > 0 ? Math.round((words / elapsed) * 60) : 0;
  }, [finalText, elapsed]);

  function submit() {
    const out: AnswerSubmission = {
      transcript: mode === "written" ? finalText : (finalText.trim() || interim.trim()),
      mode,
      duration_sec: Math.round(elapsed),
      words_per_minute: wpm,
      has_face: mode === "video" && hasFaceRef.current,
      media_meta: { kind: mode, ...mediaMeta },
    };
    if (!out.transcript.trim()) {
      setError("No transcript captured. Type the answer or try again.");
      return;
    }
    onSubmit(out);
  }

  // Written mode — just a textarea
  if (mode === "written") {
    return (
      <div className="space-y-3">
        <WrittenPad
          value={transcript}
          onChange={(v) => { setTranscript(v); finalTranscriptRef.current = v; }}
          question={question}
          onAsk={askAloud}
          speaking={speaking}
        />
        <div className="flex items-center justify-end gap-2">
          {onCancel && <Action variant="subtle" onClick={onCancel}>Cancel</Action>}
          <Action variant="primary" onClick={submit} disabled={!transcript.trim()}>
            <IconCheck /> Use this answer
          </Action>
        </div>
      </div>
    );
  }

  // Video / audio mode
  return (
    <div className="space-y-3">
      <div className="rounded-md border border-line bg-canvas p-3">
        <div className="flex items-start justify-between gap-2 mb-2">
          <div>
            <div className="fp-eyebrow">Question</div>
            <div className="text-sm font-semibold text-ink">{question}</div>
            {rationale && <div className="text-xs text-muted mt-0.5">{rationale}</div>}
          </div>
          <Action variant="subtle" size="sm" onClick={askAloud} disabled={speaking}>
            <IconSparkle /> {speaking ? "Speaking…" : "AI reads aloud"}
          </Action>
        </div>

        {mode === "video" ? (
          <div className="relative rounded-md overflow-hidden bg-ink/90 aspect-video">
            <video ref={videoRef} className="w-full h-full object-cover" autoPlay playsInline muted />
            {recording && (
              <div className="absolute top-2 left-2 flex items-center gap-2 rounded-full bg-danger-fg/95 text-canvas text-xs px-2 py-0.5">
                <span className="block h-2 w-2 rounded-full bg-canvas animate-pulse" /> REC · {fmt(elapsed)}
              </div>
            )}
            {!recording && !previewUrl && (
              <div className="absolute inset-0 flex items-center justify-center text-canvas text-sm opacity-80">
                {permissionState === "requesting" ? "Requesting camera + mic…" : "Ready"}
              </div>
            )}
          </div>
        ) : (
          <div className="rounded-md bg-canvas border border-line p-4 flex items-center justify-between">
            <div className="text-sm text-muted">{recording ? "Recording audio…" : "Audio ready"}</div>
            <div className="font-mono text-sm text-ink tabular-nums">{fmt(elapsed)}</div>
          </div>
        )}

        <div className="mt-3 flex flex-wrap items-center gap-2">
          {!recording ? (
            <Action variant="primary" onClick={startRecording} disabled={permissionState === "requesting"}>
              ● Start recording
            </Action>
          ) : (
            <>
              {!paused ? (
                <Action variant="subtle" onClick={pauseRecording}>Pause</Action>
              ) : (
                <Action variant="subtle" onClick={resumeRecording}>Resume</Action>
              )}
              <Action variant="primary" onClick={handleStop}>Stop</Action>
            </>
          )}
          {sttSupported ? (
            <Pill tone={recording ? "success" : "neutral"}>
              {recording ? "Live transcript on" : "Transcript ready"}
            </Pill>
          ) : (
            <Pill tone="warn">
              Live transcript unsupported — Chrome / Edge recommended
            </Pill>
          )}
          <span className="flex-1" />
          <div className="text-2xs uppercase tracking-eyebrow text-muted">
            {fmt(elapsed)} · ~{wpm} wpm
          </div>
        </div>

        {/* Live transcript display */}
        <div className="mt-3 rounded-md border border-line bg-surface p-3 min-h-[80px] text-sm leading-relaxed text-ink">
          {transcript || <span className="text-muted">{recording ? "Listening…" : "Transcript will appear here as you speak."}</span>}
          {interim && <span className="text-muted italic"> {interim}</span>}
        </div>

        {previewUrl && (
          <div className="mt-3">
            <div className="fp-eyebrow mb-1">Playback</div>
            {mode === "video" ? (
              <video src={previewUrl} controls className="w-full rounded-md border border-line" />
            ) : (
              <audio src={previewUrl} controls className="w-full" />
            )}
            {mediaMeta.size_bytes && (
              <div className="text-2xs uppercase tracking-eyebrow text-muted mt-1">
                {(mediaMeta.size_bytes / (1024 * 1024)).toFixed(2)} MB · {mediaMeta.mime_type}
              </div>
            )}
          </div>
        )}

        {/* Editable transcript fallback so you can correct STT mistakes before submit */}
        <div className="mt-3">
          <div className="fp-eyebrow mb-1">Edit transcript before submit (optional)</div>
          <textarea
            value={transcript}
            onChange={(e) => { setTranscript(e.target.value); finalTranscriptRef.current = e.target.value; }}
            rows={4}
            className="w-full rounded-md border border-line bg-canvas px-3 py-2 text-sm text-ink outline-none focus:bg-surface"
            placeholder={sttSupported ? "Tweak any speech-to-text mistakes here." : "Browser doesn't support live transcript — type the answer here."}
          />
        </div>

        {error && (
          <div className="mt-2 rounded-md border border-warn-line bg-warn-bg text-warn-fg text-xs px-3 py-2">
            {error}
          </div>
        )}
      </div>

      <div className="flex items-center justify-between gap-2">
        <div className="text-2xs uppercase tracking-eyebrow text-muted">
          Recording stays in your browser. Submitting only sends the transcript + duration to AI scoring.
        </div>
        <div className="flex items-center gap-2">
          {onCancel && <Action variant="subtle" onClick={onCancel}><IconClose /> Cancel</Action>}
          <Action variant="primary" onClick={submit} disabled={!transcript.trim() && !interim.trim()}>
            <IconCheck /> Use this answer
          </Action>
        </div>
      </div>
    </div>
  );
}

function WrittenPad({ value, onChange, question, onAsk, speaking }: { value: string; onChange: (v: string) => void; question: string; onAsk: () => void; speaking: boolean }) {
  return (
    <div className="rounded-md border border-line bg-canvas p-3">
      <div className="flex items-start justify-between gap-2 mb-2">
        <div>
          <div className="fp-eyebrow">Question</div>
          <div className="text-sm font-semibold text-ink">{question}</div>
        </div>
        <Action variant="subtle" size="sm" onClick={onAsk} disabled={speaking}>
          <IconSparkle /> {speaking ? "Speaking…" : "AI reads aloud"}
        </Action>
      </div>
      <textarea
        value={value}
        onChange={(e) => onChange(e.target.value)}
        rows={6}
        placeholder="Type the candidate's response (or notes you took during the live call)…"
        className="w-full rounded-md border border-line bg-surface px-3 py-2 text-sm text-ink outline-none focus:bg-surface"
      />
    </div>
  );
}

function pickMime(mode: InterviewMode): string {
  if (typeof window === "undefined") return "video/webm";
  const candidates = mode === "video"
    ? ["video/webm;codecs=vp9,opus", "video/webm;codecs=vp8,opus", "video/webm", "video/mp4"]
    : ["audio/webm;codecs=opus", "audio/webm", "audio/mp4"];
  for (const c of candidates) {
    try {
      if ((window as any).MediaRecorder?.isTypeSupported?.(c)) return c;
    } catch { /* noop */ }
  }
  return mode === "video" ? "video/webm" : "audio/webm";
}
