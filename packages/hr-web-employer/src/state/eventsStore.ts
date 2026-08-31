import { create } from "zustand";

export type RealtimeEvent = {
  id?: string;
  type?: string;
  title?: string;
  message?: string;
  created_at?: string;
  payload?: Record<string, unknown>;
  [key: string]: unknown;
};

type EventsState = {
  events: RealtimeEvent[];
  push: (event: RealtimeEvent) => void;
  clear: () => void;
};

export const useEventsStore = create<EventsState>((set) => ({
  events: [],

  push: (event: RealtimeEvent) =>
    set((s) => ({
      events: [event, ...s.events],
    })),

  clear: () => set({ events: [] }),
}));
