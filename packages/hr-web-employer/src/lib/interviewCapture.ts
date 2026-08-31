/**
 * Real capture: camera, microphone, and the browser's own speech recognition.
 *
 * WHAT THIS ACTUALLY DOES
 * getUserMedia -> MediaRecorder -> Blob parts uploaded to the API, plus
 * SpeechRecognition results carrying offsets from the SAME clock the recorder
 * started on. That shared clock is the whole point: it is what lets the server
 * check a transcript offset against the recording's measured duration instead
 * of against a button press.
 *
 * WHAT IT REFUSES TO PRETEND
 * If the browser has no MediaRecorder, no getUserMedia, or the user declines
 * the permission prompt, this reports that state and the UI says so. It never
 * shows a recording indicator over a recorder that is not running -- a
 * candidate who believes they are being recorded when they are not has been
 * misled about the thing they consented to.
 *
 * SpeechRecognition is Chrome and Safari only. Where it is absent the
 * interview still records; there is simply no live transcript, and the server
 * reports those segments as absent rather than inventing them.
 */

/** Bounded so a permanently failing upload cannot retry forever behind a
 *  candidate who is waiting to submit. */
const UPLOAD_MAX_ATTEMPTS = 3;
const UPLOAD_RETRY_BASE_MS = 400;

export type CaptureState =
  | "IDLE"
  | "REQUESTING_PERMISSION"
  | "PERMISSION_DENIED"
  | "UNSUPPORTED"
  | "RECORDING"
  | "STOPPED"
  /** The camera or microphone went away mid-interview (unplugged, taken by
   *  another app, permission revoked in the OS). Distinct from ERROR because
   *  the candidate can plausibly fix it, and distinct from RECORDING because
   *  we must stop showing a recording indicator the moment it stops being
   *  true. */
  | "DEVICE_LOST"
  | "ERROR";

export type SpeechResult = {
  text: string;
  start_ms: number;
  end_ms: number;
  confidence?: number;
  speaker: "CANDIDATE";
};

export type CaptureSupport = {
  getUserMedia: boolean;
  mediaRecorder: boolean;
  speechRecognition: boolean;
  /** The container this browser will actually produce. */
  mimeType: string | null;
};

/** What this browser can do, checked rather than assumed. */
export function detectSupport(): CaptureSupport {
  const hasGum =
    typeof navigator !== "undefined" &&
    !!navigator.mediaDevices?.getUserMedia;
  const hasRecorder =
    typeof window !== "undefined" && typeof window.MediaRecorder !== "undefined";

  let mimeType: string | null = null;
  if (hasRecorder) {
    for (const c of [
      "video/webm;codecs=vp9,opus",
      "video/webm;codecs=vp8,opus",
      "video/webm",
      "video/mp4",
    ]) {
      if (MediaRecorder.isTypeSupported(c)) {
        mimeType = c;
        break;
      }
    }
  }

  const SR =
    typeof window !== "undefined" &&
    ((window as any).SpeechRecognition || (window as any).webkitSpeechRecognition);

  return {
    getUserMedia: hasGum,
    mediaRecorder: hasRecorder,
    speechRecognition: !!SR,
    mimeType,
  };
}

type Handlers = {
  onState: (s: CaptureState, detail?: string) => void;
  /** Called for each finished part, with the recorder clock offset. */
  onPart: (blob: Blob, partNumber: number, offsetMs: number, durationMs: number) => void;
  onTranscript: (results: SpeechResult[]) => void;
};

export class InterviewCapture {
  private stream: MediaStream | null = null;
  private recorder: MediaRecorder | null = null;
  private recognition: any = null;
  private chunks: Blob[] = [];
  private partNumber = 0;
  private partStartedAt = 0;
  /** Recorder clock origin. Every offset below is relative to this. */
  private clockOrigin = 0;
  private pending: SpeechResult[] = [];
  /** Part uploads that have not settled. See `stop` and `flush`. */
  private inFlight = new Set<Promise<unknown>>();
  /** Parts the recorder produced, whether or not their upload succeeded. */
  private producedParts = 0;
  /** Parts whose upload failed after every retry. These are the difference
   *  between what the candidate recorded and what the server actually holds,
   *  and the one number that must never be rounded down to zero. */
  private failedPartNumbers: number[] = [];
  /** True once a deliberate stop() has begun. Stopping our own tracks must not
   *  be reported to the candidate as "your camera disappeared". */
  private stopping = false;
  private stoppedResolvers: Array<() => void> = [];
  private support = detectSupport();

  constructor(private handlers: Handlers) {}

  get supported(): CaptureSupport {
    return this.support;
  }

  /** Elapsed on the recorder clock, which is what the server verifies against. */
  now(): number {
    return this.clockOrigin ? Date.now() - this.clockOrigin : 0;
  }

