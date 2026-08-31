"use client";

import { IconSparkle } from "./icons";
import { useShellState } from "./ShellState";

/**
 * Employee Topbar — calm, single "Ask HR" affordance.
 */
export function Topbar() {
  const { toggleAssistant } = useShellState();

  return (
    <header className="sticky top-0 z-20 border-b border-line bg-canvas/85 backdrop-blur">
      <div className="flex items-center justify-end gap-3 px-6 h-14">
        <button
          onClick={toggleAssistant}
          className="h-9 px-3 rounded-md bg-accent text-accent-fg hover:opacity-90 transition-opacity duration-150 ease-calm flex items-center gap-2 text-sm"
        >
          <IconSparkle />
          <span>Ask HR</span>
        </button>
      </div>
    </header>
  );
}
