"use client";
import { Pill } from "@/components/ds";
import type { InterviewInsight } from "./types";

export function InterviewInsights({ items }: { items: InterviewInsight[] }) {
  if (items.length === 0) return <div className="text-sm text-muted">No insights recorded.</div>;
  return (
    <ul className="space-y-2">
      {items.map((i) => (
        <li
          key={i.id}
          className={`rounded-md border p-3 ${
            i.severity === "block" ? "border-danger-line bg-danger-bg" :
            i.severity === "warn" ? "border-warn-line bg-warn-bg" :
            "border-line bg-canvas"
          }`}
        >
          <div className="flex items-center justify-between">
            <div className="text-sm font-semibold text-ink">{i.title}</div>
            <Pill tone={i.severity === "block" ? "danger" : i.severity === "warn" ? "warn" : "info"}>
              {i.type.replace(/_/g, " ")}
            </Pill>
          </div>
          <div className="text-xs text-body mt-0.5">{i.description}</div>
          {i.evidence.length > 0 && (
            <ul className="mt-1 text-2xs text-muted italic">
              {i.evidence.slice(0, 2).map((e, j) => <li key={j}>"{e}"</li>)}
            </ul>
          )}
          {i.recommended_action && (
            <div className="mt-1 text-2xs text-ink">→ {i.recommended_action}</div>
          )}
        </li>
      ))}
    </ul>
  );
}
