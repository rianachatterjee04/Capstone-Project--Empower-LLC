"use client";

import { useEffect } from "react";

export default function RealtimeBootstrap() {
  useEffect(() => {
    let socket: WebSocket | null = null;

    function connect() {
      const wsBase = process.env.NEXT_PUBLIC_API_WS ?? "ws://localhost:8000";
      socket = new WebSocket(wsBase + "/ws");

      socket.onmessage = (msg) => {
        const event = JSON.parse(msg.data);
        window.dispatchEvent(new CustomEvent("org-event", { detail: event }));
      };

      socket.onclose = () => setTimeout(connect, 2000);
      socket.onerror = () => socket?.close();
    }

    connect();
    return () => socket?.close();
  }, []);

  return null;
}
