import { useEffect } from "react";
import { connectRealtime } from "../services/realtime";
import { useEventStore } from "../state/eventsStore";

export default function RealtimeBootstrap() {
  const push = useEventStore((s: any) => s.push);

  useEffect(() => {
    connectRealtime(push);
  }, []);

  return null;
}
