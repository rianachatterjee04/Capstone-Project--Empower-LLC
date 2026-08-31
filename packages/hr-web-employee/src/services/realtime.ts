import { apiWsBase } from "@/lib/env";

let socket: WebSocket | null = null;
let reconnectTimer: any = null;
let listeners: ((event: any) => void)[] = [];

function notify(event: any) {
  listeners.forEach(l => l(event));
}

export function connectRealtime(onEvent: (event: any) => void) {
  // prevent duplicate listeners
  if (!listeners.includes(onEvent)) {
    listeners.push(onEvent);
  }

  // already connected
  if (socket && socket.readyState === WebSocket.OPEN) return;

  const url = apiWsBase() + "/ws";

  socket = new WebSocket(url);

  socket.onopen = () => {
    console.log("🧠 Foundry realtime connected");
  };

  socket.onmessage = (msg) => {
    try {
      const data = JSON.parse(msg.data);
      notify(data);
    } catch (e) {
      console.error("Invalid realtime payload", e);
    }
  };

  socket.onclose = () => {
    console.log("⚠️ realtime disconnected — retrying");

    if (reconnectTimer) return;
    reconnectTimer = setTimeout(() => {
      reconnectTimer = null;
      connectRealtime(onEvent);
    }, 2000);
  };

  socket.onerror = () => socket?.close();
}

