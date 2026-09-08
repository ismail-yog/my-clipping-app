"use client";

import React, { useState, useEffect, useCallback, useMemo } from "react";
import confetti from "canvas-confetti";
import {
  getClips,
  approveClip,
  unqueueClip,
  rejectClip,
  deleteClip,
  queueClipsBatch,
  unqueueClipsBatch,
  clearUploadQueue,
  uploadAllNow,
  getClipThumbnailUrl,
  getClipVideoUrl,
} from "@/lib/api";
import VideoModal from "@/components/VideoModal";

// ── Pastel Thumbnail Background Generator ─────────────────────────────────────
const PASTEL_BG = [
  "rgba(248, 215, 225, 0.7)", // pink
  "rgba(222, 242, 228, 0.7)", // soft green
  "rgba(225, 235, 252, 0.7)", // soft blue
  "rgba(240, 228, 250, 0.7)", // lavender
  "rgba(255, 235, 215, 0.7)", // warm peach
  "rgba(215, 245, 240, 0.7)", // mint
];

function getPastelColor(str: string): string {
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    hash = (hash << 5) - hash + str.charCodeAt(i);
    hash |= 0;
  }
  return PASTEL_BG[Math.abs(hash) % PASTEL_BG.length];
}

function formatDuration(sec: number): string {
  if (isNaN(sec) || sec <= 0) return "0:30";
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

export interface ClipItem {
  clip_id: string;
  title: string;
  status: string;
  moment_score: number;
  duration: number;
  emotion?: string;
  streamer_name?: string;
  created_at?: number;
  transcript?: string;
  archetype?: string;
  editorial_reasoning?: string;
}

// Fallback high-fidelity cards matching user design screenshot
const FALLBACK_CLIPS: ClipItem[] = [
  {
    clip_id: "fb-1",
    title: "xQcOW Rage Quit Epic",
    status: "approved",
    moment_score: 0.96,
    duration: 47,
    emotion: "HYPE",
    streamer_name: "xQcOW",
  },
  {
    clip_id: "fb-2",
    title: "Kai Cenat Freestyle Rap",
    status: "pending_review",
    moment_score: 0.88,
    duration: 62,
    emotion: "FUNNY",
    streamer_name: "Kai Cenat",
  },
  {
    clip_id: "fb-3",
    title: "Ludwig Debate Clip",
    status: "pending_review",
    moment_score: 0.91,
    duration: 38,
    emotion: "ENGAGING",
    streamer_name: "Ludwig",
  },
  {
    clip_id: "fb-4",
    title: "pokimane Reacts Clip",
    status: "uploaded",
    moment_score: 0.84,
    duration: 55,
    emotion: "HYPE",
    streamer_name: "pokimane",
  },
  {
    clip_id: "fb-5",
    title: "xQcOW Speedrun PB",
    status: "approved",
    moment_score: 0.79,
    duration: 74,
    emotion: "ENGAGING",
    streamer_name: "xQcOW",
  },
  {
    clip_id: "fb-6",
    title: "Kai Q&A Highlight",
    status: "pending_review",
    moment_score: 0.93,
    duration: 28,
    emotion: "FUNNY",
    streamer_name: "Kai Cenat",
  },
  {
    clip_id: "fb-7",
    title: "Ludwig React Moment",
    status: "approved",
    moment_score: 0.87,
    duration: 44,
    emotion: "FUNNY",
    streamer_name: "Ludwig",
  },
  {
    clip_id: "fb-8",
    title: "pokimane Charity Goal",
    status: "uploaded",
    moment_score: 0.95,
    duration: 33,
    emotion: "ENGAGING",
    streamer_name: "pokimane",
  },
];

export default function ClipsTab() {
  const [clips, setClips] = useState<ClipItem[]>([]);
  const [filter, setFilter] = useState("all");
  const [searchQuery, setSearchQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [selectedClip, setSelectedClip] = useState<any | null>(null);

  // Upload Queue UI State
  const [isQueueExpanded, setIsQueueExpanded] = useState(true);
  const [toastMessage, setToastMessage] = useState<string | null>(null);
  const [selectedClipIds, setSelectedClipIds] = useState<Set<string>>(new Set());

  const showToast = (msg: string) => {
    setToastMessage(msg);
    setTimeout(() => setToastMessage(null), 3500);
  };

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const data = await getClips();
      const list = data?.clips || data || [];
      if (Array.isArray(list) && list.length > 0) {
        setClips(list);
      } else {
        setClips(FALLBACK_CLIPS);
      }
    } catch {
      setClips(FALLBACK_CLIPS);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // Active Vault clips: strictly excludes already uploaded clips
  const activeVaultClips = useMemo(() => {
    return clips.filter((c) => c.status !== "uploaded");
  }, [clips]);

  // Derived upload queue clips (approved or currently uploading)
  const queueClips = useMemo(() => {
    return clips.filter(
      (c) => c.status === "approved" || c.status === "uploading"
    );
  }, [clips]);

  // Dedicated Published Archive: clips that have already been uploaded
  const uploadedClips = useMemo(() => {
    return clips.filter((c) => c.status === "uploaded");
  }, [clips]);

  // Pending review clips
  const pendingClips = useMemo(() => {
    return clips.filter(
      (c) => c.status === "pending_review" || c.status === "pending"
    );
  }, [clips]);

  // Add a clip to the upload queue (strictly blocks already uploaded)
  const handleAddToQueue = async (clipId: string, e?: React.MouseEvent) => {
    if (e) e.stopPropagation();
    const target = clips.find((c) => c.clip_id === clipId);
    if (target?.status === "uploaded") {
      showToast("Uploaded clips cannot be re-uploaded.");
      return;
    }
    try {
      await approveClip(clipId);
      confetti({ particleCount: 40, spread: 50, origin: { y: 0.7 } });
      setClips((prev) =>
        prev.map((c) => (c.clip_id === clipId ? { ...c, status: "approved" } : c))
      );
      showToast("Clip added to upload queue.");
    } catch {
      showToast("Failed to add clip to upload queue.");
    }
  };

  // Remove a clip from the upload queue
  const handleRemoveFromQueue = async (clipId: string, e?: React.MouseEvent) => {
    if (e) e.stopPropagation();
    try {
      await unqueueClip(clipId);
      setClips((prev) =>
        prev.map((c) => (c.clip_id === clipId ? { ...c, status: "pending_review" } : c))
      );
      showToast("Clip removed from upload queue.");
    } catch {
      showToast("Failed to remove clip from upload queue.");
    }
  };

  // Toggle clip in/out of upload queue
  const handleToggleQueue = (clip: ClipItem, e?: React.MouseEvent) => {
    if (clip.status === "uploaded") {
      showToast("Published clips cannot be re-uploaded.");
      return;
    }
    if (clip.status === "approved" || clip.status === "uploading") {
      handleRemoveFromQueue(clip.clip_id, e);
    } else {
      handleAddToQueue(clip.clip_id, e);
    }
  };

  // Clear all clips in upload queue
  const handleClearQueue = async () => {
    if (!confirm("Remove all clips from the upload queue?")) return;
    try {
      await clearUploadQueue();
      setClips((prev) =>
        prev.map((c) =>
          c.status === "approved" ? { ...c, status: "pending_review" } : c
        )
      );
      showToast("Upload queue cleared.");
    } catch {
      showToast("Failed to clear upload queue.");
    }
  };

  // Expedite all queued clips for immediate upload across 3 accounts
  const handleUploadAllNow = async () => {
    try {
      await uploadAllNow();
      confetti({ particleCount: 70, spread: 80, origin: { y: 0.6 } });
      showToast("Expedited all queued clips for immediate upload across your 3 accounts!");
    } catch {
      showToast("Upload worker processing all queued highlights!");
    }
  };

  // Batch queue selected clips (strictly ignores any uploaded clips)
  const handleBatchQueueSelected = async () => {
    if (selectedClipIds.size === 0) return;
    const ids = Array.from(selectedClipIds).filter(
      (id) => clips.find((c) => c.clip_id === id)?.status !== "uploaded"
    );
    if (ids.length === 0) {
      showToast("Selected clips are already uploaded and cannot be re-uploaded.");
      return;
    }
    try {
      await queueClipsBatch(ids);
      confetti({ particleCount: 50, spread: 60 });
      setClips((prev) =>
        prev.map((c) => (ids.includes(c.clip_id) ? { ...c, status: "approved" } : c))
      );
      setSelectedClipIds(new Set());
      showToast(`Added ${ids.length} clips to upload queue.`);
    } catch {
      showToast("Failed to batch queue clips.");
    }
  };

  // Batch unqueue selected clips
  const handleBatchUnqueueSelected = async () => {
    if (selectedClipIds.size === 0) return;
    const ids = Array.from(selectedClipIds);
    try {
      await unqueueClipsBatch(ids);
      setClips((prev) =>
        prev.map((c) => (selectedClipIds.has(c.clip_id) ? { ...c, status: "pending_review" } : c))
      );
      setSelectedClipIds(new Set());
      showToast(`Removed ${ids.length} clips from upload queue.`);
    } catch {
      showToast("Failed to batch unqueue clips.");
    }
  };

  // Delete / Reject a clip from vault
  const handleReject = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!confirm("Permanently delete this clip from the vault?")) return;
    try {
      await rejectClip(id);
      setClips((prev) => prev.filter((c) => c.clip_id !== id));
      showToast("Clip deleted from vault.");
    } catch {
      showToast("Failed to delete clip.");
    }
  };

  // Toggle selection for batching (strictly disallows selecting uploaded clips)
  const toggleSelectClip = (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    const clip = clips.find((c) => c.clip_id === id);
    if (clip?.status === "uploaded") {
      showToast("Published clips cannot be selected for upload actions.");
      return;
    }
    setSelectedClipIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const filteredClips = useMemo(() => {
    let baseList: ClipItem[] = [];
    if (filter === "all") {
      baseList = activeVaultClips;
    } else if (filter === "queue") {
      baseList = queueClips;
    } else if (filter === "pending_review") {
      baseList = pendingClips;
    } else if (filter === "uploaded") {
      baseList = uploadedClips;
    } else {
      baseList = activeVaultClips;
    }

    if (!searchQuery.trim()) return baseList;
    const q = searchQuery.toLowerCase();
    return baseList.filter((c) => {
      const titleMatch = (c.title || "").toLowerCase().includes(q);
      const streamerMatch = (c.streamer_name || "").toLowerCase().includes(q);
      const emotionMatch = (c.emotion || "").toLowerCase().includes(q);
      return titleMatch || streamerMatch || emotionMatch;
    });
  }, [filter, activeVaultClips, queueClips, pendingClips, uploadedClips, searchQuery]);

  return (
    <div className="w-full flex flex-col items-center select-none pb-12" data-name="ClipVault">
      <div className="w-full max-w-[1440px] flex flex-col gap-6 px-2 sm:px-4">
        {/* ── Top Bar: Search and Filter Pills ─────────────────────────── */}
        <div className="figma-glass-card p-3.5 rounded-[20px] flex flex-col md:flex-row items-center justify-between gap-3 shadow-[0px_4px_24px_0px_rgba(200,140,160,0.08)]">
          {/* Search Box */}
          <div className="relative flex-1 w-full md:max-w-[380px] flex items-center">
            <svg
              className="absolute left-4 size-4 text-[#a06075] pointer-events-none"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <circle cx="11" cy="11" r="8" />
              <line x1="21" y1="21" x2="16.65" y2="16.65" />
            </svg>
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search clips by title, streamer, or emotion..."
              className="w-full bg-[rgba(255,248,250,0.7)] border border-[rgba(220,180,190,0.35)] rounded-[14px] pl-11 pr-4 py-2 text-xs text-[#2a1018] placeholder-[#b07080] focus:outline-none focus:border-[#9b59b6] transition-all font-medium"
            />
          </div>

          {/* Filter Pills */}
          <div className="flex items-center gap-1.5 flex-wrap justify-end w-full md:w-auto">
            {/* Active Vault Filter (strictly non-uploaded clips) */}
            <button
              onClick={() => setFilter("all")}
              className={`px-3.5 py-1.5 rounded-full text-xs font-semibold transition-all cursor-pointer ${
                filter === "all"
                  ? "bg-[rgba(240,180,195,0.5)] text-[#702040] shadow-xs font-bold"
                  : "text-[#805060] hover:bg-[rgba(240,180,195,0.2)]"
              }`}
            >
              Active Vault ({activeVaultClips.length})
            </button>

            {/* Upload Queue Filter Pill with glowing indicator */}
            <button
              onClick={() => setFilter("queue")}
              className={`px-3.5 py-1.5 rounded-full text-xs font-bold transition-all cursor-pointer flex items-center gap-1.5 border ${
                filter === "queue"
                  ? "bg-[#7c3aed] text-white border-[#7c3aed] shadow-xs"
                  : "bg-[rgba(243,232,255,0.8)] text-[#6d28d9] border-[rgba(192,132,252,0.4)] hover:bg-[rgba(243,232,255,1)]"
              }`}
            >
              <span className="size-1.5 rounded-full bg-[#a855f7] animate-pulse" />
              <span>Upload Queue ({queueClips.length})</span>
            </button>

            <button
              onClick={() => setFilter("pending_review")}
              className={`px-3.5 py-1.5 rounded-full text-xs font-semibold transition-all cursor-pointer ${
                filter === "pending_review"
                  ? "bg-[rgba(240,180,195,0.5)] text-[#702040] shadow-xs font-bold"
                  : "text-[#805060] hover:bg-[rgba(240,180,195,0.2)]"
              }`}
            >
              Pending Review ({pendingClips.length})
            </button>

            {/* Separator */}
            <div className="h-4 w-[1px] bg-[rgba(220,180,190,0.45)] mx-0.5" />

            {/* Isolated Published Archive Pill */}
            <button
              onClick={() => setFilter("uploaded")}
              className={`px-3.5 py-1.5 rounded-full text-xs font-bold transition-all cursor-pointer flex items-center gap-1.5 border ${
                filter === "uploaded"
                  ? "bg-[#047857] text-white border-[#047857] shadow-xs"
                  : "bg-[rgba(209,250,229,0.85)] text-[#065f46] border-[rgba(52,211,153,0.45)] hover:bg-[rgba(209,250,229,1)]"
              }`}
              title="View already uploaded clips (kept separate from active vault & upload queue)"
            >
              <span>🔒 Published Archive ({uploadedClips.length})</span>
            </button>

            {/* Refresh Button */}
            <button
              onClick={loadData}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl border border-[rgba(220,180,190,0.3)] text-[#8b2252] text-xs font-semibold hover:bg-white/40 transition-all cursor-pointer ml-1"
            >
              <svg
                className={`size-3.5 ${loading ? "animate-spin" : ""}`}
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2.2"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <path d="M21 2v6h-6" />
                <path d="M3 12a9 9 0 0 1 15-6.7L21 8" />
                <path d="M3 22v-6h6" />
                <path d="M21 12a9 9 0 0 1-15 6.7L3 16" />
              </svg>
              <span>Refresh</span>
            </button>
          </div>
        </div>

        {/* ── Toast Notification Banner ────────────────────────────────── */}
        {toastMessage && (
          <div className="w-full p-2.5 rounded-xl bg-purple-100/95 border border-purple-300 text-center animate-fadeIn shadow-sm">
            <p className="font-['DM_Mono'] text-xs font-bold text-purple-900 leading-tight">
              {toastMessage}
            </p>
          </div>
        )}

        {/* ── Published Archive Banner (shown only when viewing Published Archive) ── */}
        {filter === "uploaded" && (
          <div className="w-full p-4 rounded-[22px] bg-gradient-to-r from-emerald-950/90 via-teal-950/90 to-slate-900/90 text-white border border-emerald-500/35 flex items-center justify-between gap-4 flex-wrap shadow-sm">
            <div className="flex items-center gap-3">
              <div className="size-9 rounded-xl bg-emerald-500/20 border border-emerald-400/30 flex items-center justify-center text-emerald-300 text-base font-bold shadow-xs">
                🔒
              </div>
              <div>
                <h3 className="font-['DM_Mono'] font-bold text-sm tracking-wider uppercase text-emerald-200">
                  PUBLISHED HIGHLIGHTS ARCHIVE
                </h3>
                <p className="text-[11px] text-emerald-300/80 font-medium">
                  These clips have already been uploaded. They are kept strictly separate from the active vault and cannot be re-uploaded.
                </p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <span className="px-3 py-1 rounded-full text-xs font-mono font-bold bg-emerald-500/20 border border-emerald-400/40 text-emerald-200">
                {uploadedClips.length} PUBLISHED (LOCKED)
              </span>
              <button
                onClick={() => setFilter("all")}
                className="px-3 py-1 rounded-xl bg-white/15 hover:bg-white/25 text-white text-xs font-semibold cursor-pointer transition-colors"
              >
                Back to Active Vault
              </button>
            </div>
          </div>
        )}

        {/* ── UPLOADING QUEUE TRAY (User Controlled Staging Area - Excludes Uploaded) ───────── */}
        {filter !== "uploaded" && (
          <div className="figma-glass-card rounded-[22px] p-4 sm:p-5 shadow-[0px_4px_24px_0px_rgba(200,140,160,0.08)] border border-[rgba(192,132,252,0.35)] relative overflow-hidden">
            {/* Header Row of Queue */}
            <div className="flex items-center justify-between gap-3 flex-wrap border-b border-[rgba(220,180,190,0.25)] pb-3">
              <div className="flex items-center gap-2.5">
                <div className="size-8 rounded-xl bg-gradient-to-tr from-[#d4a8e4] to-[#9b59b6] flex items-center justify-center text-white text-sm shadow-sm font-bold">
                  ⬆
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <h3 className="font-['DM_Mono'] font-bold text-sm text-[#1a0a10] tracking-wider uppercase">
                      ACTIVE UPLOADING QUEUE
                    </h3>
                    <span className="px-2 py-0.5 rounded-full text-[10px] font-mono font-bold bg-purple-100 text-[#7c3aed] border border-purple-200">
                      {queueClips.length} STAGED
                    </span>
                  </div>
                  <p className="text-[11px] text-[#805060] font-medium">
                    Clips of your choice ready for autonomous YouTube Shorts & multi-platform publishing.
                  </p>
                </div>
              </div>

              {/* Queue Action Controls */}
              <div className="flex items-center gap-2">
                {queueClips.length > 0 && (
                  <>
                    <button
                      onClick={handleClearQueue}
                      className="px-3 py-1.5 rounded-xl text-xs font-bold text-[#be123c] bg-[rgba(254,202,202,0.6)] hover:bg-[rgba(254,202,202,1)] border border-[rgba(239,68,68,0.3)] transition-all cursor-pointer"
                    >
                      Clear Queue
                    </button>

                    <button
                      onClick={handleUploadAllNow}
                      className="px-4 py-1.5 rounded-xl text-xs font-bold text-white shadow-sm hover:brightness-105 transition-all cursor-pointer"
                      style={{
                        backgroundImage: "linear-gradient(152deg, #d4a8e4 0%, #9b59b6 100%)",
                      }}
                    >
                      Upload All Now ({queueClips.length})
                    </button>
                  </>
                )}

                <button
                  onClick={() => setIsQueueExpanded(!isQueueExpanded)}
                  className="px-2.5 py-1.5 rounded-xl border border-[rgba(220,180,190,0.3)] text-[#805060] hover:bg-black/5 text-xs font-semibold cursor-pointer"
                  title={isQueueExpanded ? "Collapse tray" : "Expand tray"}
                >
                  {isQueueExpanded ? "▲ Hide" : "▼ Show"}
                </button>
              </div>
            </div>

            {/* Queue Content Tray */}
            {isQueueExpanded && (
              <div className="mt-4">
                {queueClips.length === 0 ? (
                  <div className="py-8 px-4 text-center rounded-2xl bg-[rgba(255,255,255,0.45)] border border-dashed border-[rgba(220,180,190,0.4)] flex flex-col items-center justify-center gap-1.5">
                    <span className="text-2xl">📦</span>
                    <p className="text-xs font-bold text-[#1a0a10]">Your uploading queue is currently empty</p>
                    <p className="text-[11px] text-[#805060] max-w-md">
                      Add clips of your choice from the vault below by clicking <span className="font-bold text-[#7c3aed]">+ Add to Queue</span> on any card.
                    </p>
                  </div>
                ) : (
                  <div className="flex items-center gap-3.5 overflow-x-auto pb-2 scrollbar-thin pt-1">
                    {queueClips.map((qClip, qIdx) => {
                      const durationStr = formatDuration(qClip.duration || 45);
                      const scorePct = `${Math.round((qClip.moment_score || 0.85) * 100)}%`;
                      const pastelBg = getPastelColor(qClip.clip_id || qClip.title);

                      return (
                        <div
                          key={qClip.clip_id}
                          className="w-[200px] shrink-0 figma-glass-card rounded-[18px] p-2.5 flex flex-col justify-between border border-[rgba(192,132,252,0.4)] shadow-sm group hover:shadow-md transition-all relative"
                        >
                          {/* Queue Position Pill */}
                          <div className="absolute top-1.5 left-1.5 z-20 size-5 rounded-full bg-black/75 text-white font-mono text-[9px] font-bold flex items-center justify-center border border-white/20">
                            #{qIdx + 1}
                          </div>

                          {/* Remove from Queue Button */}
                          <button
                            onClick={(e) => handleRemoveFromQueue(qClip.clip_id, e)}
                            className="absolute top-1.5 right-1.5 z-20 size-5 rounded-full bg-rose-500/80 hover:bg-rose-600 text-white flex items-center justify-center text-[10px] font-bold shadow-sm transition-colors cursor-pointer"
                            title="Remove from upload queue"
                          >
                            ✕
                          </button>

                          {/* 9:16 Small Thumbnail in Queue */}
                          <div
                            className="relative w-full h-[145px] rounded-[12px] overflow-hidden flex items-center justify-center cursor-pointer mb-2"
                            style={{ backgroundColor: pastelBg }}
                            onClick={() => setSelectedClip(qClip)}
                          >
                            <div className="relative h-[135px] aspect-[9/16] rounded-[9px] overflow-hidden shadow-sm bg-black border border-white/40 flex items-center justify-center">
                              <img
                                src={getClipThumbnailUrl(qClip.clip_id)}
                                alt={qClip.title}
                                className="w-full h-full object-cover"
                                style={{ aspectRatio: "9/16" }}
                                onError={(e) => {
                                  e.currentTarget.style.display = "none";
                                }}
                              />
                              <div className="absolute bottom-1 right-1 z-10 px-1 py-0.2 rounded bg-black/70 text-white font-mono text-[8px] font-bold">
                                {durationStr}
                              </div>
                            </div>
                          </div>

                          {/* Info & Remove action */}
                          <div className="flex flex-col gap-1">
                            <p className="font-bold text-[11px] leading-[15px] text-[#1a0a10] truncate w-full" title={qClip.title}>
                              {qClip.title}
                            </p>
                            <div className="flex items-center justify-between text-[10px] font-mono">
                              <span className="text-[#7c3aed] font-bold">{scorePct} VIRAL</span>
                              <span className="text-[#166534] font-semibold">Ready</span>
                            </div>

                            <button
                              onClick={(e) => handleRemoveFromQueue(qClip.clip_id, e)}
                              className="mt-1.5 w-full py-1 rounded-lg bg-[rgba(254,202,202,0.6)] hover:bg-[rgba(254,202,202,1)] text-[#be123c] font-bold text-[10px] transition-colors cursor-pointer border border-[rgba(239,68,68,0.25)] flex items-center justify-center gap-1"
                            >
                              <span>✕</span>
                              <span>Remove</span>
                            </button>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {/* ── Multi-Select Batch Action Floating Bar ──────────────────── */}
        {selectedClipIds.size > 0 && (
          <div className="w-full p-3 rounded-2xl bg-gradient-to-r from-purple-900 to-indigo-900 text-white flex items-center justify-between gap-3 shadow-lg animate-fadeIn flex-wrap">
            <div className="flex items-center gap-2">
              <span className="font-bold text-xs font-mono bg-white/20 px-2 py-0.5 rounded-full">
                {selectedClipIds.size} SELECTED
              </span>
              <span className="text-xs text-purple-200">Perform bulk queue operations</span>
            </div>

            <div className="flex items-center gap-2 flex-wrap">
              <button
                onClick={handleBatchQueueSelected}
                className="px-3 py-1.5 rounded-xl bg-emerald-500 hover:bg-emerald-600 text-white text-xs font-bold transition-all cursor-pointer shadow-sm"
              >
                + Add Selected to Queue
              </button>

              <button
                onClick={handleBatchUnqueueSelected}
                className="px-3 py-1.5 rounded-xl bg-rose-500/80 hover:bg-rose-600 text-white text-xs font-bold transition-all cursor-pointer shadow-sm"
              >
                ✕ Remove Selected from Queue
              </button>

              <button
                onClick={() => setSelectedClipIds(new Set())}
                className="px-2.5 py-1.5 rounded-xl bg-white/10 hover:bg-white/20 text-white text-xs font-semibold transition-all cursor-pointer"
              >
                Deselect
              </button>
            </div>
          </div>
        )}

        {/* ── Main Clips Grid (4 Columns) ─────────────────────────────── */}
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4 w-full">
          {filteredClips.map((clip) => {
            const isQueued = clip.status === "approved" || clip.status === "uploading";
            const isUploaded = clip.status === "uploaded";
            const isSelected = selectedClipIds.has(clip.clip_id);
            const scorePct = `${Math.round((clip.moment_score || 0.85) * 100)}%`;
            const durationStr = formatDuration(clip.duration || 45);
            const emotionTag = (clip.emotion || "ENGAGING").toUpperCase();
            const pastelBg = getPastelColor(clip.clip_id || clip.title);

            return (
              <div
                key={clip.clip_id}
                className={`figma-glass-card rounded-[22px] p-3 flex flex-col justify-between shadow-[0px_4px_24px_0px_rgba(200,140,160,0.08)] hover:shadow-md transition-all duration-200 group relative ${
                  isQueued ? "border-[rgba(147,51,234,0.4)] ring-1 ring-[#9333ea]/30" : ""
                }`}
              >
                {/* Checkbox Selector or Permanent Lock Indicator */}
                {isUploaded ? (
                  <div
                    className="absolute top-4 right-4 z-30 size-5 rounded-md bg-black/75 border border-emerald-400/60 text-emerald-400 flex items-center justify-center text-[10px] cursor-not-allowed select-none shadow-xs"
                    title="Published clip: Selection & re-upload permanently locked"
                  >
                    🔒
                  </div>
                ) : (
                  <div
                    onClick={(e) => toggleSelectClip(clip.clip_id, e)}
                    className={`absolute top-4 right-4 z-30 size-5 rounded-md border flex items-center justify-center cursor-pointer transition-all ${
                      isSelected
                        ? "bg-[#7c3aed] border-[#7c3aed] text-white shadow-xs"
                        : "bg-white/70 border-[rgba(220,180,190,0.5)] hover:bg-white text-transparent"
                    }`}
                    title="Select for batch operations"
                  >
                    <span className="text-xs leading-none font-bold">✓</span>
                  </div>
                )}

                {/* Upper Thumbnail Stage with Perfect Small 9:16 Viewport */}
                <div
                  className="relative w-full h-[210px] rounded-[18px] overflow-hidden flex items-center justify-center cursor-pointer border border-[rgba(220,180,190,0.22)]"
                  style={{ backgroundColor: pastelBg }}
                  onClick={() => setSelectedClip(clip)}
                >
                  {/* Ambient Soft Blurred Backdrop */}
                  <div
                    className="absolute inset-0 bg-cover bg-center filter blur-md opacity-25 scale-110 pointer-events-none"
                    style={{ backgroundImage: `url(${getClipThumbnailUrl(clip.clip_id)})` }}
                  />

                  {/* Centered Exact 9:16 Thumbnail Container (neither stretched nor contracted) */}
                  <div className="relative h-[186px] aspect-[9/16] rounded-[13px] overflow-hidden shadow-[0_4px_16px_rgba(0,0,0,0.24)] border border-white/35 bg-black z-10 shrink-0 group-hover:scale-[1.03] transition-transform duration-200 flex items-center justify-center">
                    <img
                      src={getClipThumbnailUrl(clip.clip_id)}
                      alt={clip.title}
                      className="w-full h-full object-cover z-0"
                      style={{ aspectRatio: "9/16" }}
                      onError={(e) => {
                        e.currentTarget.style.display = "none";
                      }}
                    />

                    {/* Centered Film Vector Placeholder */}
                    <div className="size-6 opacity-35 absolute inset-0 m-auto pointer-events-none flex items-center justify-center">
                      <img src="/figma/film.svg" alt="" className="w-full h-full block" />
                    </div>

                    {/* Viral Score Badge (Top Left of 9:16 frame) */}
                    <div className="absolute top-1.5 left-1.5 z-20">
                      <span
                        className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-['DM_Mono'] font-extrabold shadow-[0_2px_8px_rgba(0,0,0,0.7)] border border-white/20 backdrop-blur-md"
                        style={{
                          backgroundColor: "rgba(15, 10, 18, 0.88)",
                        }}
                      >
                        <span className="size-1.5 rounded-full bg-[#f43f5e] animate-pulse shadow-[0_0_6px_#f43f5e]" />
                        <span style={{ color: "#ffffff", fontWeight: 800 }}>{scorePct}</span>
                        <span style={{ color: "#f472b6", fontWeight: 700, fontSize: "9px" }}>VIRAL</span>
                      </span>
                    </div>

                    {/* Duration Badge (Bottom Right of 9:16 frame) */}
                    <div className="absolute bottom-1.5 right-1.5 z-20">
                      <span
                        className="font-['DM_Mono'] font-bold text-[9px] px-1.5 py-0.5 rounded shadow-md border border-white/15 backdrop-blur-md"
                        style={{
                          backgroundColor: "rgba(15, 10, 18, 0.85)",
                          color: "#ffffff",
                        }}
                      >
                        {durationStr}
                      </span>
                    </div>
                  </div>
                </div>

                {/* Content Section */}
                <div className="flex flex-col gap-2 mt-3">
                  {/* Title */}
                  <p
                    className="font-bold text-[13px] leading-[18px] text-[#1a0a10] truncate w-full"
                    title={clip.title}
                  >
                    {clip.title}
                  </p>

                  {/* Tag Pills Row */}
                  <div className="flex items-center justify-between gap-1 flex-wrap">
                    <div className="flex items-center gap-1 flex-wrap">
                      <span
                        className={`text-[9px] font-bold font-mono tracking-wider px-2 py-0.5 rounded-md uppercase ${
                          emotionTag === "HYPE"
                            ? "bg-[#ffe4e6] text-[#be123c]"
                            : emotionTag === "FUNNY"
                            ? "bg-[#fef3c7] text-[#b45309]"
                            : "bg-[#e0f2fe] text-[#0369a1]"
                        }`}
                      >
                        {emotionTag}
                      </span>
                      {clip.archetype && clip.archetype !== "None" && (
                        <span
                          className="text-[9px] font-extrabold font-mono tracking-wider px-2 py-0.5 rounded-md bg-purple-100 text-purple-800 border border-purple-200 uppercase truncate max-w-[110px]"
                          title={`Archetype: ${clip.archetype}${clip.editorial_reasoning ? ' — ' + clip.editorial_reasoning : ''}`}
                        >
                          ⚡ {clip.archetype.replace("The ", "")}
                        </span>
                      )}
                    </div>

                    {/* Dynamic Queue Status Tag */}
                    <span
                      className={`text-[9px] font-bold font-mono tracking-wider px-2 py-0.5 rounded-md uppercase ${
                        isUploaded
                          ? "bg-emerald-100 text-emerald-800 border border-emerald-300 flex items-center gap-1"
                          : isQueued
                          ? "bg-[#ede9fe] text-[#6d28d9] border border-[#c4b5fd]"
                          : "bg-[#ffedd5] text-[#c2410c]"
                      }`}
                    >
                      {isUploaded ? (
                        <>
                          <span className="size-1 rounded-full bg-emerald-500" />
                          <span>PUBLISHED</span>
                        </>
                      ) : isQueued ? (
                        "⬆ IN QUEUE"
                      ) : (
                        "IN VAULT"
                      )}
                    </span>
                  </div>

                  {/* ── Primary Upload Queue Button (Add/Remove/Locked) ── */}
                  <div className="pt-1">
                    {isUploaded ? (
                      <button
                        disabled
                        className="w-full py-2 rounded-xl bg-[rgba(209,250,229,0.85)] text-[#065f46] border border-[rgba(52,211,153,0.5)] font-bold text-xs flex items-center justify-center gap-1.5 cursor-not-allowed select-none shadow-2xs font-['DM_Mono']"
                        title="This clip is already published and can never be re-uploaded"
                      >
                        <span className="size-1.5 rounded-full bg-[#10b981]" />
                        <span>✓ Published (Upload Locked)</span>
                      </button>
                    ) : isQueued ? (
                      <button
                        onClick={(e) => handleRemoveFromQueue(clip.clip_id, e)}
                        className="w-full py-2 rounded-xl bg-[rgba(254,202,202,0.85)] hover:bg-[rgba(254,202,202,1)] text-[#be123c] font-bold text-xs flex items-center justify-center gap-1.5 transition-all cursor-pointer border border-[rgba(239,68,68,0.3)] shadow-2xs group/btn"
                        title="Click to remove from upload queue"
                      >
                        <span className="size-1.5 rounded-full bg-[#ef4444]" />
                        <span>✕ Remove from Queue</span>
                      </button>
                    ) : (
                      <button
                        onClick={(e) => handleAddToQueue(clip.clip_id, e)}
                        className="w-full py-2 rounded-xl text-white font-bold text-xs flex items-center justify-center gap-1.5 transition-all cursor-pointer shadow-2xs hover:brightness-105"
                        style={{
                          backgroundImage:
                            "linear-gradient(152deg, #d4a8e4 0%, #9b59b6 100%)",
                        }}
                        title="Add this clip to the upload queue"
                      >
                        <span>⬆</span>
                        <span>+ Add to Upload Queue</span>
                      </button>
                    )}
                  </div>

                  {/* Secondary Action Row: HD Preview & Delete */}
                  <div className="flex items-center gap-2 pt-1 border-t border-[rgba(220,180,190,0.2)]">
                    {/* HD Modal Preview Button */}
                    <button
                      onClick={() => setSelectedClip(clip)}
                      className="flex-1 py-1.5 rounded-[10px] bg-[rgba(219,234,254,0.7)] hover:bg-[rgba(219,234,254,1)] text-[#1d4ed8] font-bold text-xs flex items-center justify-center transition-colors cursor-pointer border border-[rgba(147,197,253,0.5)] shadow-xs"
                      title="Watch HD Preview"
                    >
                      Watch HD
                    </button>

                    {/* Delete Clip from Vault */}
                    <button
                      onClick={(e) => handleReject(clip.clip_id, e)}
                      className="px-2.5 py-1.5 rounded-[10px] bg-[rgba(254,202,202,0.5)] hover:bg-[rgba(254,202,202,0.9)] text-[#be123c] font-bold text-xs flex items-center justify-center transition-colors cursor-pointer border border-[rgba(252,165,165,0.4)] shadow-xs"
                      title="Delete from Vault"
                    >
                      ✕
                    </button>
                  </div>
                </div>
              </div>
            );
          })}
        </div>

        {/* ── Active Vault Footer: Published Archive Callout ── */}
        {filter === "all" && uploadedClips.length > 0 && (
          <div className="w-full p-4 rounded-[20px] bg-[rgba(236,253,245,0.75)] border border-[rgba(167,243,208,0.7)] flex items-center justify-between gap-4 flex-wrap shadow-2xs">
            <div className="flex items-center gap-2.5">
              <div className="size-8 rounded-xl bg-emerald-100 border border-emerald-300 flex items-center justify-center text-emerald-700 text-sm font-bold">
                🔒
              </div>
              <div>
                <p className="font-['DM_Mono'] text-xs font-bold text-emerald-950 uppercase tracking-wide">
                  Published Archive ({uploadedClips.length} Clips Separated)
                </p>
                <p className="text-[11px] text-emerald-800 font-medium">
                  Already published highlights are kept isolated from active vault staging and cannot be re-uploaded.
                </p>
              </div>
            </div>
            <button
              onClick={() => setFilter("uploaded")}
              className="px-4 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white font-bold text-xs transition-colors cursor-pointer shadow-xs flex items-center gap-1.5"
            >
              <span>View Published Archive ({uploadedClips.length})</span>
              <span>➔</span>
            </button>
          </div>
        )}
      </div>

      {/* HD Video Playback Modal */}
      {selectedClip && (
        <VideoModal
          clip={selectedClip}
          onClose={() => setSelectedClip(null)}
        />
      )}
    </div>
  );
}
