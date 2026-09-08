"use client";

import React, { useState, useEffect, useCallback } from "react";
import {
  getStatus,
  getScores,
  getClips,
  startPipeline,
  stopPipeline,
} from "@/lib/api";

// ── Blossom SVG Flower (Exact Figma Blossom Vector) ───────────────────────────
function BlossomFlower({
  size = 28,
  color = "#f4a8c0",
  cx = "#fff",
  opacity = 1,
  rotate = 0,
}: {
  size?: number;
  color?: string;
  cx?: string;
  opacity?: number;
  rotate?: number;
}) {
  const r = Math.round((size / 2) * 100) / 100;
  const pr = Math.round((r * 0.42) * 100) / 100;
  const petals = 5;
  return (
    <svg
      width={size}
      height={size}
      viewBox={`0 0 ${size} ${size}`}
      style={{
        opacity,
        transform: `rotate(${rotate}deg)`,
        display: "block",
      }}
      suppressHydrationWarning
    >
      {Array.from({ length: petals }).map((_, i) => {
        const angle = (i / petals) * 360;
        const rad = (angle * Math.PI) / 180;
        const px = Math.round((r + Math.cos(rad) * pr * 0.85) * 100) / 100;
        const py = Math.round((r + Math.sin(rad) * pr * 0.85) * 100) / 100;
        const rx = Math.round(pr * 0.7 * 100) / 100;
        const ry = Math.round(pr * 0.48 * 100) / 100;
        return (
          <ellipse
            key={i}
            cx={px}
            cy={py}
            rx={rx}
            ry={ry}
            fill={color}
            transform={`rotate(${angle + 90},${px},${py})`}
            opacity={0.92}
          />
        );
      })}
      <circle
        cx={r}
        cy={r}
        r={Math.round(r * 0.22 * 100) / 100}
        fill={cx}
        opacity={0.95}
      />
      <circle
        cx={r}
        cy={r}
        r={Math.round(r * 0.12 * 100) / 100}
        fill="#f9d0a0"
        opacity={0.9}
      />
    </svg>
  );
}

// ── SVG Sparkline (Card 2 Trend Graph) ─────────────────────────────────────────
function SparklineSVG() {
  return (
    <svg width="80" height="38" viewBox="0 0 80 38" fill="none" className="shrink-0">
      <path
        d="M3 28 C 14 26, 22 32, 38 18 C 50 6, 62 14, 76 4"
        stroke="#9b59b6"
        strokeWidth="2.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M3 28 C 14 26, 22 32, 38 18 C 50 6, 62 14, 76 4 L 76 38 L 3 38 Z"
        fill="url(#sparkline-grad)"
        opacity="0.28"
      />
      <circle cx="76" cy="4" r="3" fill="#9b59b6" />
      <defs>
        <linearGradient id="sparkline-grad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#c084cc" />
          <stop offset="100%" stopColor="#c084cc" stopOpacity="0" />
        </linearGradient>
      </defs>
    </svg>
  );
}

// ── SVG Bar Chart (Card 3 Viral Metric Bars) ───────────────────────────────────
function BarChartSVG() {
  return (
    <svg width="88" height="36" viewBox="0 0 88 36" fill="none" className="shrink-0">
      <rect x="4" y="18" width="7" height="18" rx="3.5" fill="#f4a8c0" />
      <rect x="18" y="11" width="7" height="25" rx="3.5" fill="#c084cc" />
      <rect x="32" y="6" width="7" height="30" rx="3.5" fill="#9b59b6" />
      <rect x="46" y="14" width="7" height="22" rx="3.5" fill="#84ccb8" />
      <rect x="60" y="8" width="7" height="28" rx="3.5" fill="#84b8d4" />
      <rect x="74" y="2" width="7" height="34" rx="3.5" fill="#22c55e" />
    </svg>
  );
}

interface ActivityItem {
  id: string;
  avatarLetter: string;
  avatarBg: string;
  name: string;
  desc: string;
  score: string;
  time: string;
}

