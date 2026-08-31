"use client";

import { useEffect } from "react";
import { apiWsBase } from "@/lib/env";

export default function RealtimeBootstrap() {
  useEffect(() => {
    let socket: WebSocket | null = null;

    function connect() {
      const wsBase = apiWsBase();
      socket = new WebSocket(wsBase + "/ws");

      socket.onmessage = (msg) => {
        const event = JSON.parse(msg.data);
        window.dispatchEvent(new CustomEvent("org-event", { detail: event }));
      };

      socket.onclose = () => {
        setTimeout(connect, 2000);
      };

      socket.onerror = () => socket?.close();
    }

    connect();

    return () => socket?.close();
  }, []);

  return null;
}
