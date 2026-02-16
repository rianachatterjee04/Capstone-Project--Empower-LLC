import { create } from "zustand";

export const useEventStore = create((set) => ({
  events: [],

  push: (event) =>
    set((s) => ({
      events: [event, ...s.events],
    })),

  remove: (id) =>
    set((s) => ({
      events: s.events.filter(e => e.id !== id),
    }))
}));

