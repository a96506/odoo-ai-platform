"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { getWsUrl } from "../lib/api";

const RECONNECT_DELAYS = [1000, 2000, 4000, 8000, 16000, 30000];

export default function useWebSocket(role = null) {
  const [lastMessage, setLastMessage] = useState(null);
  const [isConnected, setIsConnected] = useState(false);
  const wsRef = useRef(null);
  const retriesRef = useRef(0);
  const timerRef = useRef(null);

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    const base = getWsUrl();
    const url = role ? `${base}/ws/dashboard?role=${role}` : `${base}/ws/dashboard`;

    try {
      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onopen = () => {
        setIsConnected(true);
        retriesRef.current = 0;
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data.type !== "pong") {
            setLastMessage(data);
          }
        } catch {
          // ignore non-JSON
        }
      };

      ws.onclose = () => {
        setIsConnected(false);
        wsRef.current = null;
        const delay = RECONNECT_DELAYS[Math.min(retriesRef.current, RECONNECT_DELAYS.length - 1)];
        retriesRef.current += 1;
        timerRef.current = setTimeout(connect, delay);
      };

      ws.onerror = () => {
        ws.close();
      };
    } catch {
      setIsConnected(false);
    }
  }, [role]);

  useEffect(() => {
    connect();
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
      if (wsRef.current) {
        wsRef.current.onclose = null;
        wsRef.current.close();
      }
    };
  }, [connect]);

  return { lastMessage, isConnected };
}
