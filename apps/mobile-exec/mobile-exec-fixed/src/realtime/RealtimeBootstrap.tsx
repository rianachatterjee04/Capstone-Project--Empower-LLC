import { useEffect } from "react";
import { connectRealtime } from "../services/realtime";
import { useEventStore } from "../state/eventsStore";

export default function RealtimeBootstrap() {
  const push = useEventStore((s: any) => s.push);

  useEffect(() => {
    connectRealtime((msg: any) => {
      // bus wraps events as { event: "decision", data: {...} }
      // handle both wrapped and unwrapped formats
      const payload = msg?.data ?? msg;
      if (payload?.id) {
        push(payload);
      }
    });
  }, []);

  return null;
}