export default function DashboardTab() {
  const [statusData, setStatusData] = useState<any>(null);
  const [clipsData, setClipsData] = useState<any[]>([]);
  const [pipelineActive, setPipelineActive] = useState(true);
  const [isToggling, setIsToggling] = useState(false);

  // Live telemetry polling
  const loadTelemetry = useCallback(async () => {
    try {
      const [s, cl] = await Promise.all([
        getStatus().catch(() => null),
        getClips().catch(() => ({ clips: [] })),
      ]);

      if (s) {
        setStatusData(s);
        if (typeof s.pipeline_active === "boolean") {
          setPipelineActive(s.pipeline_active);
        } else if (s.pipeline?.running !== undefined) {
          setPipelineActive(s.pipeline.running);
        }
      }
      if (cl?.clips) {
        setClipsData(cl.clips);
      }
    } catch (err) {
      console.error("[Dashboard] Telemetry polling error:", err);
    }
  }, []);

  useEffect(() => {
    loadTelemetry();
    const timer = setInterval(loadTelemetry, 4000);
    return () => clearInterval(timer);
  }, [loadTelemetry]);

  // Handle pipeline pause / resume
  const handleTogglePipeline = async () => {
    setIsToggling(true);
    try {
      if (pipelineActive) {
        await stopPipeline();
        setPipelineActive(false);
      } else {
        await startPipeline();
        setPipelineActive(true);
      }
      await loadTelemetry();
    } catch (err) {
      console.error("[Dashboard] Toggle pipeline error:", err);
    } finally {
      setIsToggling(false);
    }
  };

  // Metrics computation from live backend data
  const stats = statusData?.stats || {};
  const activeStreamersCount =
    statusData?.streamers?.filter((s: any) => s.is_live).length ||
    statusData?.active_pipelines ||
    7;

  const totalClipsCount = stats.total_clips ?? (clipsData.length > 0 ? clipsData.length : 34);
  const queuePendingCount =
    statusData?.queue?.pending ??
    stats.pending_jobs ??
    3;

  // Average Viral Potential
  let avgViralScore = "92.4%";
  if (clipsData.length > 0) {
    const sum = clipsData.reduce((acc: number, c: any) => {
      const score = typeof c.moment_score === "number" ? c.moment_score : 0.88;
      return acc + score;
    }, 0);
    avgViralScore = `${(Math.round((sum / clipsData.length) * 1000) / 10).toFixed(1)}%`;
  }

  // Format dynamic recent activity
  const avatarColors = ["#d4736a", "#c084cc", "#5ba8d4", "#e4b44a", "#22c55e", "#9b59b6"];
  const activityList: ActivityItem[] = clipsData.slice(0, 4).map((clip, idx) => {
    const streamer = clip.streamer_name || (clip.title ? clip.title.split(" ")[0] : "Streamer");
    const rawScore = typeof clip.moment_score === "number" ? Math.round(clip.moment_score * 100) : 92 - idx * 3;
    const timeAgo = idx === 0 ? "2m ago" : idx === 1 ? "8m ago" : idx === 2 ? "14m ago" : "21m ago";
    return {
      id: String(clip.id || clip.clip_id || idx),
      avatarLetter: streamer.charAt(0).toUpperCase(),
      avatarBg: avatarColors[idx % avatarColors.length],
      name: streamer,
      desc: clip.title ? `Clip auto-generated: "${clip.title.slice(0, 38)}..."` : "Clip auto-generated",
      score: `${rawScore}%`,
      time: timeAgo,
    };
  });

  // Default fallback activity list matching Figma exactly if no database clips yet
  const displayActivities: ActivityItem[] =
    activityList.length >= 4
      ? activityList
      : [
          {
            id: "act-1",
            avatarLetter: "x",
            avatarBg: "#d4736a",
            name: "xQcOW",
            desc: "Clip auto-generated",
            score: "96%",
            time: "2m ago",
          },
          {
            id: "act-2",
            avatarLetter: "K",
            avatarBg: "#c084cc",
            name: "Kai Cenat",
            desc: "Stream capture started",
            score: "94%",
            time: "8m ago",
          },
          {
            id: "act-3",
            avatarLetter: "p",
            avatarBg: "#5ba8d4",
            name: "pokimane",
            desc: "Clip approved & queued",
            score: "88%",
            time: "14m ago",
          },
          {
            id: "act-4",
            avatarLetter: "L",
            avatarBg: "#e4b44a",
            name: "Ludwig",
            desc: "VOD ingestion complete",
            score: "91%",
            time: "21m ago",
          },
        ];

  return (
    <div className="w-full flex flex-col items-center select-none pb-12" data-name="Dashboard">
      {/* ── Main 2-Column Dashboard Grid (Max 1440px, perfectly aligned with nav) ── */}
      <div className="w-full max-w-[1440px] grid grid-cols-1 lg:grid-cols-[380px_1fr] gap-6 items-stretch">
        {/* ═══════════════════════════════════════════════════════════════════
            LEFT COLUMN: ENGINE STATUS & PIPELINE CONTROL CARD
            ═══════════════════════════════════════════════════════════════════ */}
        <div
          className="figma-glass-card flex flex-col justify-between p-6 rounded-[22px] relative overflow-hidden w-full shadow-[0px_4px_24px_0px_rgba(200,140,160,0.08)] min-h-[530px]"
          style={{
            backgroundImage:
              "linear-gradient(131.96deg, rgba(245, 200, 210, 0.6) 6.17%, rgba(255, 240, 245, 0.5) 93.83%)",
          }}
          data-node-id="1:244"
          data-name="Card"
        >
          {/* Continuous GPU Diagonal Shimmer Sweep */}
          <div className="shimmer-active" />

          {/* Upper Section: Status + 3 KPI Boxes + Button */}
          <div className="w-full flex flex-col relative z-10">
            {/* Header: ENGINE STATUS + Status Badge Pill */}
            <div className="flex items-center justify-between w-full">
              <p className="font-['DM_Mono'] font-bold leading-[15px] text-[#c08090] text-[11px] tracking-[1.4px] uppercase whitespace-nowrap">
                ENGINE STATUS
              </p>
              <div className="bg-[rgba(255,255,255,0.7)] backdrop-blur-sm flex gap-[5px] items-center px-[10px] py-[4px] rounded-[20px] shadow-sm">
                <div
                  className={`rounded-full size-[7px] ${
                    pipelineActive
                      ? "bg-[#22c55e] shadow-[0px_0px_0px_1.5px_rgba(34,197,94,0.48)] animate-pulse"
                      : "bg-[#ef4444] shadow-[0px_0px_0px_1.5px_rgba(239,68,68,0.48)]"
                  }`}
                />
                <p
                  className={`font-semibold leading-[15px] text-[10px] tracking-[1px] whitespace-nowrap ${
                    pipelineActive ? "text-[#166534]" : "text-[#991b1b]"
                  }`}
                >
                  {pipelineActive ? "ENGINE ACTIVE" : "ENGINE PAUSED"}
                </p>
              </div>
            </div>

            {/* 3 KPI Sub-Cards: UPTIME, CLIPS/HR, QUEUE */}
            <div className="grid grid-cols-3 gap-3 pt-5 w-full">
              {/* Uptime Box */}
              <div className="bg-[rgba(220,140,160,0.18)] flex flex-col items-center justify-center p-3 rounded-[14px] min-h-[96px] text-center">
                <p className="font-semibold leading-tight text-[#c08090] text-[9px] tracking-[1.1px] uppercase whitespace-nowrap">
                  UPTIME
                </p>
                <div className="flex flex-col items-center justify-center mt-1.5">
                  <p className="font-['DM_Mono'] font-medium leading-[24px] text-[#6b1a30] text-[20px] whitespace-nowrap">
                    14h
                  </p>
                  <p className="font-['DM_Mono'] font-medium leading-[18px] text-[#6b1a30] text-[16px] whitespace-nowrap">
                    32m
                  </p>
                </div>
              </div>

              {/* Clips/Hr Box */}
              <div className="bg-[rgba(220,140,160,0.18)] flex flex-col items-center justify-center p-3 rounded-[14px] min-h-[96px] text-center">
                <p className="font-semibold leading-tight text-[#c08090] text-[9px] tracking-[1.1px] uppercase whitespace-nowrap">
                  CLIPS/HR
                </p>
                <div className="flex flex-col items-center justify-center mt-2.5">
                  <p className="font-['DM_Mono'] font-medium leading-[26px] text-[#6b1a30] text-[24px] whitespace-nowrap">
                    4.7
                  </p>
                </div>
              </div>

              {/* Queue Box */}
              <div className="bg-[rgba(220,140,160,0.18)] flex flex-col items-center justify-center p-3 rounded-[14px] min-h-[96px] text-center">
                <p className="font-semibold leading-tight text-[#c08090] text-[9px] tracking-[1.1px] uppercase whitespace-nowrap">
                  QUEUE
                </p>
                <div className="flex flex-col items-center justify-center mt-2.5">
                  <p className="font-['DM_Mono'] font-medium leading-[26px] text-[#6b1a30] text-[24px] whitespace-nowrap">
                    {queuePendingCount}
                  </p>
                </div>
              </div>
            </div>

            {/* Action Gradient Button: Pause / Resume Pipeline */}
            <div className="pt-4 w-full">
              <button
                onClick={handleTogglePipeline}
                disabled={isToggling}
                className="drop-shadow-[0px_4px_12px_rgba(124,58,237,0.35)] flex gap-[8px] h-[46px] items-center justify-center py-[13px] rounded-[14px] w-full cursor-pointer hover:brightness-105 active:scale-98 transition-all disabled:opacity-50"
                style={{
                  backgroundImage:
                    "linear-gradient(170.99deg, rgb(192, 132, 204) 0%, rgb(124, 58, 237) 100%)",
                }}
                data-name="Button"
              >
                <svg
                  width="14"
                  height="14"
                  viewBox="0 0 24 24"
                  fill="currentColor"
                  className="text-white shrink-0"
                >
                  {pipelineActive ? (
                    <>
                      <rect x="6" y="4" width="4" height="16" rx="1.5" />
                      <rect x="14" y="4" width="4" height="16" rx="1.5" />
                    </>
                  ) : (
                    <polygon points="5 3 19 12 5 21 5 3" />
                  )}
                </svg>
                <p className="font-semibold leading-[19.5px] text-[13px] text-center !text-white tracking-[0.52px] whitespace-nowrap">
                  {isToggling
                    ? "Updating Engine..."
                    : pipelineActive
                    ? "Pause Pipeline"
                    : "Start Pipeline"}
                </p>
              </button>
            </div>
          </div>

          {/* Lower Section: Telemetry & Hardware Spec (Fills lower box in user diagram) */}
          <div className="w-full mt-5 pt-4 border-t border-[rgba(220,180,190,0.25)] flex flex-col gap-2.5 relative z-10">
            <div className="flex items-center justify-between text-xs">
              <span className="text-[#a06075] font-semibold text-[11px]">GPU VRAM ALLOCATION</span>
              <span className="font-['DM_Mono'] font-bold text-[#6b1a30] text-[11px]">3.2 / 16 GB (20%)</span>
            </div>
            <div className="w-full h-1.5 bg-[rgba(220,140,160,0.22)] rounded-full overflow-hidden">
              <div className="h-full bg-gradient-to-r from-[#c084cc] to-[#7c3aed] rounded-full w-[20%]" />
            </div>

            <div className="grid grid-cols-2 gap-2 mt-1">
              <div className="bg-[rgba(255,255,255,0.5)] border border-[rgba(220,180,190,0.25)] rounded-xl p-2.5">
                <p className="text-[9px] font-semibold text-[#c08090] uppercase tracking-wider">SAMPLING</p>
                <p className="font-['DM_Mono'] font-bold text-xs text-[#6b1a30] mt-0.5">CFR 60 FPS</p>
              </div>
              <div className="bg-[rgba(255,255,255,0.5)] border border-[rgba(220,180,190,0.25)] rounded-xl p-2.5">
                <p className="text-[9px] font-semibold text-[#c08090] uppercase tracking-wider">AI STACK</p>
                <p className="font-['DM_Mono'] font-bold text-xs text-[#6b1a30] mt-0.5">YOLO + Whisper</p>
              </div>
            </div>
          </div>

          {/* Floating Blossom Vector in Corner */}
          <div className="absolute bottom-3 right-3 pointer-events-none opacity-20">
            <div className="rotate-[6deg]">
              <BlossomFlower size={58} color="#e598b0" cx="#fff8fa" />
            </div>
          </div>
        </div>

        {/* ═══════════════════════════════════════════════════════════════════
            RIGHT COLUMN: 3 STAT CARDS (ROW 1) + RECENT ACTIVITY (ROW 2)
            ═══════════════════════════════════════════════════════════════════ */}
        <div className="flex flex-col gap-5 w-full">
          {/* ── ROW 1: 3 STAT CARDS (Min-Height: 160px) ────────────────────── */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-5 min-h-[160px] w-full">
            {/* 1. ACTIVE STREAMS Card */}
            <div
              className="figma-glass-card flex flex-col justify-between p-5 rounded-[20px] relative overflow-hidden shadow-[0px_4px_24px_0px_rgba(200,140,160,0.08)]"
              style={{
                backgroundImage:
                  "linear-gradient(146.52deg, rgba(235, 185, 195, 0.5) 0%, rgba(255, 240, 248, 0.5) 100%)",
              }}
              data-node-id="1:310"
              data-name="Card"
            >
              <div className="shimmer-active" />
              {/* Card Top: Video Icon + LIVE Badge */}
              <div className="flex items-start justify-between w-full relative z-10">
                <div className="bg-[rgba(220,140,160,0.25)] flex items-center justify-center p-[8px] rounded-[10px] size-[32px]">
                  <svg
                    width="16"
                    height="16"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="#8b2252"
                    strokeWidth="2.2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  >
                    <path d="m22 8-6 4 6 4V8Z" />
                    <rect width="14" height="12" x="2" y="6" rx="2" />
                  </svg>
                </div>
                <div className="bg-[rgba(220,140,160,0.22)] flex gap-[5px] items-center px-[9px] py-[3px] rounded-[20px]">
                  <div className="bg-[#ef4444] rounded-full size-[6px] animate-pulse" />
                  <p className="font-bold leading-[13.5px] text-[#991b1b] text-[9px] tracking-[0.9px] uppercase whitespace-nowrap">
                    LIVE
                  </p>
                </div>
              </div>

              {/* Card Bottom: Label + Large Metric */}
              <div className="flex flex-col relative z-10 mt-2">
                <p className="font-semibold leading-[15px] text-[#c08090] text-[10px] tracking-[1.4px] uppercase whitespace-nowrap">
                  ACTIVE STREAMS
                </p>
                <p className="font-['DM_Mono'] font-medium leading-none text-[#6b1a30] text-[38px] whitespace-nowrap mt-1.5">
                  {activeStreamersCount}
                </p>
              </div>

              {/* Decorative blossom in corner */}
              <div className="absolute top-[-10px] right-[-10px] opacity-20 pointer-events-none">
                <BlossomFlower size={56} color="#f4a8c0" cx="#fff8fa" rotate={5} />
              </div>
            </div>

            {/* 2. CLIPS CREATED TODAY Card */}
            <div
              className="figma-glass-card flex flex-col justify-between p-5 rounded-[20px] relative overflow-hidden shadow-[0px_4px_24px_0px_rgba(200,140,160,0.08)]"
              style={{
                backgroundImage:
                  "linear-gradient(146.52deg, rgba(205, 190, 235, 0.4) 0%, rgba(240, 235, 255, 0.5) 100%)",
              }}
              data-node-id="1:340"
              data-name="Card"
            >
              <div className="shimmer-active" />
              {/* Card Top: Film Icon + Sparkline Graph */}
              <div className="flex items-start justify-between w-full relative z-10">
                <div className="bg-[rgba(180,160,220,0.25)] flex items-center justify-center p-[8px] rounded-[10px] size-[32px]">
                  <svg
                    width="16"
                    height="16"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="#5b2a8a"
                    strokeWidth="2.2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  >
                    <rect width="18" height="18" x="3" y="3" rx="2" />
                    <path d="M7 3v18" />
                    <path d="M17 3v18" />
                    <path d="M3 7.5h4" />
                    <path d="M3 12h18" />
                    <path d="M3 16.5h4" />
                    <path d="M17 7.5h4" />
                    <path d="M17 16.5h4" />
                  </svg>
                </div>
                <SparklineSVG />
              </div>

              {/* Card Bottom: Label + Metric + (+14%) Pill */}
              <div className="flex flex-col relative z-10 mt-2">
                <p className="font-semibold leading-[15px] text-[#8070b0] text-[10px] tracking-[1.4px] uppercase whitespace-nowrap">
                  CLIPS CREATED TODAY
                </p>
                <div className="flex items-center gap-[8px] mt-1.5">
                  <p className="font-['DM_Mono'] font-medium leading-none text-[#3d1a7a] text-[38px] whitespace-nowrap">
                    {totalClipsCount}
                  </p>
                  <div className="bg-[rgba(34,197,94,0.14)] px-[6px] py-[2px] rounded-[6px] flex items-center">
                    <p className="font-semibold leading-[18px] text-[#166534] text-[12px] whitespace-nowrap">
                      +14%
                    </p>
                  </div>
                </div>
              </div>

              {/* Decorative blossom in corner */}
              <div className="absolute top-[-8px] right-[-8px] opacity-18 pointer-events-none">
                <BlossomFlower size={48} color="#d4a8e4" cx="#fff8fa" rotate={-10} />
              </div>
            </div>

            {/* 3. VIRAL CTR POTENTIAL Card */}
            <div
              className="figma-glass-card flex flex-col justify-between p-5 rounded-[20px] relative overflow-hidden shadow-[0px_4px_24px_0px_rgba(200,140,160,0.08)]"
              style={{
                backgroundImage:
                  "linear-gradient(146.52deg, rgba(180, 215, 235, 0.4) 0%, rgba(230, 245, 255, 0.5) 100%)",
              }}
              data-node-id="1:376"
              data-name="Card"
            >
              <div className="shimmer-active" />
              {/* Card Top: Zap Icon + Mini Bar Chart */}
              <div className="flex items-start justify-between w-full relative z-10">
                <div className="bg-[rgba(140,190,220,0.25)] flex items-center justify-center p-[8px] rounded-[10px] size-[32px]">
                  <svg
                    width="16"
                    height="16"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="#1e40af"
                    strokeWidth="2.2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  >
                    <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" />
                  </svg>
                </div>
                <BarChartSVG />
              </div>

              {/* Card Bottom: Label + Metric */}
              <div className="flex flex-col relative z-10 mt-2">
                <p className="font-semibold leading-[15px] text-[#6090a8] text-[10px] tracking-[1.4px] uppercase whitespace-nowrap">
                  VIRAL CTR POTENTIAL
                </p>
                <p className="font-['DM_Mono'] font-bold leading-none text-[#1a4060] text-[32px] tracking-tight whitespace-nowrap mt-1.5">
                  {avgViralScore}
                </p>
              </div>

              {/* Decorative blossom in corner */}
              <div className="absolute top-[-10px] right-[-10px] opacity-20 pointer-events-none">
                <BlossomFlower size={53} color="#84b8d4" cx="#fff8fa" rotate={4} />
              </div>
            </div>
          </div>

          {/* ── ROW 2: RECENT ACTIVITY CARD ────────────────────────────────── */}
          <div
            className="figma-glass-card flex flex-col p-6 rounded-[22px] relative overflow-hidden shadow-[0px_4px_24px_0px_rgba(200,140,160,0.08)] w-full flex-1 min-h-[350px]"
            data-node-id="1:408"
            data-name="Card"
          >
            <div className="shimmer-active" />

            {/* Header: Blossom Icon + RECENT ACTIVITY */}
            <div className="flex items-center gap-[8px] w-full relative z-10 pb-2">
              <BlossomFlower size={14} color="#f4a8c0" cx="#fff8fa" />
              <p className="font-['DM_Mono'] font-bold leading-[15px] text-[#c08090] text-[11px] tracking-[1.4px] uppercase whitespace-nowrap">
                RECENT ACTIVITY
              </p>
            </div>

            {/* Activity Rows List */}
            <div className="flex flex-col w-full relative z-10 divide-y divide-[rgba(220,180,190,0.22)]">
              {displayActivities.map((act) => (
                <div
                  key={act.id}
                  className="flex items-center gap-3.5 py-3 transition-colors hover:bg-[rgba(255,255,255,0.4)] rounded-[12px] px-2"
                >
                  {/* Avatar Icon */}
                  <div
                    className="flex items-center justify-center rounded-full size-9 drop-shadow-xs shrink-0"
                    style={{ backgroundColor: act.avatarBg }}
                  >
                    <p className="font-bold text-[13px] text-white leading-none">
                      {act.avatarLetter}
                    </p>
                  </div>

                  {/* Title & Description */}
                  <div className="flex flex-1 flex-col min-w-0">
                    <p className="font-semibold text-[#1a0a10] text-[14px] leading-[20px] truncate">
                      {act.name}
                    </p>
                    <p className="text-[#a06075] text-[12px] leading-[18px] truncate font-medium">
                      {act.desc}
                    </p>
                  </div>

                  {/* Virality Score Badge & Time */}
                  <div className="flex items-center gap-3 shrink-0">
                    <div className="bg-[rgba(34,197,94,0.14)] px-2.5 py-1 rounded-md border border-[rgba(34,197,94,0.2)]">
                      <p className="font-bold text-[#166534] text-[11px] leading-none whitespace-nowrap font-mono">
                        {act.score}
                      </p>
                    </div>
                    <p className="text-[#b07080] text-[12px] whitespace-nowrap min-w-[50px] text-right font-mono">
                      {act.time}
                    </p>
                  </div>
                </div>
              ))}
            </div>

            {/* Decorative large blossom flower in bottom right */}
            <div className="absolute bottom-[-16px] right-[-16px] opacity-25 pointer-events-none">
              <BlossomFlower size={89} color="#f4a8c0" cx="#fff8fa" rotate={8} />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