  async start(opts: { video: boolean; audio: boolean }): Promise<boolean> {
    this.support = detectSupport();

    if (!this.support.getUserMedia || !this.support.mediaRecorder) {
      this.handlers.onState(
        "UNSUPPORTED",
        "this browser cannot record. The interview can still run as text.",
      );
      return false;
    }

    this.handlers.onState("REQUESTING_PERMISSION");
    try {
      this.stream = await navigator.mediaDevices.getUserMedia({
        video: opts.video ? { width: 1280, height: 720 } : false,
        audio: opts.audio,
      });
    } catch (e: any) {
      // Distinguishing these matters: "you said no" and "there is no camera"
      // need different things from the person reading the message.
      const name = e?.name ?? "";
      if (name === "NotAllowedError" || name === "SecurityError") {
        this.handlers.onState(
          "PERMISSION_DENIED",
          "camera and microphone access was declined",
        );
      } else if (name === "NotFoundError" || name === "DevicesNotFoundError") {
        this.handlers.onState(
          "UNSUPPORTED",
          "no camera or microphone was found on this device",
        );
      } else {
        this.handlers.onState("ERROR", e?.message ?? String(e));
      }
      return false;
    }

    this.clockOrigin = Date.now();
    this.watchDevices();
    this.startPart();
    this.startRecognition();
    this.handlers.onState("RECORDING");
    return true;
  }

  private startPart() {
    if (!this.stream) return;
    this.chunks = [];
    this.partNumber += 1;
    this.partStartedAt = this.now();

    const mime = this.support.mimeType ?? "video/webm";
    this.recorder = new MediaRecorder(this.stream, { mimeType: mime });

    this.recorder.ondataavailable = (ev) => {
      if (ev.data && ev.data.size > 0) this.chunks.push(ev.data);
    };
    // A recorder that errors mid-part is not still recording. Without this the
    // failure was invisible and the part was lost with no state change.
    this.recorder.onerror = (ev: any) => {
      this.handlers.onState(
        "ERROR",
        ev?.error?.message ?? "the recorder stopped unexpectedly",
      );
    };
    this.recorder.onstop = () => {
      const blob = new Blob(this.chunks, { type: mime });
      const duration = this.now() - this.partStartedAt;
      // A zero-byte part is refused by the server on purpose; do not send one.
      if (blob.size > 0) {
        this.producedParts += 1;
        // TRACK THE UPLOAD SO IT CAN BE WAITED ON.
        // `onPart` is async. Without holding the promise, `stop()` returned
        // while the LAST part -- the candidate's final answer -- was still
        // being uploaded, the page moved to "done", and closing the tab lost
        // it silently. `flush()` is what makes that waitable.
        const sent = this.sendPartWithRetry(
          blob, this.partNumber, this.partStartedAt, duration,
        );
        this.inFlight.add(sent);
        void sent.finally(() => this.inFlight.delete(sent));
      }
      this.stoppedResolvers.splice(0).forEach((r) => r());
    };
    // A timeslice means a dropped connection still leaves usable parts rather
    // than one blob that never got flushed.
    this.recorder.start(5000);
  }

  /**
   * Upload one part, retrying a transient failure a bounded number of times.
   *
   * A dropped part used to be swallowed by `.catch(() => undefined)`: the
   * candidate saw a successful interview, the server held fewer parts than were
   * recorded, and nobody was told. Retrying handles the common case (a brief
   * network blip mid-answer); recording the failure handles the rest, because a
   * part that is genuinely lost must be reported, not hidden.
   */
  private sendPartWithRetry(
    blob: Blob, part: number, startedAt: number, duration: number,
  ): Promise<void> {
    const attempt = async (tries: number): Promise<void> => {
      try {
        await this.handlers.onPart(blob, part, startedAt, duration);
      } catch (err) {
        if (tries >= UPLOAD_MAX_ATTEMPTS) {
          this.failedPartNumbers.push(part);
          // Not a state change: recording continues, and a mid-interview error
          // banner over a working camera helps nobody. It surfaces at flush(),
          // where the decision to finalize is actually made.
          return;
        }
        await new Promise((r) =>
          setTimeout(r, UPLOAD_RETRY_BASE_MS * 2 ** (tries - 1)),
        );
        return attempt(tries + 1);
      }
    };
    const sent = attempt(1);
    this.inFlight.add(sent);
    void sent.finally(() => this.inFlight.delete(sent));
    return sent;
  }

  /**
   * Watch the tracks we were granted. If the camera is unplugged, claimed by
   * another application, or revoked in OS settings, the track ends: the
   * recorder quietly stops producing data while the UI happily goes on showing
   * a recording indicator. Stop the part so what was captured is kept, then say
   * what happened.
   */
  private watchDevices() {
    if (!this.stream) return;
    for (const track of this.stream.getTracks()) {
      track.onended = () => {
        if (this.stopping) return;      // we ended it ourselves
        if (!this.recorder || this.recorder.state === "inactive") return;
        const kind = track.kind === "video" ? "camera" : "microphone";
        try {
          this.recorder.stop();          // flush the part; keep what we have
        } catch {
          /* already stopping */
        }
        this.stopRecognition();
        this.handlers.onState(
          "DEVICE_LOST",
          `the ${kind} stopped being available during the interview`,
        );
      };
    }
  }

