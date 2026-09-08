export const getApiBase = () => {
  if (typeof window !== "undefined") {
    return `http://${window.location.hostname}:8000`;
  }
  return process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
};

async function fetchAPI<T = any>(path: string, options?: RequestInit): Promise<T> {
  const base = getApiBase();
  const url = `${base}${path}${path.includes("?") ? "&" : "?"}_t=${Date.now()}`;
  try {
    const res = await fetch(url, {
      headers: { "Content-Type": "application/json", ...options?.headers },
      ...options,
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || res.statusText);
    }
    return await res.json();
  } catch (e) {
    console.warn(`[API] Error on ${path}:`, e);
    throw e;
  }
}

// ── Status & Control ──────────────────────────────────────
export const getStatus = () => fetchAPI("/api/status");
export const getScores = () => fetchAPI("/api/scores");
export const startPipeline = () => fetchAPI("/api/pipeline/start", { method: "POST" });
export const stopPipeline = () => fetchAPI("/api/pipeline/stop", { method: "POST" });
export const startYouTubeAuth = (accountId: string = "account1") =>
  fetchAPI("/api/auth/youtube/start", { method: "POST", body: JSON.stringify({ account_id: accountId }) });
export const getYouTubeAuthStatus = (accountId: string = "account1") =>
  fetchAPI(`/api/auth/youtube/status?account_id=${encodeURIComponent(accountId)}`);
export const getYouTubeAccounts = () => fetchAPI("/api/auth/youtube/accounts");
export const logoutYouTube = (accountId: string = "account1") =>
  fetchAPI("/api/auth/youtube/logout", { method: "POST", body: JSON.stringify({ account_id: accountId }) });
export const addYouTubeAccount = (data: { client_id: string; client_secret: string; name?: string }) =>
  fetchAPI("/api/auth/youtube/add", { method: "POST", body: JSON.stringify(data) });
export const processVOD = (url: string, layoutType?: string, subtitleStyle?: string) =>
  fetchAPI("/api/vod/process", {
    method: "POST",
    body: JSON.stringify({ url, layout_type: layoutType, subtitle_style: subtitleStyle }),
  });
export const processStreamerVOD = (streamerId: number) =>
  fetchAPI(`/api/vod/process_streamer/${streamerId}`, { method: "POST" });
export const getVODProgress = () => fetchAPI("/api/vod/progress");
export const getVODJobProgress = (jobId: string) => fetchAPI(`/api/vod/progress/${jobId}`);
export const cancelVODJob = (jobId: string) => fetchAPI(`/api/vod/cancel/${jobId}`, { method: "POST" });

// Clip media URLs
export const getClipVideoUrl = (clipId: string) => `${getApiBase()}/api/clips/${clipId}/video`;
export const getClipThumbnailUrl = (clipId: string) => `${getApiBase()}/api/clips/${clipId}/thumbnail`;

// ── Streamers ───────────────────────────────────────────
export const getStreamers = () => fetchAPI("/api/streamers");
export const addStreamer = (data: {
  name: string;
  platform: string;
  channel: string;
  url: string;
  enabled?: boolean;
  auto_approve?: boolean;
  framing_mode?: string;
  subtitle_style?: string;
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
export const unqueueClip = (clipId: string) =>
  fetchAPI(`/api/clips/${clipId}/unqueue`, { method: "POST" });
export const queueClipsBatch = (clipIds: string[]) =>
  fetchAPI("/api/clips/queue_batch", { method: "POST", body: JSON.stringify({ clip_ids: clipIds }) });
export const unqueueClipsBatch = (clipIds: string[]) =>
  fetchAPI("/api/clips/unqueue_batch", { method: "POST", body: JSON.stringify({ clip_ids: clipIds }) });
export const clearUploadQueue = () =>
  fetchAPI("/api/clips/clear_upload_queue", { method: "POST" });
export const uploadAllNow = () =>
  fetchAPI("/api/clips/upload_all_now", { method: "POST" });
export const getUploadQueue = () =>
  fetchAPI("/api/clips/upload_queue");
export const rejectClip = (clipId: string) =>
  fetchAPI(`/api/clips/${clipId}/reject`, { method: "POST" });
export const deleteClip = (clipId: string) =>
  fetchAPI(`/api/clips/${clipId}`, { method: "DELETE" });

// ── Uploads ─────────────────────────────────────────────
export const getUploads = () => fetchAPI("/api/uploads");

// ── Jobs ────────────────────────────────────────────────
export const getJobs = (status?: string, limit: number = 50) =>
  fetchAPI(`/api/jobs${status ? `?status=${status}&limit=${limit}` : `?limit=${limit}`}`);
export const getJobsStats = () => fetchAPI("/api/jobs/stats");
export const cancelJob = (jobId: number) =>
  fetchAPI(`/api/jobs/${jobId}/cancel`, { method: "POST" });
export const retryJob = (jobId: number) =>
  fetchAPI(`/api/jobs/${jobId}/retry`, { method: "POST" });
export const deleteJob = (jobId: number) =>
  fetchAPI(`/api/jobs/${jobId}`, { method: "DELETE" });

// ── Dream Team Multi-Agent ──────────────────────────────
export const getDreamTeamStatus = () => fetchAPI("/api/dreamteam/status");
export const runDreamTeamEnhance = (clipId: string) =>
  fetchAPI(`/api/dreamteam/enhance/${clipId}`, { method: "POST" });

// ── Settings ──────────────────────────────────────────
export const getSettings = () => fetchAPI("/api/settings");
export const updateSettings = (data: any) =>
  fetchAPI("/api/settings", { method: "POST", body: JSON.stringify(data) });
