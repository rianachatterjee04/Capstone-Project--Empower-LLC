let socket: WebSocket | null = null;

export function connectRealtime(onEvent: (event: any) => void) {
  socket = new WebSocket("ws://localhost:8000/ws");

  socket.onmessage = (msg) => {
    const data = JSON.parse(msg.data);
    onEvent(data);
  };

  socket.onclose = () => {
    setTimeout(() => connectRealtime(onEvent), 2000);
  };
}