  /** Close the current part and open the next. Used on reconnect. */
  rollPart() {
    if (this.recorder && this.recorder.state !== "inactive") {
      this.recorder.stop();
    }
    this.startPart();
  }

  /** Tear down recognition without letting `onend` restart it. */
  private stopRecognition() {
    if (!this.recognition) return;
    try {
      this.recognition.onend = null;   // else onend restarts it
      this.recognition.stop();
    } catch {
      /* ignore */
    }
  }

  private startRecognition() {
    const SR =
      (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SR) return;

    this.recognition = new SR();
    this.recognition.continuous = true;
    this.recognition.interimResults = false;
    this.recognition.lang = "en-US";

    let segmentStart = this.now();
    this.recognition.onresult = (event: any) => {
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const r = event.results[i];
        if (!r.isFinal) continue;
        const alt = r[0];
        const end = this.now();
        this.pending.push({
          text: alt.transcript.trim(),
          start_ms: segmentStart,
          end_ms: end,
          confidence: typeof alt.confidence === "number" ? alt.confidence : undefined,
          speaker: "CANDIDATE",
        });
        segmentStart = end;
      }
    };
    // Recognition stops itself on silence; restart while still recording.
    this.recognition.onend = () => {
      if (this.recorder && this.recorder.state === "recording") {
        try {
          this.recognition.start();
        } catch {
          /* already starting */
        }
      }
    };
    try {
      this.recognition.start();
    } catch {
      /* some browsers throw if called twice */
    }
  }

  /** Hand over the transcript captured since the last call. */
  takeTranscript(): SpeechResult[] {
    const out = this.pending;
    this.pending = [];
    return out;
  }

  /** How many part uploads have not settled yet. */
  get pendingUploads(): number {
    return this.inFlight.size;
  }

  /**
   * How many parts this recorder produced, INCLUDING any whose upload failed.
   *
   * This is what the client seals with. It deliberately counts what was
   * RECORDED rather than what was successfully sent: if part three failed to
   * upload, sealing with 2 would tell the server the recording is complete
   * when it is missing an answer. Sealing with 3 makes the server report
   * INCOMPLETE and name the gap, which is the truth.
   */
  get partsProduced(): number {
    return this.producedParts;
  }

  /** Part numbers whose upload failed every retry. Non-empty means the server
   *  holds LESS than was recorded, and the session must not be presented as a
   *  complete one. */
  get lostParts(): number[] {
    return [...this.failedPartNumbers];
  }

  /**
   * Stop recording and resolve once every part has finished uploading.
   *
   * THIS USED TO BE SYNCHRONOUS AND FIRE-AND-FORGET.
   * `MediaRecorder.stop()` flushes its final buffer ASYNCHRONOUSLY, so the
   * last part -- the candidate's answer to the final question -- was still
   * being assembled and uploaded when this returned. The page moved to "done"
   * immediately, and a candidate who closed the tab lost that answer's
   * recording with no sign anything had gone wrong.
   *
   * The tracks are also released only AFTER the recorder has flushed. Killing
   * them first can truncate the final chunk.
   */
  async stop(): Promise<void> {
    this.stopping = true;
    this.stopRecognition();

    if (this.recorder && this.recorder.state !== "inactive") {
      const flushed = new Promise<void>((resolve) => {
        this.stoppedResolvers.push(resolve);
        // Never hang the UI on a recorder that does not fire onstop.
        setTimeout(resolve, 4000);
      });
      this.recorder.stop();
      await flushed;
    }

    this.stream?.getTracks().forEach((t) => t.stop());
    this.stream = null;
    this.handlers.onState("STOPPED");

    await this.flush();
  }

  /** Wait for every in-flight part upload to settle. */
  async flush(): Promise<void> {
    while (this.inFlight.size) {
      await Promise.allSettled([...this.inFlight]);
    }
  }
}

/** Upload one captured part. Multipart, because it is a file. */
export async function uploadPart(
  apiBase: string,
  interviewId: string,
  blob: Blob,
  opts: {
    partNumber: number;
    offsetMs: number;
    durationMs: number;
    attemptId?: string | null;
    mediaKind?: "VIDEO" | "AUDIO";
    headers?: Record<string, string>;
  },
): Promise<{ recording_id: string; sha256: string; storage_kind: string }> {
  const form = new FormData();
  form.append("file", blob, `part-${opts.partNumber}.webm`);
  form.append("media_kind", opts.mediaKind ?? "VIDEO");
  form.append("part_number", String(opts.partNumber));
  form.append("timeline_offset_ms", String(Math.max(0, Math.round(opts.offsetMs))));
  form.append("duration_ms", String(Math.max(0, Math.round(opts.durationMs))));
  if (opts.attemptId) form.append("attempt_id", opts.attemptId);

  const res = await fetch(`${apiBase}/interview-v2/${interviewId}/media`, {
    method: "POST",
    body: form,
    headers: opts.headers ?? {},
  });
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      detail = typeof body?.detail === "string" ? body.detail : JSON.stringify(body?.detail);
    } catch {
      /* keep the status */
    }
    throw new Error(detail);
  }
  return res.json();
}
