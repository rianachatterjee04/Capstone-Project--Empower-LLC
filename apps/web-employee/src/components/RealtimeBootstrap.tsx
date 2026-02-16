"use client";

import { useEffect } from "react";

export default function RealtimeBootstrap() {

  useEffect(() => {
    let socket: WebSocket | null = null;

    function connect() {
      socket = new WebSocket("ws://localhost:8000/ws");

      socket.onmessage = (msg) => {
        const event = JSON.parse(msg.data);
        window.dispatchEvent(new CustomEvent("org-event", { detail: event }));
      };

      socket.onclose = () => {
        setTimeout(connect, 2000);
      };
    }

    connect();

    return () => socket?.close();
  }, []);

  return null;
}

