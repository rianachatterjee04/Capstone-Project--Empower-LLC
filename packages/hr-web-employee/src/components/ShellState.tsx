"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

type ShellState = {
  paletteOpen: boolean;
  openPalette: () => void;
  closePalette: () => void;

  assistantOpen: boolean;
  openAssistant: () => void;
  closeAssistant: () => void;
  toggleAssistant: () => void;

  inboxOpen: boolean;
  openInbox: () => void;
  closeInbox: () => void;
  toggleInbox: () => void;
};

const Ctx = createContext<ShellState | null>(null);

export function ShellStateProvider({ children }: { children: React.ReactNode }) {
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [assistantOpen, setAssistantOpen] = useState(false);
  const [inboxOpen, setInboxOpen] = useState(false);

  const openPalette = useCallback(() => setPaletteOpen(true), []);
  const closePalette = useCallback(() => setPaletteOpen(false), []);
  const openAssistant = useCallback(() => setAssistantOpen(true), []);
  const closeAssistant = useCallback(() => setAssistantOpen(false), []);
  const toggleAssistant = useCallback(() => setAssistantOpen((v) => !v), []);
  const openInbox = useCallback(() => setInboxOpen(true), []);
  const closeInbox = useCallback(() => setInboxOpen(false), []);
  const toggleInbox = useCallback(() => setInboxOpen((v) => !v), []);

  // Global ⌘K / Ctrl+K shortcut.
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const mod = e.metaKey || e.ctrlKey;
      if (mod && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPaletteOpen((v) => !v);
      }
      if (e.key === "Escape") {
        setPaletteOpen(false);
        setAssistantOpen(false);
        setInboxOpen(false);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const value = useMemo(
    () => ({
      paletteOpen, openPalette, closePalette,
      assistantOpen, openAssistant, closeAssistant, toggleAssistant,
      inboxOpen, openInbox, closeInbox, toggleInbox,
    }),
    [paletteOpen, assistantOpen, inboxOpen, openPalette, closePalette, openAssistant, closeAssistant, toggleAssistant, openInbox, closeInbox, toggleInbox],
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useShellState() {
  const v = useContext(Ctx);
  if (!v) throw new Error("useShellState must be used inside <ShellStateProvider>");
  return v;
}
