import Constants from "expo-constants";

let socket: WebSocket | null = null;
let reconnectTimer: any = null;
let listeners: ((event: any) => void)[] = [];

function notify(event: any) {
  listeners.forEach(l => l(event));
}

export function connectRealtime(onEvent: (event: any) => void) {
  if (!listeners.includes(onEvent)) {
    listeners.push(onEvent);
  }

  if (socket && socket.readyState === WebSocket.OPEN) return;

  const apiBase: string = (Constants.expoConfig?.extra as any)?.apiBaseUrl ?? "http://localhost:8000/api";
  const wsBase = apiBase.replace(/^http/, "ws").replace(/\/api$/, "");
  const url = wsBase + "/ws";

  socket = new WebSocket(url);

  socket.onopen = () => console.log("🧠 Foundry realtime connected");

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
