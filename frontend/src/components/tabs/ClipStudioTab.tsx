"use client";

import React, { useState, useEffect, useRef, useCallback } from "react";
import confetti from "canvas-confetti";
import {
  getClips,
  processVOD,
  approveClip,
  rejectClip,
  getClipVideoUrl,
  getClipThumbnailUrl,
  getVODJobProgress,
} from "@/lib/api";

const CAPTION_PRESETS = [
  { id: "hormozi", name: "Alex Hormozi Yellow" },
  { id: "glacier_glow", name: "Glacier Glow Cyan" },
  { id: "mrbeast", name: "MrBeast Hype" },
  { id: "tiktok_bold", name: "TikTok Bold" },
  { id: "neon", name: "Neon Cyber" },
  { id: "minimal_clean", name: "Clean Sans" },
];

const FRAMING_MODES = [
  { id: "white_canvas", name: "16:9 White Canvas (Top Hook + Streamer Badge + Bottom Captions)" },
  { id: "gamer", name: "Gamer Split" },
  { id: "center", name: "AI Centered" },
  { id: "speaker", name: "Active Speaker" },
  { id: "split", name: "Split Screen" },
  { id: "blur", name: "Blurred Backdrop" },
];

const PASTEL_PALETTES = [
  "rgba(235,185,195,0.5)",
  "rgba(210,230,195,0.5)",
  "rgba(205,220,240,0.5)",
  "rgba(225,210,240,0.5)",
  "rgba(195,230,220,0.5)",
  "rgba(245,220,195,0.5)",
];

function getPastelBg(seed: string): string {
  let hash = 0;
  for (let i = 0; i < seed.length; i++) {
    hash = (hash << 5) - hash + seed.charCodeAt(i);
    hash |= 0;
  }
  return PASTEL_PALETTES[Math.abs(hash) % PASTEL_PALETTES.length];
}

function formatDurationSeconds(sec: number): string {
  if (isNaN(sec) || sec < 0) return "0:00";
  const mins = Math.floor(sec / 60);
  const remSecs = Math.floor(sec % 60);
  return `${mins}:${remSecs.toString().padStart(2, "0")}`;
}

export interface ClipItem {
  id: string;
  clip_id: string;
  title: string;
  score: string;
  rawScore: number;
  duration: string;
  rawDuration: number;
  bg: string;
  status: "pending" | "approved" | "rejected" | "uploaded";
  videoUrl: string;
  thumbnailUrl: string;
  streamer_name?: string;
  hook_text?: string;
}

