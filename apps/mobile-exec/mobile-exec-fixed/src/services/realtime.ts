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

  // Dev token: dev:<org_id>:<role>:<email>:<user_id>
  const token = "dev:11111111-1111-1111-1111-111111111111:owner:dev@local.test:22222222-2222-2222-2222-222222222222";
  const url = `${wsBase}/ws?token=${encodeURIComponent(token)}`;

  socket = new WebSocket(url);

  socket.onopen = () => console.log("🧠 Foundry realtime connected");

  socket.onmessage = (msg) => {
    try {
      const data = JSON.parse(msg.data);
      // ignore meta messages like connected/subscribed/pong
      if (data.type === "connected" || data.type === "subscribed") return;
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