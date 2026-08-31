import { create } from "zustand";

type EventItem = { id: string; [key: string]: any };

type EventStore = {
  events: EventItem[];
  push: (event: EventItem) => void;
  remove: (id: string) => void;
};

export const useEventStore = create<EventStore>((set) => ({
  events: [],

  push: (event) =>
    set((s) => ({
      events: [event, ...s.events],
    })),

  remove: (id) =>
    set((s) => ({
      events: s.events.filter((e) => e.id !== id),
    })),
}));
