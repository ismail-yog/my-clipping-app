const WS_URL = process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8000/ws/events";

export type StatusUpdate = {
  type: string;
  timestamp: number;
  active: number;
  total_clips: number;
  pending_review: number;
  uploads_today: number;
  queue_pending: number;
  vod_progress?: Record<string, { url: string; progress: number; status: string }>;
};

export function connectWebSocket(onMessage: (data: StatusUpdate) => void): WebSocket | null {
  if (typeof window === "undefined") return null;

  const ws = new WebSocket(WS_URL);

  ws.onmessage = (event) => {
    try {
      const data: StatusUpdate = JSON.parse(event.data);
      onMessage(data);
    } catch {}
  };

  ws.onclose = () => {
    // Auto-reconnect after 3 seconds
    setTimeout(() => connectWebSocket(onMessage), 3000);
  };

  ws.onerror = () => ws.close();

  return ws;
}
