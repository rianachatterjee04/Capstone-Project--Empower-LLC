import { useEffect } from "react";
import { connectRealtime } from "../services/realtime";
import { useEventsStore, type RealtimeEvent } from "../state/eventsStore";

export function useRealtime() {
  const push = useEventsStore((s) => s.push);

  useEffect(() => {
    const unsubscribe = connectRealtime((event: RealtimeEvent) => {
      push(event);
    }) as void | (() => void);

    return () => {
      unsubscribe?.();
    };
  }, [push]);
}
