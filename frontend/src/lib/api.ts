const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
console.log(`[API] Base URL: ${API_BASE}`);

async function fetchAPI<T = any>(path: string, options?: RequestInit): Promise<T> {
  const url = `${API_BASE}${path}${path.includes("?") ? "&" : "?"}_t=${Date.now()}`;
  console.log(`[API] Fetching: ${url}`);
  try {
    const res = await fetch(url, {
      headers: { "Content-Type": "application/json", ...options?.headers },
      ...options,
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      console.error(`[API] Error on ${path}:`, err);
      throw new Error(err.detail || res.statusText);
    }
    const data = await res.json();
    console.log(`[API] Success ${path}:`, data);
    return data;
  } catch (e) {
    console.error(`[API] Network/Fetch Error on ${path}:`, e);
    throw e;
  }
}

// ── Status & Control ──────────────────────────────────────
export const getStatus = () => fetchAPI("/api/status");
export const getScores = () => fetchAPI("/api/scores");
export const startPipeline = () => fetchAPI("/api/pipeline/start", { method: "POST" });
export const stopPipeline = () => fetchAPI("/api/pipeline/stop", { method: "POST" });
export const startYouTubeAuth    = () => fetchAPI("/api/auth/youtube/start", { method: "POST" });
export const getYouTubeAuthStatus = () => fetchAPI("/api/auth/youtube/status");
export const processVOD = (url: string, layoutType?: string) => fetchAPI("/api/vod/process", { method: "POST", body: JSON.stringify({ url, layout_type: layoutType }) });
export const processStreamerVOD = (streamerId: number) => fetchAPI(`/api/vod/process_streamer/${streamerId}`, { method: "POST" });
export const getVODProgress = () => fetchAPI("/api/vod/progress");
export const getVODJobProgress = (jobId: string) => fetchAPI(`/api/vod/progress/${jobId}`);
export const cancelVODJob = (jobId: string) => fetchAPI(`/api/vod/cancel/${jobId}`, { method: "POST" });

// Clip media URLs (not fetch — direct browser URLs)
export const getClipVideoUrl = (clipId: string) => `${API_BASE}/api/clips/${clipId}/video`;
export const getClipThumbnailUrl = (clipId: string) => `${API_BASE}/api/clips/${clipId}/thumbnail`;

// ── Streamers ───────────────────────────────────────────
export const getStreamers = () => fetchAPI("/api/streamers");
export const addStreamer = (data: {
  name: string; platform: string; channel: string; url: string;
  enabled?: boolean; auto_approve?: boolean;
}) => fetchAPI("/api/streamers", { method: "POST", body: JSON.stringify(data) });
export const updateStreamer = (id: number, data: Record<string, any>) =>
  fetchAPI(`/api/streamers/${id}`, { method: "PUT", body: JSON.stringify(data) });
export const deleteStreamer = (id: number) =>
  fetchAPI(`/api/streamers/${id}`, { method: "DELETE" });

// ── Clips ───────────────────────────────────────────────
export const getClips = (status?: string) =>
  fetchAPI(`/api/clips${status ? `?status=${status}` : ""}`);
export const approveClip = (clipId: string) =>
  fetchAPI(`/api/clips/${clipId}/approve`, { method: "POST" });
export const rejectClip = (clipId: string) =>
  fetchAPI(`/api/clips/${clipId}/reject`, { method: "POST" });

// ── Uploads ─────────────────────────────────────────────
export const getUploads = () => fetchAPI("/api/uploads");

// ── Jobs ────────────────────────────────────────────────
export const getJobs = (status?: string) =>
  fetchAPI(`/api/jobs${status ? `?status=${status}` : ""}`);

// ── Settings ──────────────────────────────────────────
export const getSettings = () => fetchAPI("/api/settings");
export const updateSettings = (data: any) => fetchAPI("/api/settings", { method: "POST", body: JSON.stringify(data) });
