import { useEffect } from "react";
import { connectRealtime } from "../services/realtime";
import { useEventStore } from "../state/eventsStore";

export function useRealtime() {
  const push = useEventStore((s:any) => s.push);

  useEffect(() => {
    connectRealtime(push);
  }, []);
}