export default function ClipStudioTab() {
  const [url, setUrl] = useState("");
  const [selectedCaption, setSelectedCaption] = useState("hormozi");
  const [selectedFraming, setSelectedFraming] = useState("white_canvas");
  const [clips, setClips] = useState<ClipItem[]>([]);
  const [selectedClip, setSelectedClip] = useState<ClipItem | null>(null);
  const [loadingClips, setLoadingClips] = useState(true);

  // Video playback telemetry
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [videoDuration, setVideoDuration] = useState(0);
  const [scrubberPercent, setScrubberPercent] = useState(0);

  // Ingestion job state
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [jobProgress, setJobProgress] = useState<number>(0);
  const [jobStatusText, setJobStatusText] = useState<string>("");
  const [publishFeedback, setPublishFeedback] = useState<string | null>(null);

  const videoRef = useRef<HTMLVideoElement>(null);
  const progressPollRef = useRef<NodeJS.Timeout | null>(null);

  // Fetch live clips from database
  const loadClips = useCallback(async () => {
    try {
      const data = await getClips();
      const rawList = data?.clips || [];
      const formatted: ClipItem[] = rawList.map((c: any) => {
        const rawDur = typeof c.duration === "number" ? c.duration : 60;
        const scoreVal =
          typeof c.moment_score === "number"
            ? Math.round(c.moment_score * 100)
            : 85;
        const clipId = String(c.clip_id || c.id);
        return {
          id: String(c.id || clipId),
          clip_id: clipId,
          title: c.title || clipId,
          score: `${scoreVal}%`,
          rawScore: scoreVal,
          duration: formatDurationSeconds(rawDur),
          rawDuration: rawDur,
          bg: getPastelBg(clipId),
          status: (c.status as any) || "pending",
          videoUrl: getClipVideoUrl(clipId),
          thumbnailUrl: getClipThumbnailUrl(clipId),
          streamer_name: c.streamer_name,
          hook_text: c.hook_text,
        };
      });

      if (formatted.length > 0) {
        setClips(formatted);
        setSelectedClip((prev) => {
          if (!prev && formatted.length > 0) return formatted[0];
          if (prev && !formatted.some((c) => c.clip_id === prev.clip_id)) {
            return formatted[0];
          }
          return prev;
        });
      } else {
        const fallbacks: ClipItem[] = [
          {
            id: "cs-1",
            clip_id: "clip-xqc-1",
            title: "xQcOW Rage Moment",
            score: "96%",
            rawScore: 96,
            duration: "0:47",
            rawDuration: 47,
            bg: "rgba(248, 215, 225, 0.7)",
            status: "pending",
            videoUrl: "",
            thumbnailUrl: "",
            streamer_name: "xQcOW",
          },
          {
            id: "cs-2",
            clip_id: "clip-kai-2",
            title: "Kai Cenat Freestyle",
            score: "88%",
            rawScore: 88,
            duration: "1:02",
            rawDuration: 62,
            bg: "rgba(222, 242, 228, 0.7)",
            status: "pending",
            videoUrl: "",
            thumbnailUrl: "",
            streamer_name: "Kai Cenat",
          },
          {
            id: "cs-3",
            clip_id: "clip-lud-3",
            title: "Ludwig Debate Clip",
            score: "91%",
            rawScore: 91,
            duration: "0:38",
            rawDuration: 38,
            bg: "rgba(225, 235, 252, 0.7)",
            status: "pending",
            videoUrl: "",
            thumbnailUrl: "",
            streamer_name: "Ludwig",
          },
        ];
        setClips(fallbacks);
        setSelectedClip(fallbacks[0]);
      }
    } catch (err) {
      console.error("[ClipStudio] Failed to load live clips:", err);
    } finally {
      setLoadingClips(false);
    }
  }, []);

  useEffect(() => {
    loadClips();
  }, [loadClips]);

  // Handle active VOD job progress polling
  useEffect(() => {
    if (!activeJobId) {
      if (progressPollRef.current) {
        clearInterval(progressPollRef.current);
        progressPollRef.current = null;
      }
      return;
    }

    const poll = async () => {
      try {
        const job = await getVODJobProgress(activeJobId);
        if (!job) return;

        if (typeof job.progress === "number") {
          setJobProgress(job.progress);
        }
        if (job.status_text) {
          setJobStatusText(job.status_text);
        }

        if (job.status === "completed") {
          setJobProgress(100);
          setJobStatusText("Complete!");
          setIsSubmitting(false);
          setActiveJobId(null);
          await loadClips();
          confetti({
            particleCount: 80,
            spread: 60,
            origin: { y: 0.6 },
          });
        } else if (job.status === "failed") {
          setIsSubmitting(false);
          setActiveJobId(null);
          setJobStatusText(`Failed: ${job.error || "Unknown error"}`);
        }
      } catch (err) {
        console.warn("[ClipStudio] Poll error:", err);
      }
    };

    poll();
    progressPollRef.current = setInterval(poll, 1500);

    return () => {
      if (progressPollRef.current) {
        clearInterval(progressPollRef.current);
        progressPollRef.current = null;
      }
    };
  }, [activeJobId, loadClips]);

  // Submit URL for ingestion
  const handleIngest = async (e: React.FormEvent) => {
    e.preventDefault();
    const cleanUrl = url.trim();
    if (!cleanUrl) return;

    setIsSubmitting(true);
    setJobProgress(5);
    setJobStatusText("Queuing Ingestion...");

    try {
      const res = await processVOD(cleanUrl, selectedFraming, selectedCaption);
      if (res && res.job_id) {
        setActiveJobId(res.job_id);
        setJobStatusText("Processing stream...");
        setUrl("");
      } else {
        setIsSubmitting(false);
        setJobStatusText(res?.error || "Failed to start ingestion");
      }
    } catch (err: any) {
      console.error("[ClipStudio] Ingestion error:", err);
      setIsSubmitting(false);
      setJobStatusText(err.message || "Failed to submit VOD");
    }
  };

  const handleSelectClip = (clip: ClipItem) => {
    setSelectedClip(clip);
    setCurrentTime(0);
    setScrubberPercent(0);
    setIsPlaying(false);
    if (videoRef.current) {
      videoRef.current.currentTime = 0;
      videoRef.current.pause();
    }
  };

  const handleLoadedMetadata = () => {
    if (videoRef.current) {
      const d = videoRef.current.duration || selectedClip?.rawDuration || 0;
      setVideoDuration(d);
    }
  };

  const handleTimeUpdate = () => {
    if (videoRef.current) {
      const curr = videoRef.current.currentTime;
      const dur = videoRef.current.duration || selectedClip?.rawDuration || 1;
      setCurrentTime(curr);
      setScrubberPercent(Math.min(100, Math.max(0, (curr / dur) * 100)));
    }
  };

  const handleTogglePlay = () => {
    if (!videoRef.current) return;
    if (videoRef.current.paused) {
      videoRef.current.play().catch((err) => {
        console.warn("[ClipStudio] Video play error:", err);
      });
      setIsPlaying(true);
    } else {
      videoRef.current.pause();
      setIsPlaying(false);
    }
  };

  const handleScrubberClick = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!videoRef.current) return;
    const rect = e.currentTarget.getBoundingClientRect();
    const clickX = e.clientX - rect.left;
    const ratio = Math.max(0, Math.min(1, clickX / rect.width));
    const targetTime = ratio * (videoRef.current.duration || selectedClip?.rawDuration || 0);
    videoRef.current.currentTime = targetTime;
    setCurrentTime(targetTime);
    setScrubberPercent(ratio * 100);
  };

  const handleApprove = async (clipId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      await approveClip(clipId);
      setClips((prev) =>
        prev.map((c) => (c.clip_id === clipId ? { ...c, status: "approved" } : c))
      );
      if (selectedClip && selectedClip.clip_id === clipId) {
        setSelectedClip((prev) => (prev ? { ...prev, status: "approved" } : null));
      }
      confetti({ particleCount: 50, spread: 50, origin: { y: 0.7 } });
    } catch (err) {
      console.error("[ClipStudio] Approve clip error:", err);
    }
  };

  const handleReject = async (clipId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      await rejectClip(clipId);
      setClips((prev) => prev.filter((c) => c.clip_id !== clipId));
      if (selectedClip && selectedClip.clip_id === clipId) {
        const remaining = clips.filter((c) => c.clip_id !== clipId);
        setSelectedClip(remaining.length > 0 ? remaining[0] : null);
      }
    } catch (err) {
      console.error("[ClipStudio] Reject clip error:", err);
    }
  };

  const handlePublishAll = async () => {
    if (!selectedClip) return;
    try {
      setPublishFeedback(`Publishing "${selectedClip.title}" to TikTok, YouTube Shorts & IG Reels...`);
      await approveClip(selectedClip.clip_id);
      setClips((prev) =>
        prev.map((c) =>
          c.clip_id === selectedClip.clip_id ? { ...c, status: "approved" } : c
        )
      );
      setSelectedClip((prev) => (prev ? { ...prev, status: "approved" } : null));
      confetti({
        particleCount: 120,
        spread: 80,
        origin: { y: 0.5 },
        colors: ["#c084cc", "#9b59b6", "#22c55e", "#7c3aed"],
      });
      setTimeout(() => setPublishFeedback(null), 4000);
    } catch (err: any) {
      console.error("[ClipStudio] Publish error:", err);
      setPublishFeedback(`Publish error: ${err.message || "Failed"}`);
      setTimeout(() => setPublishFeedback(null), 4000);
    }
  };

  const effectiveDuration = videoDuration || selectedClip?.rawDuration || 0;
  const timeDisplay = `${formatDurationSeconds(currentTime)} / ${formatDurationSeconds(effectiveDuration)}`;

  return (
    <div className="w-full flex justify-center pb-12 select-none" data-name="ClipStudio">
      {/* ── Outer Responsive 2-Column Container (Max 1440px, perfectly centered) ── */}
      <div className="w-full max-w-[1440px] flex flex-col lg:flex-row gap-6 items-start px-2 sm:px-4">
        {/* ═══════════════════════════════════════════════════════════════════
            LEFT STUDIO COLUMN (Flexible width, balanced cards)
            ═══════════════════════════════════════════════════════════════════ */}
        <div className="flex-1 min-w-0 w-full flex flex-col gap-5">
          {/* 1. PASTE LINK CARD */}
          <div
            className="figma-glass-card flex flex-col p-6 rounded-[22px] relative overflow-hidden w-full shadow-[0px_4px_24px_0px_rgba(200,140,160,0.08)]"
            data-node-id="1:72"
            data-name="Card"
          >
            <div className="shimmer-active" />
            <div className="flex items-center justify-between w-full relative z-10">
              <p className="font-['DM_Mono'] font-bold leading-none text-[#a06075] text-[11px] tracking-[1.5px] uppercase whitespace-nowrap">
                PASTE LINK
              </p>
              {jobStatusText && (
                <span className="font-['DM_Mono'] text-xs font-bold text-[#9b59b6] animate-pulse">
                  {jobStatusText} {jobProgress > 0 ? `(${jobProgress}%)` : ""}
                </span>
              )}
            </div>

            <form onSubmit={handleIngest} className="flex gap-3 items-center mt-4 w-full relative z-10">
              <div className="bg-[rgba(255,248,250,0.85)] border border-[rgba(220,180,190,0.4)] flex flex-1 h-12 items-center px-4 rounded-xl shadow-xs focus-within:border-[#9b59b6] transition-colors">
                <input
                  type="text"
                  value={url}
                  onChange={(e) => setUrl(e.target.value)}
                  placeholder="Paste YouTube / Twitch / Kick URL…"
                  disabled={isSubmitting}
                  className="w-full text-sm text-[#2a1018] placeholder-[rgba(58,16,32,0.45)] bg-transparent outline-none font-sans font-medium"
                />
              </div>
              <button
                type="submit"
                disabled={isSubmitting || !url.trim()}
                className="drop-shadow-[0px_4px_12px_rgba(155,89,182,0.35)] flex items-center justify-center px-7 h-12 rounded-xl shrink-0 cursor-pointer hover:brightness-105 active:scale-95 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                style={{
                  backgroundImage:
                    "linear-gradient(152.42deg, rgb(212, 168, 228) 0%, rgb(155, 89, 182) 100%)",
                }}
                data-name="Button"
              >
                <p className="font-semibold text-sm text-center !text-white whitespace-nowrap">
                  {isSubmitting ? "Starting..." : "Start"}
                </p>
              </button>
            </form>

            {/* Ingestion Progress Bar */}
            {isSubmitting && (
              <div className="w-full bg-[rgba(220,180,190,0.25)] h-1 rounded-full overflow-hidden mt-3 relative z-10">
                <div
                  className="bg-gradient-to-r from-[#c084cc] to-[#9b59b6] h-full transition-all duration-300"
                  style={{ width: `${jobProgress || 15}%` }}
                />
              </div>
            )}
          </div>

          {/* 2. CAPTION PRESET & FRAMING MODE CARD */}
          <div
            className="figma-glass-card flex flex-col p-6 rounded-[22px] relative overflow-hidden w-full gap-5 shadow-[0px_4px_24px_0px_rgba(200,140,160,0.08)]"
            data-node-id="1:84"
            data-name="Card"
          >
            <div className="shimmer-active" />

            {/* Section A: Caption Presets */}
            <div className="flex flex-col items-start w-full relative z-10">
              <p className="font-['DM_Mono'] font-bold leading-none text-[#a06075] text-[11px] tracking-[1.5px] uppercase whitespace-nowrap mb-3">
                CAPTION PRESET
              </p>
              <div className="flex flex-wrap gap-2.5 w-full">
                {CAPTION_PRESETS.map((preset) => {
                  const isActive = selectedCaption === preset.id;
                  return (
                    <button
                      key={preset.id}
                      onClick={() => setSelectedCaption(preset.id)}
                      className={`flex items-center justify-center px-4 py-2 rounded-full transition-all cursor-pointer text-xs font-semibold ${
                        isActive
                          ? "shadow-sm !text-white"
                          : "bg-[rgba(255,248,250,0.7)] border border-[rgba(220,180,190,0.4)] text-[#8070a0] hover:border-[#9b59b6]"
                      }`}
                      style={
                        isActive
                          ? {
                              backgroundImage:
                                "linear-gradient(164.19deg, rgb(192, 132, 204) 0%, rgb(155, 89, 182) 100%)",
                            }
                          : {}
                      }
                    >
                      {preset.name}
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Section B: Framing Modes */}
            <div className="flex flex-col items-start w-full relative z-10 border-t border-[rgba(220,180,190,0.25)] pt-4">
              <p className="font-['DM_Mono'] font-bold leading-none text-[#a06075] text-[11px] tracking-[1.5px] uppercase whitespace-nowrap mb-3">
                FRAMING MODE
              </p>
              <div className="flex flex-wrap gap-2.5 w-full">
                {FRAMING_MODES.map((mode) => {
                  const isActive = selectedFraming === mode.id;
                  return (
                    <button
                      key={mode.id}
                      onClick={() => setSelectedFraming(mode.id)}
                      className={`flex items-center justify-center px-4 py-2 rounded-full transition-all cursor-pointer text-xs font-semibold ${
                        isActive
                          ? "shadow-sm !text-white"
                          : "bg-[rgba(255,248,250,0.7)] border border-[rgba(220,180,190,0.4)] text-[#507068] hover:border-[#2d9b7a]"
                      }`}
                      style={
                        isActive
                          ? {
                              backgroundImage:
                                "linear-gradient(161.56deg, rgb(132, 204, 184) 0%, rgb(45, 155, 122) 100%)",
                            }
                          : {}
                      }
                    >
                      {mode.name}
                    </button>
                  );
                })}
              </div>
            </div>
          </div>

          {/* 3. GENERATED CLIPS (ONLY 3 RECENT - REST IN CLIP VAULT) */}
          <div
            className="figma-glass-card flex flex-col p-6 rounded-[22px] relative overflow-hidden w-full min-h-[360px] shadow-[0px_4px_24px_0px_rgba(200,140,160,0.08)]"
            data-node-id="1:132"
            data-name="Card"
          >
            <div className="shimmer-active" />
            <div className="flex items-center justify-between w-full relative z-10 pb-2">
              <p className="font-['DM_Mono'] font-bold leading-none text-[#a06075] text-[11px] tracking-[1.5px] uppercase whitespace-nowrap">
                RECENT CLIPS
              </p>
              <span className="font-['DM_Mono'] text-xs font-semibold text-[#8b2252]">
                Showing 3 recent • {clips.length} in Clip Vault
              </span>
            </div>

            <div className="w-full relative z-10 mt-3">
              {loadingClips ? (
                <div className="flex flex-col items-center justify-center py-24 w-full text-center">
                  <div className="size-6 mb-3 animate-spin text-[#9b59b6]">
                    <img src="/figma/film.svg" alt="" className="w-full h-full" />
                  </div>
                  <p className="font-medium text-xs text-[#8070a0]">
                    Synchronizing clip vault...
                  </p>
                </div>
              ) : clips.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-16 w-full text-center">
                  <div className="size-10 mb-3 opacity-40">
                    <img src="/figma/film.svg" alt="" className="w-full h-full" />
                  </div>
                  <p className="font-semibold text-sm text-[#2a1018]">
                    No Clips in Queue
                  </p>
                  <p className="text-xs text-[#a08090] mt-1 max-w-sm">
                    Paste a Twitch, YouTube, or Kick stream link above and click Start to harvest highlights autonomously.
                  </p>
                </div>
              ) : (
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 w-full">
                  {clips.slice(0, 3).map((clip) => {
                    const isSelected = selectedClip?.clip_id === clip.clip_id;
                    const isApproved = clip.status === "approved";

                    return (
                      <div
                        key={clip.clip_id}
                        onClick={() => handleSelectClip(clip)}
                        className={`bg-[rgba(255,255,255,0.75)] border flex flex-col rounded-2xl overflow-hidden cursor-pointer transition-all duration-200 group ${
                          isSelected
                            ? "border-[#9b59b6] ring-2 ring-[#9b59b6]/30 shadow-md transform -translate-y-0.5"
                            : "border-[rgba(220,180,190,0.3)] hover:border-[#c084cc] hover:shadow-sm"
                        }`}
                      >
                        {/* Perfect Small 9:16 Thumbnail Viewport */}
                        <div
                          className="w-full h-[205px] relative overflow-hidden flex items-center justify-center rounded-t-2xl border-b border-[rgba(220,180,190,0.22)]"
                          style={{ backgroundColor: clip.bg }}
                        >
                          {/* Ambient soft blurred backdrop from clip thumbnail */}
                          {clip.thumbnailUrl && (
                            <div
                              className="absolute inset-0 bg-cover bg-center filter blur-md opacity-25 scale-110 pointer-events-none"
                              style={{ backgroundImage: `url(${clip.thumbnailUrl})` }}
                            />
                          )}

                          {/* Exact 9:16 Centered Thumbnail Box (neither stretched nor contracted) */}
                          <div className="relative h-[185px] aspect-[9/16] rounded-[13px] overflow-hidden shadow-[0_4px_16px_rgba(0,0,0,0.22)] border border-white/35 bg-black flex items-center justify-center z-10 shrink-0 group-hover:scale-[1.03] transition-transform duration-200">
                            <img
                              src={clip.thumbnailUrl}
                              alt={clip.title}
                              className="w-full h-full object-cover z-0"
                              style={{ aspectRatio: "9/16" }}
                              onError={(e) => {
                                e.currentTarget.style.display = "none";
                              }}
                            />
                            <div className="size-5 relative z-10 opacity-40 pointer-events-none flex items-center justify-center">
                              <img alt="" className="w-full h-full block" src="/figma/film.svg" />
                            </div>

                            {/* Viral Score Badge on Thumbnail (Top-Left) */}
                            <div className="absolute top-1.5 left-1.5 z-20">
                              <span
                                className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[9px] font-['DM_Mono'] font-extrabold shadow-md border border-white/25 backdrop-blur-md"
                                style={{ backgroundColor: "rgba(15, 10, 18, 0.88)" }}
                              >
                                <span className="size-1.5 rounded-full bg-[#f43f5e] animate-pulse" />
                                <span style={{ color: "#ffffff", fontWeight: 800 }}>{clip.score}</span>
                                <span style={{ color: "#f472b6", fontSize: "8px", fontWeight: 700 }}>VIRAL</span>
                              </span>
                            </div>

                            {/* Duration Badge Bottom-Right */}
                            <div className="absolute bottom-1.5 right-1.5 z-20">
                              <span
                                className="font-['DM_Mono'] font-bold text-[9px] px-1.5 py-0.5 rounded shadow-md border border-white/15 backdrop-blur-md"
                                style={{ backgroundColor: "rgba(15, 10, 18, 0.85)", color: "#ffffff" }}
                              >
                                {clip.duration}
                              </span>
                            </div>

                            {/* Approved Status Badge Top-Right */}
                            {isApproved && (
                              <div className="absolute top-1.5 right-1.5 z-20 bg-emerald-500 text-white rounded-full p-0.5 shadow-sm flex items-center justify-center size-4">
                                <img alt="" className="w-2.5 h-2.5 block filter brightness-200" src="/figma/check.svg" />
                              </div>
                            )}
                          </div>
                        </div>

                        {/* Card Info & Quick Actions */}
                        <div className="p-3.5 flex flex-col justify-between flex-1 gap-2.5">
                          <div>
                            <p className="font-semibold text-xs text-[#2a1018] truncate w-full" title={clip.title}>
                              {clip.title}
                            </p>
                          </div>

                          <div className="flex items-center justify-between">
                            <div
                              className="px-2.5 py-1 rounded-md flex items-center gap-1.5 shadow-2xs border border-[rgba(22,101,52,0.25)]"
                              style={{ backgroundColor: "rgba(220, 252, 231, 0.95)" }}
                            >
                              <span className="size-1.5 rounded-full bg-[#16a34a]" />
                              <p className="font-['DM_Mono'] font-extrabold text-[#14532d] text-[11px] leading-none" style={{ color: "#14532d" }}>
                                {clip.score}
                              </p>
                            </div>

                            {/* Responsive 2-Button Action Grid */}
                            <div className="flex items-center gap-1.5">
                              <button
                                onClick={(e) => handleApprove(clip.clip_id, e)}
                                className={`flex items-center justify-center px-3 py-1.5 rounded-lg transition-colors cursor-pointer ${
                                  isApproved
                                    ? "bg-emerald-500 text-white"
                                    : "bg-[rgba(187,247,208,0.7)] hover:bg-[rgba(187,247,208,1)] text-emerald-900"
                                }`}
                                title={isApproved ? "Approved" : "Approve Clip"}
                              >
                                <img alt="" className="w-3 h-3 block" src="/figma/check.svg" />
                              </button>
                              <button
                                onClick={(e) => handleReject(clip.clip_id, e)}
                                className="bg-[rgba(254,202,202,0.7)] hover:bg-[rgba(254,202,202,1)] text-rose-900 flex items-center justify-center px-3 py-1.5 rounded-lg transition-colors cursor-pointer"
                                title="Reject & Delete Clip"
                              >
                                <img alt="" className="w-3 h-3 block" src="/figma/icon.svg" />
                              </button>
                            </div>
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          </div>
        </div>

        {/* ═══════════════════════════════════════════════════════════════════
            RIGHT COLUMN: PREVIEW PLAYER & PUBLISH TO ALL PLATFORMS (320px)
            ═══════════════════════════════════════════════════════════════════ */}
        <div className="w-full lg:w-[320px] shrink-0 flex flex-col gap-4">
          {/* PREVIEW Card */}
          <div
            className="figma-glass-card flex flex-col p-5 rounded-[22px] relative overflow-hidden w-full shadow-[0px_4px_24px_0px_rgba(200,140,160,0.08)]"
            data-node-id="1:338"
            data-name="Card"
          >
            <div className="shimmer-active" />
            <div className="flex items-center justify-between w-full relative z-10 mb-3">
              <p className="font-['DM_Mono'] font-bold leading-none text-[#a06075] text-[11px] tracking-[1.5px] uppercase whitespace-nowrap">
                PREVIEW
              </p>
              <span className="font-['DM_Mono'] text-[10px] text-[#b090a0]">
                9:16 VERTICAL
              </span>
            </div>

            {/* 9:16 Vertical Video Screen */}
            <div
              className="aspect-[9/16] w-full rounded-xl overflow-hidden relative bg-black flex items-center justify-center shadow-inner z-10"
              style={{
                backgroundImage:
                  "linear-gradient(124.4deg, rgba(220, 185, 235, 0.3) 6%, rgba(185, 215, 235, 0.3) 94%)",
              }}
              data-name="ClipStudio"
            >
              {selectedClip?.videoUrl ? (
                <video
                  ref={videoRef}
                  key={selectedClip.videoUrl}
                  src={selectedClip.videoUrl}
                  className="w-full h-full object-cover cursor-pointer"
                  playsInline
                  onClick={handleTogglePlay}
                  onLoadedMetadata={handleLoadedMetadata}
                  onTimeUpdate={handleTimeUpdate}
                  onPlay={() => setIsPlaying(true)}
                  onPause={() => setIsPlaying(false)}
                  onEnded={() => setIsPlaying(false)}
                />
              ) : (
                <div className="flex flex-col items-center gap-2 text-center p-4">
                  <div className="size-6 opacity-40">
                    <img alt="" className="w-full h-full block" src="/figma/film.svg" />
                  </div>
                  <p className="font-['DM_Mono'] text-[11px] text-[#b090a0] whitespace-nowrap">
                    1080 × 1920
                  </p>
                </div>
              )}

              {/* Play Overlay Badge */}
              {selectedClip?.videoUrl && !isPlaying && (
                <div
                  onClick={handleTogglePlay}
                  className="absolute inset-0 flex items-center justify-center bg-black/25 cursor-pointer transition-opacity"
                >
                  <div className="size-12 rounded-full bg-white/85 backdrop-blur-xs flex items-center justify-center shadow-lg hover:scale-105 transition-transform">
                    <div className="size-4 ml-0.5">
                      <img alt="" className="w-full h-full block" src="/figma/play.svg" />
                    </div>
                  </div>
                </div>
              )}
            </div>

            {/* Scrubber & Controls */}
            <div className="flex flex-col gap-2 mt-3.5 w-full relative z-10">
              <div className="flex gap-2 items-center w-full">
                {/* Interactive Scrubber Track */}
                <div
                  onClick={handleScrubberClick}
                  className="bg-[rgba(220,180,190,0.35)] flex-1 h-1.5 rounded-full cursor-pointer relative hover:h-2 transition-all"
                >
                  <div
                    className="bg-gradient-to-r from-[#c084cc] to-[#9b59b6] h-full rounded-full transition-all duration-75"
                    style={{ width: `${scrubberPercent}%` }}
                  />
                </div>
                {/* Play / Pause Toggle Button */}
                <div
                  onClick={handleTogglePlay}
                  className="flex items-center justify-center rounded-lg size-6 cursor-pointer hover:bg-[rgba(240,180,195,0.3)] transition-colors shrink-0"
                  title={isPlaying ? "Pause" : "Play"}
                >
                  <div className="size-3">
                    <img alt="" className="w-full h-full block" src="/figma/play.svg" />
                  </div>
                </div>
              </div>
              <p className="font-['DM_Mono'] text-[11px] text-[#a08090] text-center">
                {timeDisplay}
              </p>
            </div>
          </div>

          {/* Action Button: Publish to All Platforms */}
          <button
            onClick={handlePublishAll}
            disabled={!selectedClip}
            className="drop-shadow-[0px_4px_14px_rgba(124,58,237,0.35)] flex items-center justify-center h-12 rounded-xl w-full cursor-pointer hover:brightness-105 active:scale-98 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
            style={{
              backgroundImage:
                "linear-gradient(167.69deg, rgb(192, 132, 204) 0%, rgb(124, 58, 237) 100%)",
            }}
            data-name="Button"
          >
            <p className="font-semibold text-sm text-center !text-white whitespace-nowrap">
              Publish to All Platforms
            </p>
          </button>

          {/* Feedback Toast */}
          {publishFeedback && (
            <div className="w-full p-3 rounded-xl bg-purple-500/10 border border-purple-500/20 text-center animate-fadeIn">
              <p className="font-['DM_Mono'] text-xs text-purple-700 font-bold leading-tight">
                {publishFeedback}
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
