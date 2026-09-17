"use client";
/**
 * Platform-wide toast notifications. (#127 / #141)
 *
 * WHY THIS EXISTS
 * Before this, form actions gave no feedback at all, or a bare inline
 * `<div>{msg}</div>` that only the person still looking at that exact spot
 * on the page would ever see (see Cases, Onboarding). Actions that failed
 * silently (DecisionInbox's `.catch(() => {})`) looked indistinguishable
 * from actions that succeeded. This gives every submit/approve/deny a
 * visible, consistent confirmation, whether it worked or not.
 *
 * USAGE
 *   const toast = useToast();
 *   toast.success("Packet created");
 *   toast.error("Could not save: " + detailMessage(e));
 *
 * Wrapped around the app once, in Providers.tsx.
 */
import React, { createContext, useCallback, useContext, useMemo, useRef, useState } from "react";
import clsx from "clsx";
import { IconCheck, IconClose } from "./icons";

export type ToastTone = "success" | "error" | "warn" | "info";

type ToastInput = {
  message: string;
  title?: string;
  tone?: ToastTone;
  /** ms before auto-dismiss. 0 disables auto-dismiss. Defaults by tone. */
  duration?: number;
};

type ToastItem = ToastInput & { id: number; tone: ToastTone };

type ToastAPI = {
  show: (input: ToastInput) => number;
  success: (message: string, opts?: Omit<ToastInput, "message" | "tone">) => number;
  error: (message: string, opts?: Omit<ToastInput, "message" | "tone">) => number;
  warn: (message: string, opts?: Omit<ToastInput, "message" | "tone">) => number;
  info: (message: string, opts?: Omit<ToastInput, "message" | "tone">) => number;
  dismiss: (id: number) => void;
};

const ToastContext = createContext<ToastAPI | null>(null);

const TONE_CLASSES: Record<ToastTone, string> = {
  success: "bg-success-bg text-success-fg border-success-line",
  error: "bg-danger-bg text-danger-fg border-danger-line",
  warn: "bg-warn-bg text-warn-fg border-warn-line",
  info: "bg-info-bg text-info-fg border-info-line",
};

// Errors stay up longer than a routine success — worth the extra second to read.
const DEFAULT_DURATION: Record<ToastTone, number> = {
  success: 4000,
  info: 4000,
  warn: 5000,
  error: 6500,
};

const svgBase = {
  width: 14,
  height: 14,
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.6,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
};

function ToastIcon({ tone }: { tone: ToastTone }) {
  if (tone === "success") return <IconCheck size={14} />;
  if (tone === "error")
    return (
      <svg {...svgBase} aria-hidden>
        <circle cx="12" cy="12" r="9" />
        <path d="M12 7.5v5.5" />
        <path d="M12 16.5h.01" />
      </svg>
    );
  if (tone === "warn")
    return (
      <svg {...svgBase} aria-hidden>
        <path d="M10.3 3.9 2.9 17a1.6 1.6 0 0 0 1.4 2.4h15.4a1.6 1.6 0 0 0 1.4-2.4L13.7 3.9a1.6 1.6 0 0 0-2.8 0Z" />
        <path d="M12 9.5v4" />
        <path d="M12 16.5h.01" />
      </svg>
    );
  return (
    <svg {...svgBase} aria-hidden>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 11v5" />
      <path d="M12 8h.01" />
    </svg>
  );
}

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const idRef = useRef(0);
  const timers = useRef<Map<number, ReturnType<typeof setTimeout>>>(new Map());

  const dismiss = useCallback((id: number) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
    const timer = timers.current.get(id);
    if (timer) {
      clearTimeout(timer);
      timers.current.delete(id);
    }
  }, []);

  const show = useCallback(
    (input: ToastInput) => {
      const id = ++idRef.current;
      const tone = input.tone ?? "info";
      const duration = input.duration ?? DEFAULT_DURATION[tone];
      setToasts((prev) => [...prev, { ...input, id, tone }]);
      if (duration > 0) {
        timers.current.set(id, setTimeout(() => dismiss(id), duration));
      }
      return id;
    },
    [dismiss],
  );

  const api = useMemo<ToastAPI>(
    () => ({
      show,
      success: (message, opts) => show({ ...opts, message, tone: "success" }),
      error: (message, opts) => show({ ...opts, message, tone: "error" }),
      warn: (message, opts) => show({ ...opts, message, tone: "warn" }),
      info: (message, opts) => show({ ...opts, message, tone: "info" }),
      dismiss,
    }),
    [show, dismiss],
  );

  return (
    <ToastContext.Provider value={api}>
      {children}
      {/* Fixed viewport, top-right so it never collides with DecisionInbox
         (bottom-right). aria-live announces new toasts to screen readers
         without needing focus to move. */}
      <div
        className="pointer-events-none fixed top-4 right-4 z-[100] flex w-full max-w-sm flex-col gap-2"
        role="region"
        aria-label="Notifications"
      >
        {toasts.map((t) => (
          <div
            key={t.id}
            role="status"
            aria-live="polite"
            className={clsx(
              "fp-slide-in pointer-events-auto flex items-start gap-2.5 rounded-lg border p-3 shadow-lift",
              TONE_CLASSES[t.tone],
            )}
          >
            <span className="mt-0.5 shrink-0" aria-hidden>
              <ToastIcon tone={t.tone} />
            </span>
            <div className="min-w-0 flex-1">
              {t.title ? <div className="text-sm font-medium">{t.title}</div> : null}
              <div className="text-sm break-words">{t.message}</div>
            </div>
            <button
              type="button"
              onClick={() => dismiss(t.id)}
              aria-label="Dismiss notification"
              className="shrink-0 opacity-60 transition-opacity hover:opacity-100"
            >
              <IconClose size={14} />
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): ToastAPI {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used within a ToastProvider");
  return ctx;
}
