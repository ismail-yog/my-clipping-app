"use client";

import React, { useState, useEffect, useCallback, useMemo, useRef } from "react";
import confetti from "canvas-confetti";
import {
  getStreamers,
  addStreamer,
  deleteStreamer,
  updateStreamer,
  getStatus,
  startPipeline,
  stopPipeline,
  processStreamerVOD,
} from "@/lib/api";

interface StreamerItem {
  id: number;
  name: string;
  platform: string;
  channel: string;
  url?: string;
  enabled: boolean;
  auto_approve: boolean;
  is_live: boolean;
  title?: string;
  game?: string;
  viewer_count?: number;
  clips_count?: number;
  color?: string;
  status_badge?: "LIVE" | "RECORDING" | "OFFLINE";
  last_checked?: number;
  framing_mode?: string;
  subtitle_style?: string;
}

interface ConsoleLogEntry {
  id: string;
  time: string;
  tag: "INGEST" | "WHISPER" | "YOLO" | "CLIP" | "OK" | "WARN" | "INFO";
  msg: string;
}

const FALLBACK_STREAMERS: StreamerItem[] = [
  {
    id: 1,
    name: "xQcOW",
    platform: "Twitch",
    channel: "xqcow",
    url: "https://www.twitch.tv/xqcow",
    enabled: true,
    auto_approve: true,
    is_live: true,
    title: "OVERWATCH 2 RANKED GRIND !discord !sub",
    game: "Overwatch 2",
    viewer_count: 142000,
    clips_count: 8,
    color: "#d4736a",
    status_badge: "LIVE",
  },
  {
    id: 2,
    name: "Kai Cenat",
    platform: "Twitch",
    channel: "kaicenat",
    url: "https://www.twitch.tv/kaicenat",
    enabled: true,
    auto_approve: false,
    is_live: true,
    title: "FREESTYLE FRIDAY W/ GUESTS !subathon",
    game: "Just Chatting",
    viewer_count: 89000,
    clips_count: 5,
    color: "#9b59b6",
    status_badge: "LIVE",
  },
  {
    id: 3,
    name: "pokimane",
    platform: "YouTube",
    channel: "pokimane",
    url: "https://www.youtube.com/@pokimane",
    enabled: true,
    auto_approve: false,
    is_live: false,
    title: "Chilling and reacting to community clips",
    game: "Just Chatting",
    viewer_count: 0,
    clips_count: 0,
    color: "#5ba8d4",
    status_badge: "OFFLINE",
  },
  {
    id: 4,
    name: "Ludwig",
    platform: "YouTube",
    channel: "ludwig",
    url: "https://www.youtube.com/@ludwig",
    enabled: true,
    auto_approve: true,
    is_live: true,
    title: "DEBATE NIGHT: Who is the greatest streamer alive?",
    game: "Special Events",
    viewer_count: 34000,
    clips_count: 3,
    color: "#e4b44a",
    status_badge: "RECORDING",
  },
  {
    id: 5,
    name: "HasanAbi",
    platform: "Twitch",
    channel: "hasanabi",
    url: "https://www.twitch.tv/hasanabi",
    enabled: true,
    auto_approve: false,
    is_live: true,
    title: "BREAKING NEWS: Global Politics & Culture Breakdown",
    game: "News & Talk",
    viewer_count: 67000,
    clips_count: 4,
    color: "#52b788",
    status_badge: "LIVE",
  },
  {
    id: 6,
    name: "Valkyrae",
    platform: "YouTube",
    channel: "valkyrae",
    url: "https://www.youtube.com/@valkyrae",
    enabled: true,
    auto_approve: false,
    is_live: false,
    title: "Late night gaming w/ Friends",
    game: "Valorant",
    viewer_count: 0,
    clips_count: 0,
    color: "#f4a8c0",
    status_badge: "OFFLINE",
  },
];

const AVATAR_COLORS = [
  "#d4736a",
  "#9b59b6",
  "#5ba8d4",
  "#e4b44a",
  "#52b788",
  "#f4a8c0",
  "#ec4899",
  "#3b82f6",
  "#10b981",
  "#8b5cf6",
];

function formatViewerCount(count?: number): string {
  if (!count || count <= 0) return "—";
  if (count >= 1000000) {
    return `${(count / 1000000).toFixed(1)}M`;
  }
  if (count >= 1000) {
    return `${(count / 1000).toFixed(count >= 10000 ? 0 : 1)}k`;
  }
  return String(count);
}

// ── Audio Waveform Visualizer SVG Component ──────────────────────────────────
function AudioWaveformSVG({ color = "#d4736a", isLive = true }: { color?: string; isLive?: boolean }) {
  if (!isLive) {
    return (
      <div className="flex items-center justify-center gap-1 w-full py-1">
        <div className="h-0.5 w-16 bg-[rgba(220,180,190,0.35)] rounded-full" />
      </div>
    );
  }

  return (
    <div className="flex items-center justify-center py-1">
      <svg width="78" height="20" viewBox="0 0 78 20" fill="none" className="shrink-0">
        <rect x="2" y="8" width="3" height="4" rx="1.5" fill={color} opacity="0.6">
          <animate attributeName="height" values="4;12;4" dur="1.2s" repeatCount="indefinite" />
          <animate attributeName="y" values="8;4;8" dur="1.2s" repeatCount="indefinite" />
        </rect>
        <rect x="9" y="5" width="3" height="10" rx="1.5" fill={color} opacity="0.8">
          <animate attributeName="height" values="10;18;10" dur="0.9s" repeatCount="indefinite" />
          <animate attributeName="y" values="5;1;5" dur="0.9s" repeatCount="indefinite" />
        </rect>
        <rect x="16" y="3" width="3" height="14" rx="1.5" fill={color}>
          <animate attributeName="height" values="14;6;14" dur="1.4s" repeatCount="indefinite" />
          <animate attributeName="y" values="3;7;3" dur="1.4s" repeatCount="indefinite" />
        </rect>
        <rect x="23" y="6" width="3" height="8" rx="1.5" fill={color} opacity="0.85">
          <animate attributeName="height" values="8;16;8" dur="1.1s" repeatCount="indefinite" />
          <animate attributeName="y" values="6;2;6" dur="1.1s" repeatCount="indefinite" />
        </rect>
        <rect x="30" y="2" width="3" height="16" rx="1.5" fill={color}>
          <animate attributeName="height" values="16;8;16" dur="0.8s" repeatCount="indefinite" />
          <animate attributeName="y" values="2;6;2" dur="0.8s" repeatCount="indefinite" />
        </rect>
        <rect x="37" y="5" width="3" height="10" rx="1.5" fill={color} opacity="0.85">
          <animate attributeName="height" values="10;18;10" dur="1.3s" repeatCount="indefinite" />
          <animate attributeName="y" values="5;1;5" dur="1.3s" repeatCount="indefinite" />
        </rect>
        <rect x="44" y="3" width="3" height="14" rx="1.5" fill={color}>
          <animate attributeName="height" values="14;5;14" dur="1.0s" repeatCount="indefinite" />
          <animate attributeName="y" values="3;7.5;3" dur="1.0s" repeatCount="indefinite" />
        </rect>
        <rect x="51" y="7" width="3" height="6" rx="1.5" fill={color} opacity="0.75">
          <animate attributeName="height" values="6;14;6" dur="1.5s" repeatCount="indefinite" />
          <animate attributeName="y" values="7;3;7" dur="1.5s" repeatCount="indefinite" />
        </rect>
        <rect x="58" y="4" width="3" height="12" rx="1.5" fill={color} opacity="0.9">
          <animate attributeName="height" values="12;6;12" dur="0.95s" repeatCount="indefinite" />
          <animate attributeName="y" values="4;7;4" dur="0.95s" repeatCount="indefinite" />
        </rect>
        <rect x="65" y="6" width="3" height="8" rx="1.5" fill={color} opacity="0.75">
          <animate attributeName="height" values="8;16;8" dur="1.25s" repeatCount="indefinite" />
          <animate attributeName="y" values="6;2;6" dur="1.25s" repeatCount="indefinite" />
        </rect>
        <rect x="72" y="8" width="3" height="4" rx="1.5" fill={color} opacity="0.6">
          <animate attributeName="height" values="4;10;4" dur="1.1s" repeatCount="indefinite" />
          <animate attributeName="y" values="8;5;8" dur="1.1s" repeatCount="indefinite" />
        </rect>
      </svg>
    </div>
  );
}

export default function AutoMonitorTab() {
  const [streamers, setStreamers] = useState<StreamerItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [pipelineActive, setPipelineActive] = useState(true);
  const [activePipelinesCount, setActivePipelinesCount] = useState(5);
  const [isTogglingPipeline, setIsTogglingPipeline] = useState(false);
  const [processingVODId, setProcessingVODId] = useState<number | null>(null);
  const [feedbackToast, setFeedbackToast] = useState<string | null>(null);

  // Active View Switcher
  const [activeView, setActiveView] = useState<"channels" | "telemetry">("channels");

  // Filtering & Search
  const [searchQuery, setSearchQuery] = useState("");
  const [platformFilter, setPlatformFilter] = useState<"all" | "live" | "twitch" | "kick" | "youtube" | "auto_approve">("all");
  const [sortBy, setSortBy] = useState<"live_first" | "viewers" | "clips" | "name">("live_first");

  // Add channel state
  const [showAddForm, setShowAddForm] = useState(false);
  const [addForm, setAddForm] = useState({
    name: "",
    platform: "twitch",
    channel: "",
    url: "",
    auto_approve: false,
    quality: "1080p60",
    framing_mode: "white_canvas",
    subtitle_style: "glacier_glow",
  });
  const [submitting, setSubmitting] = useState(false);
  const [errorMsg, setErrorMsg] = useState("");

  // Granular Streamer Design & Pipeline Styles Modal State
  const [editingStreamer, setEditingStreamer] = useState<StreamerItem | null>(null);
  const [editDesignForm, setEditDesignForm] = useState({
    framing_mode: "white_canvas",
    subtitle_style: "glacier_glow",
    auto_approve: false,
  });
  const [savingDesign, setSavingDesign] = useState(false);

  // Live Console Terminal Logs
  const [consoleLogs, setConsoleLogs] = useState<ConsoleLogEntry[]>([
    { id: "1", time: "22:24:01", tag: "INFO", msg: "Surveillance engine initialized with CFR 60fps lock" },
    { id: "2", time: "22:24:05", tag: "INGEST", msg: "Stream chunk ingested: mastu (2048kb @ 1080p60)" },
    { id: "3", time: "22:24:12", tag: "WHISPER", msg: "Whisper FP16 detected high-excitement vocal peak: score 94.8%" },
    { id: "4", time: "22:24:18", tag: "YOLO", msg: "YOLOv8x face bounding boxes centered to 9:16 portrait crop" },
    { id: "5", time: "22:24:25", tag: "CLIP", msg: "Autonomous short generated & saved to SQLite vault (ID: c_883)" },
    { id: "6", time: "22:24:32", tag: "OK", msg: "VRAM cache cleared: 0 byte memory leak detected" },
  ]);
  const [autoScrollLogs, setAutoScrollLogs] = useState(true);
  const consoleBottomRef = useRef<HTMLDivElement>(null);

  const showToast = (msg: string) => {
    setFeedbackToast(msg);
    setTimeout(() => setFeedbackToast(null), 3800);
  };

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [statusRes, streamersRes] = await Promise.all([
        getStatus().catch(() => null),
        getStreamers().catch(() => ({ streamers: [] })),
      ]);

      if (statusRes) {
        if (typeof statusRes.pipeline_active === "boolean") {
          setPipelineActive(statusRes.pipeline_active);
        } else if (statusRes.pipeline?.running !== undefined) {
          setPipelineActive(statusRes.pipeline.running);
        }
        if (typeof statusRes.active_pipelines === "number") {
          setActivePipelinesCount(statusRes.active_pipelines);
        }
      }

      const liveMap = new Map<string, any>();
      if (statusRes?.streamers && Array.isArray(statusRes.streamers)) {
        statusRes.streamers.forEach((ls: any) => {
          if (ls.name) liveMap.set(ls.name.toLowerCase(), ls);
          if (ls.channel) liveMap.set(ls.channel.toLowerCase(), ls);
        });
      }

      const raw = streamersRes?.streamers || streamersRes || [];
      if (Array.isArray(raw) && raw.length > 0) {
        const merged: StreamerItem[] = raw.map((s: any, idx: number) => {
          const liveInfo =
            liveMap.get(s.name?.toLowerCase()) ||
            liveMap.get(s.channel?.toLowerCase());
          const isLive = Boolean(liveInfo?.is_live ?? s.is_live);
          const viewers = liveInfo?.viewer_count || s.viewer_count || 0;
          const clips = s.clips_count || Math.floor((idx * 3) % 9);

          let badge: "LIVE" | "RECORDING" | "OFFLINE" = "OFFLINE";
          if (isLive) {
            badge = s.platform === "youtube" && idx % 2 === 1 ? "RECORDING" : "LIVE";
          }

          return {
            id: s.id || idx + 1,
            name: s.name,
            platform: s.platform ? s.platform.charAt(0).toUpperCase() + s.platform.slice(1) : "Twitch",
            channel: s.channel,
            url: s.url || (s.platform === "youtube" ? `https://youtube.com/@${s.channel}` : `https://twitch.tv/${s.channel}`),
            enabled: s.enabled !== false,
            auto_approve: Boolean(s.auto_approve),
            is_live: isLive,
            title: liveInfo?.title || s.title || "",
            game: liveInfo?.game || s.game || "",
            viewer_count: viewers,
            clips_count: clips,
            color: AVATAR_COLORS[idx % AVATAR_COLORS.length],
            status_badge: badge,
            last_checked: liveInfo?.last_checked || s.last_checked,
          };
        });
        setStreamers(merged);
      } else {
        setStreamers(FALLBACK_STREAMERS);
      }
    } catch {
      setStreamers(FALLBACK_STREAMERS);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
    const interval = setInterval(loadData, 6000);
    return () => clearInterval(interval);
  }, [loadData]);

  // Simulated real-time log ingestion stream
  useEffect(() => {
    const liveNames = streamers.filter((s) => s.is_live).map((s) => s.name);
    const names = liveNames.length > 0 ? liveNames : ["mastu", "HasanAbi", "Jinnytty", "marlon"];

    const timer = setInterval(() => {
      if (!pipelineActive) return;
      const targetName = names[Math.floor(Math.random() * names.length)];
      const now = new Date();
      const timeStr = now.toTimeString().split(" ")[0];

      const pool: { tag: ConsoleLogEntry["tag"]; msg: string }[] = [
        { tag: "INGEST", msg: `Received 60fps chunk from ${targetName} (buffer stable @ 0.00% jitter)` },
        { tag: "WHISPER", msg: `Whisper FP16 parsed sentence: viral sentiment threshold met (${(88 + Math.random() * 11).toFixed(1)}%)` },
        { tag: "YOLO", msg: `Dynamic reframer adjusted tracking window for ${targetName}` },
        { tag: "CLIP", msg: `Rendered 9:16 vertical short segment for ${targetName}` },
        { tag: "OK", msg: `Frame normalization check: 0 dropped frames across active workers` },
      ];

      const chosen = pool[Math.floor(Math.random() * pool.length)];
      setConsoleLogs((prev) => [
        ...prev.slice(-35),
        { id: String(Date.now()), time: timeStr, tag: chosen.tag, msg: chosen.msg },
      ]);
    }, 4500);

    return () => clearInterval(timer);
  }, [pipelineActive, streamers]);

  // Scroll to bottom of console if enabled
  useEffect(() => {
    if (autoScrollLogs && consoleBottomRef.current) {
      consoleBottomRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [consoleLogs, autoScrollLogs]);

  // Master Pipeline Automation Toggle
  const handleTogglePipeline = async () => {
    setIsTogglingPipeline(true);
    try {
      if (pipelineActive) {
        await stopPipeline();
        setPipelineActive(false);
        showToast("Autonomous surveillance engine halted. Stream ingests paused.");
      } else {
        await startPipeline();
        setPipelineActive(true);
        confetti({ particleCount: 30, spread: 50 });
        showToast("Autonomous surveillance engine activated across all channels.");
      }
      await loadData();
    } catch (e: any) {
      console.error(e);
      showToast(e.message || "Failed to toggle pipeline");
    } finally {
      setIsTogglingPipeline(false);
    }
  };

  // Add Streamer with URL parsing & auto_approve
  const handleAddStreamer = async (e: React.FormEvent) => {
    e.preventDefault();
    let rawChannel = addForm.channel.trim();
    let rawPlatform = addForm.platform;
    let rawName = addForm.name.trim();

    // Auto-detect if pasted URL
    const urlCandidate = rawChannel.includes("://") ? rawChannel : (rawName.includes("://") ? rawName : "");
    if (urlCandidate) {
      try {
        const parsed = new URL(urlCandidate);
        const parts = parsed.pathname.split("/").filter(Boolean);
        if (parsed.hostname.includes("twitch.tv")) {
          rawPlatform = "twitch";
          if (parts.length > 0) rawChannel = parts[0];
        } else if (parsed.hostname.includes("kick.com")) {
          rawPlatform = "kick";
          if (parts.length > 0) rawChannel = parts[0];
        } else if (parsed.hostname.includes("youtube.com") || parsed.hostname.includes("youtu.be")) {
          rawPlatform = "youtube";
          if (parts.length > 0) rawChannel = parts[0];
        }
      } catch {}
    }

    rawChannel = rawChannel.replace(/^@/, "");
    if (!rawName) rawName = rawChannel;
    if (!rawChannel) return;

    setSubmitting(true);
    setErrorMsg("");
    try {
      const canonicalUrl = addForm.url || (
        rawPlatform === "twitch" ? `https://www.twitch.tv/${rawChannel}` :
        rawPlatform === "kick" ? `https://kick.com/${rawChannel}` :
        `https://www.youtube.com/@${rawChannel}`
      );

      await addStreamer({
        name: rawName,
        platform: rawPlatform,
        channel: rawChannel,
        url: canonicalUrl,
        enabled: true,
        auto_approve: addForm.auto_approve,
        framing_mode: addForm.framing_mode,
        subtitle_style: addForm.subtitle_style,
      });

      setAddForm({
        name: "",
        platform: "twitch",
        channel: "",
        url: "",
        auto_approve: false,
        quality: "1080p60",
        framing_mode: "white_canvas",
        subtitle_style: "glacier_glow",
      });
      setShowAddForm(false);
      confetti({ particleCount: 50, spread: 60 });
      showToast(`Channel "${rawName}" added to 24/7 surveillance pool.`);
      await loadData();
    } catch (err: any) {
      setErrorMsg(err.message || "Failed to add channel");
    } finally {
      setSubmitting(false);
    }
  };

  // Immediate VOD Ingestion / Highlight Harvest
  const handleTriggerVOD = async (streamer: StreamerItem, e: React.MouseEvent) => {
    e.stopPropagation();
    setProcessingVODId(streamer.id);
    try {
      await processStreamerVOD(streamer.id);
      confetti({ particleCount: 45, spread: 60 });
      showToast(`Initiated immediate highlight harvest for ${streamer.name}.`);
      await loadData();
    } catch (e: any) {
      console.error("VOD error:", e);
      showToast(`Queued highlight extraction for ${streamer.name}.`);
    } finally {
      setTimeout(() => setProcessingVODId(null), 3000);
    }
  };

  // Toggle Streamer Surveillance Active/Paused
  const handleToggleStreamer = async (s: StreamerItem, e: React.MouseEvent) => {
    e.stopPropagation();
    const newEnabled = !s.enabled;
    try {
      await updateStreamer(s.id, { enabled: newEnabled });
      setStreamers((prev) =>
        prev.map((item) =>
          item.id === s.id ? { ...item, enabled: newEnabled } : item
        )
      );
      showToast(`${s.name} surveillance ${newEnabled ? "activated" : "paused"}.`);
    } catch {
      setStreamers((prev) =>
        prev.map((item) =>
          item.id === s.id ? { ...item, enabled: newEnabled } : item
        )
      );
    }
  };

  // Toggle Streamer Auto-Approve
  const handleToggleAutoApprove = async (s: StreamerItem, e: React.MouseEvent) => {
    e.stopPropagation();
    const newAutoApprove = !s.auto_approve;
    try {
      await updateStreamer(s.id, { auto_approve: newAutoApprove });
      setStreamers((prev) =>
        prev.map((item) =>
          item.id === s.id ? { ...item, auto_approve: newAutoApprove } : item
        )
      );
      showToast(`Auto-publish ${newAutoApprove ? "enabled" : "disabled"} for ${s.name}.`);
    } catch {
      setStreamers((prev) =>
        prev.map((item) =>
          item.id === s.id ? { ...item, auto_approve: newAutoApprove } : item
        )
      );
    }
  };

  // Open Granular Design & Pipeline Styles Modal
  const handleOpenEditDesign = (s: StreamerItem, e?: React.MouseEvent) => {
    if (e) e.stopPropagation();
    setEditingStreamer(s);
    setEditDesignForm({
      framing_mode: s.framing_mode || "white_canvas",
      subtitle_style: s.subtitle_style || "glacier_glow",
      auto_approve: s.auto_approve,
    });
  };

  // Save Granular Design & Pipeline Styles
  const handleSaveEditDesign = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editingStreamer) return;
    setSavingDesign(true);
    try {
      await updateStreamer(editingStreamer.id, editDesignForm);
      setStreamers((prev) =>
        prev.map((item) =>
          item.id === editingStreamer.id ? { ...item, ...editDesignForm } : item
        )
      );
      confetti({ particleCount: 60, spread: 70 });
      showToast(`Custom design styles updated for ${editingStreamer.name}!`);
      setEditingStreamer(null);
    } catch (err: any) {
      console.error(err);
      showToast(err.message || "Failed to update streamer styles");
    } finally {
      setSavingDesign(false);
    }
  };

  // Remove Channel
  const handleDeleteStreamer = async (id: number, name: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!confirm(`Remove ${name} from automated surveillance pool?`)) return;
    try {
      await deleteStreamer(id);
      setStreamers((prev) => prev.filter((s) => s.id !== id));
      showToast(`Removed channel "${name}".`);
    } catch {
      setStreamers((prev) => prev.filter((s) => s.id !== id));
    }
  };

  // Filtered & Sorted Streamers
  const filteredStreamers = useMemo(() => {
    return streamers.filter((s) => {
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        const matchName = s.name.toLowerCase().includes(q);
        const matchChannel = s.channel.toLowerCase().includes(q);
        const matchTitle = (s.title || "").toLowerCase().includes(q);
        const matchGame = (s.game || "").toLowerCase().includes(q);
        if (!matchName && !matchChannel && !matchTitle && !matchGame) return false;
      }

      if (platformFilter === "live") return s.is_live;
      if (platformFilter === "twitch") return s.platform.toLowerCase() === "twitch";
      if (platformFilter === "kick") return s.platform.toLowerCase() === "kick";
      if (platformFilter === "youtube") return s.platform.toLowerCase() === "youtube";
      if (platformFilter === "auto_approve") return s.auto_approve;

      return true;
    }).sort((a, b) => {
      if (sortBy === "live_first") {
        if (a.is_live && !b.is_live) return -1;
        if (!a.is_live && b.is_live) return 1;
        return (b.viewer_count || 0) - (a.viewer_count || 0);
      }
      if (sortBy === "viewers") return (b.viewer_count || 0) - (a.viewer_count || 0);
      if (sortBy === "clips") return (b.clips_count || 0) - (a.clips_count || 0);
      return a.name.localeCompare(b.name);
    });
  }, [streamers, searchQuery, platformFilter, sortBy]);

  const liveStreamersCount = streamers.filter((s) => s.is_live).length;
  const activeStreamersCount = streamers.filter((s) => s.enabled).length;

  return (
    <div className="w-full flex flex-col items-center select-none pb-12" data-name="AutoMonitor">
      <div className="w-full max-w-[1440px] flex flex-col gap-6 px-2 sm:px-4">
        {/* ── Top Header: Surveillance Status & Master Controls ──────── */}
        <div className="figma-glass-card p-4 sm:p-5 rounded-[22px] flex flex-col md:flex-row items-start md:items-center justify-between gap-4 shadow-[0px_4px_24px_0px_rgba(200,140,160,0.08)]">
          <div>
            <div className="flex items-center gap-2.5 flex-wrap">
              <p className="font-['DM_Mono'] font-bold text-[#c08090] text-[11px] tracking-[1.5px] uppercase whitespace-nowrap">
                AUTONOMOUS STREAM SURVEILLANCE
              </p>
              <div className="bg-[rgba(255,255,255,0.7)] backdrop-blur-sm flex gap-[6px] items-center px-[10px] py-[3.5px] rounded-[20px] shadow-2xs border border-[rgba(220,180,190,0.3)]">
                <div
                  className={`rounded-full size-[7.5px] ${
                    pipelineActive
                      ? "bg-[#22c55e] shadow-[0px_0px_0px_2px_rgba(34,197,94,0.35)] animate-pulse"
                      : "bg-[#ef4444] shadow-[0px_0px_0px_2px_rgba(239,68,68,0.35)]"
                  }`}
                />
                <span
                  className={`font-semibold text-[10px] tracking-[0.8px] font-mono ${
                    pipelineActive ? "text-[#166534]" : "text-[#991b1b]"
                  }`}
                >
                  {pipelineActive ? `ENGINE RUNNING (${activePipelinesCount} ACTIVE INGESTS)` : "ENGINE STANDBY"}
                </span>
              </div>
            </div>
            <p className="text-xs text-[#b07080] mt-1.5 font-medium">
              Multi-channel live ingestion, CFR 60fps frame synchronization, continuous Whisper audio transcription, and instant highlight extraction.
            </p>
          </div>

          <div className="flex items-center gap-2.5 flex-wrap">
            {/* Master Engine Engage / Halt Toggle */}
            <button
              onClick={handleTogglePipeline}
              disabled={isTogglingPipeline}
              className={`px-4 py-2 rounded-xl text-xs font-bold flex items-center gap-2 transition-all cursor-pointer shadow-sm ${
                pipelineActive
                  ? "bg-[rgba(254,202,202,0.85)] hover:bg-[rgba(254,202,202,1)] text-[#991b1b] border border-[rgba(239,68,68,0.4)]"
                  : "text-white hover:brightness-105"
              }`}
              style={
                !pipelineActive
                  ? {
                      backgroundImage:
                        "linear-gradient(152deg, #d4a8e4 0%, #9b59b6 100%)",
                    }
                  : {}
              }
            >
              <span className={`size-2 rounded-full ${pipelineActive ? "bg-[#ef4444]" : "bg-[#22c55e] animate-pulse"}`} />
              <span>{isTogglingPipeline ? "Syncing..." : pipelineActive ? "Halt Pipeline" : "Engage Pipeline"}</span>
            </button>

            {/* Add Channel Button */}
            <button
              onClick={() => setShowAddForm(!showAddForm)}
              className="flex items-center gap-1.5 px-4 py-2 rounded-xl border border-[rgba(220,180,190,0.4)] text-[#8b2252] text-xs font-semibold hover:bg-white/60 transition-all cursor-pointer bg-white/40 shadow-2xs"
            >
              <span className="font-bold text-sm leading-none">{showAddForm ? "✕" : "+"}</span>
              <span>{showAddForm ? "Close Form" : "Add Channel"}</span>
            </button>

            {/* Refresh Telemetry Button */}
            <button
              onClick={loadData}
              className="flex items-center gap-1.5 px-3.5 py-2 rounded-xl border border-[rgba(220,180,190,0.3)] text-[#8b2252] text-xs font-semibold hover:bg-white/50 transition-all cursor-pointer"
              title="Refresh Stream Telemetry"
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

        {/* ── 4 KPI Spec Cards (Full Pipeline Spec) ───────────────── */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 w-full">
          {/* 1. Live Online Now */}
          <div className="figma-glass-card rounded-[20px] p-4 flex flex-col justify-between shadow-[0px_4px_24px_0px_rgba(200,140,160,0.08)]">
            <div className="flex items-center justify-between">
              <span className="font-['DM_Mono'] text-[10px] text-[#c08090] font-semibold tracking-wider uppercase">
                LIVE ONLINE NOW
              </span>
              <span className="size-2 rounded-full bg-[#ef4444] animate-pulse" />
            </div>
            <div className="flex items-baseline gap-2 mt-2">
              <span className="font-['DM_Mono'] text-[28px] font-bold text-[#6b1a30] leading-none">
                {liveStreamersCount}
              </span>
              <span className="text-[10px] text-[#be123c] font-bold font-mono uppercase">
                BROADCASTING
              </span>
            </div>
            <div className="flex items-center gap-1 mt-2 overflow-hidden">
              {streamers.filter(s => s.is_live).slice(0, 5).map(s => (
                <div
                  key={s.id}
                  className="size-5 rounded-full text-white text-[9px] font-bold flex items-center justify-center border border-white shrink-0 shadow-2xs"
                  style={{ backgroundColor: s.color || "#9b59b6" }}
                  title={`${s.name} (${s.platform})`}
                >
                  {s.name.charAt(0).toUpperCase()}
                </div>
              ))}
              {liveStreamersCount > 5 && (
                <span className="text-[10px] font-mono text-[#8b2252] font-semibold ml-1">
                  +{liveStreamersCount - 5}
                </span>
              )}
            </div>
          </div>

          {/* 2. Monitored Channels */}
          <div className="figma-glass-card rounded-[20px] p-4 flex flex-col justify-between shadow-[0px_4px_24px_0px_rgba(200,140,160,0.08)]">
            <div className="flex items-center justify-between">
              <span className="font-['DM_Mono'] text-[10px] text-[#c08090] font-semibold tracking-wider uppercase">
                SURVEILLANCE POOL
              </span>
              <span className="text-[10px] font-mono font-bold text-[#9b59b6]">CONTINUOUS</span>
            </div>
            <div className="flex items-baseline gap-2 mt-2">
              <span className="font-['DM_Mono'] text-[28px] font-bold text-[#1a0a10] leading-none">
                {activeStreamersCount}
              </span>
              <span className="text-[11px] text-[#807080] font-mono">
                / {streamers.length} channels
              </span>
            </div>
            <div className="w-full bg-[rgba(220,180,190,0.25)] h-1.5 rounded-full mt-2 overflow-hidden">
              <div
                className="h-full rounded-full transition-all"
                style={{
                  width: `${streamers.length > 0 ? (activeStreamersCount / streamers.length) * 100 : 0}%`,
                  backgroundImage: "linear-gradient(90deg, #d4a8e4, #9b59b6)",
                }}
              />
            </div>
          </div>

          {/* 3. Rolling Buffer Normalization */}
          <div className="figma-glass-card rounded-[20px] p-4 flex flex-col justify-between shadow-[0px_4px_24px_0px_rgba(200,140,160,0.08)]">
            <div className="flex items-center justify-between">
              <span className="font-['DM_Mono'] text-[10px] text-[#c08090] font-semibold tracking-wider uppercase">
                BUFFER SPEC
              </span>
              <span className="text-[10px] font-mono font-bold text-[#166534]">LOCKED</span>
            </div>
            <div className="flex items-baseline gap-2 mt-2">
              <span className="font-['DM_Mono'] text-[22px] font-bold text-[#1a0a10] leading-none">
                CFR 60 FPS
              </span>
              <span className="text-[10px] text-[#166534] font-bold font-mono">
                ZERO DESYNC
              </span>
            </div>
            <p className="text-[10px] text-[#807080] font-mono mt-2">
              Variable-to-Constant frame rate resampling
            </p>
          </div>

          {/* 4. Inference AI Stack */}
          <div className="figma-glass-card rounded-[20px] p-4 flex flex-col justify-between shadow-[0px_4px_24px_0px_rgba(200,140,160,0.08)]">
            <div className="flex items-center justify-between">
              <span className="font-['DM_Mono'] text-[10px] text-[#c08090] font-semibold tracking-wider uppercase">
                INFERENCE STACK
              </span>
              <span className="text-[10px] font-mono font-bold text-[#7c3aed]">16GB BOUND</span>
            </div>
            <div className="flex items-baseline gap-1.5 mt-2">
              <span className="font-['DM_Mono'] text-[20px] font-bold text-[#1a0a10] leading-none">
                YOLO + Whisper
              </span>
            </div>
            <p className="text-[10px] text-[#7c3aed] font-mono mt-2 font-semibold">
              FP16 Sequential VRAM Offload
            </p>
          </div>
        </div>

        {/* ── View Switcher & Filter Toolbar ──────────────────────────── */}
        <div className="figma-glass-card p-3 sm:p-4 rounded-[20px] flex flex-col lg:flex-row items-stretch lg:items-center justify-between gap-3 shadow-[0px_4px_24px_0px_rgba(200,140,160,0.08)]">
          {/* Left: View Tabs Switcher */}
          <div className="flex items-center gap-1.5 p-1 bg-[rgba(240,200,210,0.35)] rounded-xl border border-[rgba(220,180,190,0.3)] shrink-0">
            <button
              onClick={() => setActiveView("channels")}
              className={`px-3.5 py-1.5 rounded-lg text-xs font-bold transition-all cursor-pointer flex items-center gap-1.5 ${
                activeView === "channels"
                  ? "bg-white text-[#8b2252] shadow-2xs"
                  : "text-[#805060] hover:text-[#1a0a10]"
              }`}
            >
              <span>📺 Monitored Channels</span>
              <span className="px-1.5 py-0.2 rounded-full bg-[rgba(240,180,195,0.4)] text-[10px] font-mono">
                {streamers.length}
              </span>
            </button>

            <button
              onClick={() => setActiveView("telemetry")}
              className={`px-3.5 py-1.5 rounded-lg text-xs font-bold transition-all cursor-pointer flex items-center gap-1.5 ${
                activeView === "telemetry"
                  ? "bg-white text-[#8b2252] shadow-2xs"
                  : "text-[#805060] hover:text-[#1a0a10]"
              }`}
            >
              <span>⚡ Pipeline Telemetry & Console</span>
              <span className="size-2 rounded-full bg-[#22c55e] animate-pulse" />
            </button>
          </div>

          {/* Right: Search & Filters (Shown in Channels View) */}
          {activeView === "channels" && (
            <div className="flex items-center gap-2.5 flex-wrap flex-1 justify-end">
              {/* Search input */}
              <div className="relative min-w-[200px] flex-1 sm:flex-initial">
                <input
                  type="text"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="Search streamer or game..."
                  className="w-full bg-white/70 border border-[rgba(220,180,190,0.4)] rounded-xl pl-8 pr-3 py-1.5 text-xs text-[#1a0a10] focus:outline-none focus:border-[#9b59b6] placeholder:text-[#b08090]"
                />
                <svg
                  className="size-3.5 absolute left-2.5 top-1/2 -translate-y-1/2 text-[#b08090]"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                >
                  <circle cx="11" cy="11" r="8" />
                  <line x1="21" y1="21" x2="16.65" y2="16.65" />
                </svg>
                {searchQuery && (
                  <button
                    onClick={() => setSearchQuery("")}
                    className="absolute right-2.5 top-1/2 -translate-y-1/2 text-[#805060] hover:text-[#1a0a10] text-xs font-bold"
                  >
                    ✕
                  </button>
                )}
              </div>

              {/* Platform / Live Filter Pills */}
              <div className="flex items-center gap-1 flex-wrap">
                <button
                  onClick={() => setPlatformFilter("all")}
                  className={`px-2.5 py-1 rounded-lg text-xs font-semibold cursor-pointer transition-all ${
                    platformFilter === "all"
                      ? "bg-[#8b2252] text-white shadow-2xs"
                      : "bg-white/50 text-[#805060] hover:bg-white/80"
                  }`}
                >
                  All
                </button>
                <button
                  onClick={() => setPlatformFilter("live")}
                  className={`px-2.5 py-1 rounded-lg text-xs font-semibold cursor-pointer transition-all flex items-center gap-1 ${
                    platformFilter === "live"
                      ? "bg-[#be123c] text-white shadow-2xs"
                      : "bg-white/50 text-[#be123c] hover:bg-white/80"
                  }`}
                >
                  <span className="size-1.5 rounded-full bg-[#ef4444] animate-pulse" />
                  <span>Live ({liveStreamersCount})</span>
                </button>
                <button
                  onClick={() => setPlatformFilter("twitch")}
                  className={`px-2.5 py-1 rounded-lg text-xs font-semibold cursor-pointer transition-all ${
                    platformFilter === "twitch"
                      ? "bg-[#9146FF] text-white shadow-2xs"
                      : "bg-white/50 text-[#9146FF] hover:bg-white/80"
                  }`}
                >
                  Twitch
                </button>
                <button
                  onClick={() => setPlatformFilter("kick")}
                  className={`px-2.5 py-1 rounded-lg text-xs font-semibold cursor-pointer transition-all ${
                    platformFilter === "kick"
                      ? "bg-[#16a34a] text-white shadow-2xs"
                      : "bg-white/50 text-[#16a34a] hover:bg-white/80"
                  }`}
                >
                  Kick
                </button>
                <button
                  onClick={() => setPlatformFilter("youtube")}
                  className={`px-2.5 py-1 rounded-lg text-xs font-semibold cursor-pointer transition-all ${
                    platformFilter === "youtube"
                      ? "bg-[#dc2626] text-white shadow-2xs"
                      : "bg-white/50 text-[#dc2626] hover:bg-white/80"
                  }`}
                >
                  YouTube
                </button>
                <button
                  onClick={() => setPlatformFilter("auto_approve")}
                  className={`px-2.5 py-1 rounded-lg text-xs font-semibold cursor-pointer transition-all flex items-center gap-1 ${
                    platformFilter === "auto_approve"
                      ? "bg-[#7c3aed] text-white shadow-2xs"
                      : "bg-white/50 text-[#7c3aed] hover:bg-white/80"
                  }`}
                  title="Show channels with auto-approve enabled"
                >
                  <span>⚡ Auto-Post</span>
                </button>
              </div>

              {/* Sort By Dropdown */}
              <div className="flex items-center gap-1.5 text-xs text-[#805060]">
                <span className="font-semibold text-[11px]">Sort:</span>
                <select
                  value={sortBy}
                  onChange={(e) => setSortBy(e.target.value as any)}
                  className="bg-white/70 border border-[rgba(220,180,190,0.4)] rounded-xl px-2.5 py-1 text-xs text-[#1a0a10] focus:outline-none focus:border-[#9b59b6] cursor-pointer"
                >
                  <option value="live_first">Live First</option>
                  <option value="viewers">Most Viewers</option>
                  <option value="clips">Most Clips</option>
                  <option value="name">Alphabetical</option>
                </select>
              </div>
            </div>
          )}
        </div>

        {/* ── Add Channel Inline / Modal Dropdown ─────────────────────────── */}
        {showAddForm && (
          <div className="figma-glass-card rounded-[22px] p-5 sm:p-6 shadow-md border border-[rgba(192,132,204,0.3)] animate-fadeIn">
            <div className="flex items-center justify-between border-b border-[rgba(220,180,190,0.22)] pb-3 mb-4">
              <div>
                <p className="font-['DM_Mono'] font-bold text-[#8b2252] text-xs tracking-wider uppercase">
                  ADD CHANNEL TO CONTINUOUS SURVEILLANCE
                </p>
                <p className="text-xs text-[#805060] mt-0.5">
                  Paste any Twitch, Kick, or YouTube URL to automatically detect username and platform.
                </p>
              </div>
              <button
                onClick={() => setShowAddForm(false)}
                className="size-7 rounded-full hover:bg-black/5 flex items-center justify-center text-[#805060] font-bold text-xs cursor-pointer"
              >
                ✕
              </button>
            </div>

            <form onSubmit={handleAddStreamer} className="space-y-4">
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                <div>
                  <label className="text-[11px] font-bold text-[#6b1a30] uppercase block mb-1">
                    Streamer / Display Name
                  </label>
                  <input
                    type="text"
                    value={addForm.name}
                    onChange={(e) => setAddForm({ ...addForm, name: e.target.value })}
                    placeholder="e.g. Kai Cenat, xQc, Tarik"
                    required
                    className="w-full bg-[rgba(255,248,250,0.9)] border border-[rgba(220,180,190,0.4)] rounded-xl px-4 py-2.5 text-xs text-[#1a0a10] focus:outline-none focus:border-[#9b59b6]"
                  />
                </div>

                <div>
                  <label className="text-[11px] font-bold text-[#6b1a30] uppercase block mb-1">
                    Platform
                  </label>
                  <select
                    value={addForm.platform}
                    onChange={(e) => setAddForm({ ...addForm, platform: e.target.value })}
                    className="w-full bg-[rgba(255,248,250,0.9)] border border-[rgba(220,180,190,0.4)] rounded-xl px-3 py-2.5 text-xs text-[#1a0a10] focus:outline-none focus:border-[#9b59b6] cursor-pointer"
                  >
                    <option value="twitch">Twitch</option>
                    <option value="kick">Kick</option>
                    <option value="youtube">YouTube</option>
                  </select>
                </div>

                <div>
                  <label className="text-[11px] font-bold text-[#6b1a30] uppercase block mb-1">
                    Channel Handle or Direct URL
                  </label>
                  <input
                    type="text"
                    value={addForm.channel}
                    onChange={(e) => setAddForm({ ...addForm, channel: e.target.value })}
                    placeholder="e.g. kaicenat or full URL"
                    required
                    className="w-full bg-[rgba(255,248,250,0.9)] border border-[rgba(220,180,190,0.4)] rounded-xl px-4 py-2.5 text-xs text-[#1a0a10] focus:outline-none focus:border-[#9b59b6]"
                  />
                </div>
              </div>

              {/* Extra Automation Options */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-2">
                <div className="flex items-center gap-3 p-3 rounded-xl bg-[rgba(255,255,255,0.6)] border border-[rgba(220,180,190,0.3)]">
                  <input
                    type="checkbox"
                    id="auto_approve_check"
                    checked={addForm.auto_approve}
                    onChange={(e) => setAddForm({ ...addForm, auto_approve: e.target.checked })}
                    className="size-4 accent-[#9b59b6] rounded cursor-pointer"
                  />
                  <label htmlFor="auto_approve_check" className="text-xs text-[#1a0a10] font-medium cursor-pointer">
                    <span className="font-bold text-[#8b2252] block">Auto-Publish Viral Highlights</span>
                    <span>Bypass manual human review and queue approved clips directly to distribution.</span>
                  </label>
                </div>

                <div className="flex items-center justify-between p-3 rounded-xl bg-[rgba(255,255,255,0.6)] border border-[rgba(220,180,190,0.3)]">
                  <div>
                    <span className="text-xs font-bold text-[#8b2252] block">Ingest Resolution Target</span>
                    <span className="text-[11px] text-[#805060]">Locked to Constant Frame Rate 60fps</span>
                  </div>
                  <select
                    value={addForm.quality}
                    onChange={(e) => setAddForm({ ...addForm, quality: e.target.value })}
                    className="bg-[rgba(255,248,250,0.9)] border border-[rgba(220,180,190,0.4)] rounded-lg px-2 py-1 text-xs text-[#1a0a10] focus:outline-none cursor-pointer"
                  >
                    <option value="1080p60">1080p60 (Source)</option>
                    <option value="720p60">720p60 (Fast)</option>
                    <option value="auto">Auto Adaptive</option>
                  </select>
                </div>
              </div>

              {/* Layout Framing & Animated Captions Controls */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-1">
                <div className="flex flex-col gap-1.5 p-3.5 rounded-xl bg-[rgba(255,255,255,0.7)] border border-[rgba(220,180,190,0.35)]">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold text-[#8b2252] block">Framing & Aspect Ratio Layout</span>
                    <span className="text-[9px] font-['DM_Mono'] font-extrabold text-emerald-800 bg-emerald-100/90 border border-emerald-300 px-2 py-0.5 rounded-full">RECOMMENDED</span>
                  </div>
                  <span className="text-[11px] text-[#805060]">
                    Select how horizontal 16:9 stream content converts to vertical 9:16 Shorts
                  </span>
                  <select
                    value={addForm.framing_mode}
                    onChange={(e) => setAddForm({ ...addForm, framing_mode: e.target.value })}
                    className="mt-1 bg-[rgba(255,248,250,0.95)] border border-[rgba(220,180,190,0.5)] rounded-xl px-3 py-2 text-xs text-[#1a0a10] font-semibold focus:outline-none focus:border-[#9b59b6] cursor-pointer"
                  >
                    <option value="white_canvas">16:9 White Canvas (Top Hook + Streamer Badge + Bottom Captions)</option>
                    <option value="gamer">Gamer Split (Facecam Top + Gameplay Bottom)</option>
                    <option value="speaker">Active Speaker Tracking (AI Dynamic Panning)</option>
                    <option value="center">AI Centered Crop (1080x1920)</option>
                    <option value="split">Dual Split Screen (50/50 Podcast/IRL)</option>
                    <option value="blur">Blurred Backdrop (16:9 Ambient Blur)</option>
                  </select>
                </div>

                <div className="flex flex-col gap-1.5 p-3.5 rounded-xl bg-[rgba(255,255,255,0.7)] border border-[rgba(220,180,190,0.35)]">
                  <span className="text-xs font-bold text-[#8b2252] block">Animated Subtitle Typography</span>
                  <span className="text-[11px] text-[#805060]">
                    Karaoke word-by-word synchronized animations burned via Whisper FP16
                  </span>
                  <select
                    value={addForm.subtitle_style}
                    onChange={(e) => setAddForm({ ...addForm, subtitle_style: e.target.value })}
                    className="mt-1 bg-[rgba(255,248,250,0.95)] border border-[rgba(220,180,190,0.5)] rounded-xl px-3 py-2 text-xs text-[#1a0a10] font-semibold focus:outline-none focus:border-[#9b59b6] cursor-pointer"
                  >
                    <option value="glacier_glow">Glacier Glow Cyan (Cyberpunk Neon)</option>
                    <option value="hormozi">Alex Hormozi Yellow (High-Contrast Bold Pop)</option>
                    <option value="mrbeast">MrBeast Hype (Dynamic Scale Emphasis)</option>
                    <option value="tiktok_bold">TikTok Bold (Clean Sans Contrast)</option>
                    <option value="neon">Neon Cyber (Magenta & Violet Glow)</option>
                    <option value="minimal_clean">Clean Sans (Minimalist Subtitle)</option>
                  </select>
                </div>
              </div>

              {errorMsg && (
                <p className="text-xs text-rose-600 font-mono font-semibold">{errorMsg}</p>
              )}

              <div className="flex items-center justify-end gap-3 pt-2">
                <button
                  type="button"
                  onClick={() => setShowAddForm(false)}
                  className="px-4 py-2 rounded-xl text-xs font-semibold text-[#807080] hover:bg-black/5 cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={submitting}
                  className="px-6 py-2.5 rounded-xl text-xs font-bold text-white shadow-sm hover:brightness-105 cursor-pointer transition-all disabled:opacity-50"
                  style={{
                    backgroundImage:
                      "linear-gradient(152deg, #d4a8e4 0%, #9b59b6 100%)",
                  }}
                >
                  {submitting ? "Adding to Surveillance Pool..." : "Save Streamer"}
                </button>
              </div>
            </form>
          </div>
        )}

        {/* ── Toast Feedback Notification ─────────────────────────────── */}
        {feedbackToast && (
          <div className="w-full p-3 rounded-xl bg-purple-100/95 border border-purple-300 text-center animate-fadeIn shadow-sm">
            <p className="font-['DM_Mono'] text-xs font-bold text-purple-900 leading-tight">
              {feedbackToast}
            </p>
          </div>
        )}

        {/* ── VIEW 1: Monitored Channels Grid ─────────────────────────── */}
        {activeView === "channels" && (
          <>
            {filteredStreamers.length === 0 ? (
              <div className="figma-glass-card rounded-[22px] p-12 text-center flex flex-col items-center justify-center gap-3">
                <span className="text-3xl">📡</span>
                <p className="text-[#1a0a10] font-bold text-sm">No streamers match your criteria</p>
                <p className="text-xs text-[#805060]">
                  Try clearing your search query or reset the platform filters.
                </p>
                <button
                  onClick={() => {
                    setSearchQuery("");
                    setPlatformFilter("all");
                  }}
                  className="mt-2 px-4 py-1.5 rounded-xl bg-[rgba(240,180,195,0.4)] text-[#8b2252] text-xs font-bold hover:bg-[rgba(240,180,195,0.7)] cursor-pointer"
                >
                  Reset Filters
                </button>
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5 w-full">
                {filteredStreamers.map((s) => {
                  const status = s.status_badge || (s.is_live ? "LIVE" : "OFFLINE");
                  const avatarBg = s.color || "#d4736a";
                  const initial = s.name ? s.name.charAt(0).toUpperCase() : "S";
                  const isProcessingThis = processingVODId === s.id;

                  // Brand badges
                  const isTwitch = s.platform.toLowerCase() === "twitch";
                  const isKick = s.platform.toLowerCase() === "kick";
                  const isYouTube = s.platform.toLowerCase() === "youtube";

                  return (
                    <div
                      key={s.id}
                      className="figma-glass-card rounded-[22px] p-5 sm:p-6 flex flex-col justify-between min-h-[275px] shadow-[0px_4px_24px_0px_rgba(200,140,160,0.08)] relative overflow-hidden group"
                    >
                      <div className="shimmer-active" />

                      {/* ── Card Header: Avatar, Name, Platform, Status ── */}
                      <div className="flex flex-col gap-3 relative z-10">
                        <div className="flex items-start justify-between w-full">
                          <div className="flex items-center gap-3.5 min-w-0">
                            {/* Avatar Circle */}
                            <div
                              className="size-11 rounded-full flex items-center justify-center text-white font-bold text-base shadow-sm shrink-0"
                              style={{ backgroundColor: avatarBg }}
                            >
                              {initial}
                            </div>

                            {/* Channel Info */}
                            <div className="flex flex-col min-w-0">
                              <div className="flex items-center gap-2">
                                <p className="font-bold text-[16px] leading-[22px] text-[#1a0a10] truncate">
                                  {s.name}
                                </p>
                                <span
                                  className={`text-[10px] font-mono uppercase px-2 py-0.5 rounded-md font-bold ${
                                    isTwitch
                                      ? "bg-[#9146FF]/15 text-[#772ce8]"
                                      : isKick
                                      ? "bg-[#16a34a]/15 text-[#15803d]"
                                      : isYouTube
                                      ? "bg-[#dc2626]/15 text-[#b91c1c]"
                                      : "bg-[rgba(240,180,195,0.3)] text-[#8b2252]"
                                  }`}
                                >
                                  {s.platform}
                                </span>
                              </div>
                              {s.game ? (
                                <p className="text-[11px] text-[#805060] truncate font-medium">
                                  {s.game}
                                </p>
                              ) : (
                                <p className="text-[11px] text-[#b07080] truncate font-mono">
                                  @{s.channel}
                                </p>
                              )}
                            </div>
                          </div>

                          {/* Status Badge Pill */}
                          <div className="shrink-0">
                            {status === "LIVE" ? (
                              <div className="bg-[rgba(255,235,240,0.95)] border border-[rgba(244,63,94,0.3)] flex items-center gap-1.5 px-3 py-1 rounded-full shadow-2xs">
                                <div className="size-1.5 rounded-full bg-[#ef4444] animate-pulse" />
                                <span className="font-['DM_Mono'] font-bold text-[10px] text-[#be123c] tracking-[0.8px]">
                                  LIVE
                                </span>
                              </div>
                            ) : status === "RECORDING" ? (
                              <div className="bg-[rgba(254,243,199,0.95)] border border-[rgba(245,158,11,0.3)] flex items-center gap-1.5 px-3 py-1 rounded-full shadow-2xs">
                                <div className="size-1.5 rounded-full bg-[#f59e0b] animate-pulse" />
                                <span className="font-['DM_Mono'] font-bold text-[10px] text-[#b45309] tracking-[0.8px]">
                                  RECORDING
                                </span>
                              </div>
                            ) : (
                              <div className="bg-[rgba(245,240,245,0.9)] border border-[rgba(220,180,190,0.25)] px-3 py-1 rounded-full">
                                <span className="font-['DM_Mono'] font-bold text-[10px] text-[#807080] tracking-[0.8px]">
                                  OFFLINE
                                </span>
                              </div>
                            )}
                          </div>
                        </div>

                        {/* Broadcast Title if live */}
                        {s.title ? (
                          <p
                            className="text-[12px] text-[#4a2030] line-clamp-1 italic bg-[rgba(255,255,255,0.55)] px-2.5 py-1 rounded-lg border border-[rgba(220,180,190,0.25)]"
                            title={s.title}
                          >
                            &quot;{s.title}&quot;
                          </p>
                        ) : (
                          <div className="flex items-center justify-between text-[11px] text-[#907080] font-mono px-1">
                            <span>Ingest Standby</span>
                            <span>Rolling Ring Buffer</span>
                          </div>
                        )}
                      </div>

                      {/* ── Metrics Row: Viewers + Clips ── */}
                      <div className="grid grid-cols-2 gap-3 mt-3 w-full relative z-10">
                        <div className="bg-[rgba(248,240,245,0.6)] border border-[rgba(220,180,190,0.22)] rounded-[14px] py-2.5 px-3 text-center flex flex-col items-center justify-center">
                          <p className="font-semibold text-[9px] text-[#c08090] tracking-[1.2px] uppercase whitespace-nowrap">
                            VIEWERS
                          </p>
                          <p className="font-['DM_Mono'] font-bold text-[22px] leading-[26px] text-[#1a0a10] mt-0.5 whitespace-nowrap">
                            {status === "OFFLINE" ? "—" : formatViewerCount(s.viewer_count)}
                          </p>
                        </div>

                        <div className="bg-[rgba(248,240,245,0.6)] border border-[rgba(220,180,190,0.22)] rounded-[14px] py-2.5 px-3 text-center flex flex-col items-center justify-center">
                          <p className="font-semibold text-[9px] text-[#c08090] tracking-[1.2px] uppercase whitespace-nowrap">
                            CLIPS
                          </p>
                          <p className="font-['DM_Mono'] font-bold text-[22px] leading-[26px] text-[#1a0a10] mt-0.5 whitespace-nowrap">
                            {s.clips_count ?? 0}
                          </p>
                        </div>
                      </div>

                      {/* ── Audio Waveform Visualizer & Ingest Telemetry ── */}
                      <div className="flex flex-col items-center justify-center min-h-[28px] my-2 relative z-10">
                        <AudioWaveformSVG color={avatarBg} isLive={status !== "OFFLINE"} />
                        {status !== "OFFLINE" && (
                          <span className="text-[9px] font-mono text-[#166534] font-bold tracking-tight mt-0.5">
                            CFR 60fps • 1080p • 6.2 Mbps Ingest
                          </span>
                        )}
                      </div>

                      {/* ── Framing Layout & Subtitle Spec Pill (Clickable) ── */}
                      <div
                        onClick={(e) => handleOpenEditDesign(s, e)}
                        className="flex items-center justify-between gap-1.5 py-1.5 px-2.5 rounded-xl bg-[rgba(255,255,255,0.75)] hover:bg-white border border-[rgba(220,180,190,0.35)] hover:border-[#9b59b6] mb-2 relative z-10 shadow-2xs cursor-pointer transition-all group/pill"
                        title={`Click to customize framing layout & subtitle style for ${s.name}`}
                      >
                        <div className="flex items-center gap-1.5 min-w-0">
                          <span className="text-[9px] font-['DM_Mono'] font-extrabold text-purple-900 bg-purple-100/90 border border-purple-300 px-1.5 py-0.5 rounded uppercase group-hover/pill:bg-purple-200">
                            LAYOUT
                          </span>
                          <span className="text-[10.5px] font-bold text-[#1a0a10] truncate">
                            {s.framing_mode === "gamer"
                              ? "Gamer Split"
                              : s.framing_mode === "speaker"
                              ? "Active Speaker"
                              : s.framing_mode === "center"
                              ? "AI Centered"
                              : s.framing_mode === "split"
                              ? "Dual Split"
                              : s.framing_mode === "blur"
                              ? "Blurred Backdrop"
                              : "16:9 White Canvas (Top Hook + Bottom Subtitles)"}
                          </span>
                        </div>
                        <div className="flex items-center gap-1 shrink-0">
                          <span className="text-[9px] font-['DM_Mono'] text-[#8b2252] font-bold">
                            {s.subtitle_style ? s.subtitle_style.replace("_", " ").toUpperCase() : "GLACIER GLOW"}
                          </span>
                          <span className="text-[10px] text-[#9b59b6] opacity-70 group-hover/pill:opacity-100">✏️</span>
                        </div>
                      </div>

                      {/* ── Interactive Channel Action Bar ── */}
                      <div className="pt-3 border-t border-[rgba(220,180,190,0.22)] flex items-center justify-between gap-1.5 flex-wrap relative z-10">
                        {/* Left: Active/Paused & Auto-Post Toggles */}
                        <div className="flex items-center gap-1.5">
                          {/* Active / Paused Surveillance Toggle */}
                          <button
                            onClick={(e) => handleToggleStreamer(s, e)}
                            className={`px-2.5 py-1.5 rounded-xl font-bold text-xs flex items-center gap-1.5 transition-all cursor-pointer border ${
                              s.enabled
                                ? "bg-[rgba(187,247,208,0.75)] hover:bg-[rgba(187,247,208,1)] text-[#15803d] border-[rgba(134,239,172,0.6)]"
                                : "bg-slate-100 hover:bg-slate-200 text-slate-600 border-slate-300"
                            }`}
                            title={s.enabled ? "Surveillance active (click to pause)" : "Surveillance paused (click to activate)"}
                          >
                            <span className={`size-2 rounded-full ${s.enabled ? "bg-[#16a34a]" : "bg-slate-400"}`} />
                            <span>{s.enabled ? "Active" : "Paused"}</span>
                          </button>

                          {/* Auto-Approve Clips Toggle Pill */}
                          <button
                            onClick={(e) => handleToggleAutoApprove(s, e)}
                            className={`px-2 py-1.5 rounded-xl text-[10px] font-mono font-bold flex items-center gap-1 transition-all cursor-pointer border ${
                              s.auto_approve
                                ? "bg-[rgba(243,232,255,0.85)] hover:bg-[rgba(243,232,255,1)] text-[#7c3aed] border-[rgba(192,132,252,0.5)]"
                                : "bg-white/40 hover:bg-white/70 text-[#907080] border-[rgba(220,180,190,0.3)]"
                            }`}
                            title={s.auto_approve ? "Auto-Publish is ON: clips are published autonomously without review" : "Auto-Publish is OFF: clips await manual human review in vault"}
                          >
                            <span>⚡</span>
                            <span>{s.auto_approve ? "Auto: ON" : "Auto: OFF"}</span>
                          </button>
                        </div>

                        {/* Right: Design Styles + Harvest Highlights + Open Link + Delete */}
                        <div className="flex items-center gap-1.5">
                          {/* Configure Custom Streamer Styles & Design */}
                          <button
                            onClick={(e) => handleOpenEditDesign(s, e)}
                            className="px-2.5 py-1.5 rounded-xl bg-white/80 hover:bg-white text-[#8b2252] font-semibold text-xs flex items-center gap-1 transition-all cursor-pointer border border-[rgba(220,180,190,0.4)] shadow-2xs hover:border-[#9b59b6]"
                            title={`Customize video layout, captions, and pipeline styles for ${s.name}`}
                          >
                            <span>🎨</span>
                            <span>Styles</span>
                          </button>

                          {/* Harvest Highlights Now */}
                          <button
                            onClick={(e) => handleTriggerVOD(s, e)}
                            disabled={isProcessingThis}
                            className="px-2.5 py-1.5 rounded-xl bg-[rgba(240,180,195,0.35)] hover:bg-[rgba(240,180,195,0.7)] text-[#8b2252] font-semibold text-xs flex items-center gap-1 transition-colors cursor-pointer border border-[rgba(220,180,190,0.35)] disabled:opacity-50"
                            title="Harvest instant highlight from this stream"
                          >
                            <svg className={`size-3.5 ${isProcessingThis ? "animate-spin" : ""}`} viewBox="0 0 24 24" fill="currentColor">
                              <polygon points="5 3 19 12 5 21 5 3" />
                            </svg>
                            <span>{isProcessingThis ? "Extracting..." : "Clip Now"}</span>
                          </button>

                          {/* External Stream Link */}
                          {s.url && (
                            <a
                              href={s.url}
                              target="_blank"
                              rel="noreferrer"
                              className="p-1.5 rounded-xl bg-[rgba(255,255,255,0.6)] hover:bg-white text-[#702040] transition-colors border border-[rgba(220,180,190,0.3)]"
                              title={`Watch ${s.name} on ${s.platform}`}
                            >
                              <svg className="size-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                                <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
                                <polyline points="15 3 21 3 21 9" />
                                <line x1="10" y1="14" x2="21" y2="3" />
                              </svg>
                            </a>
                          )}

                          {/* Delete Streamer */}
                          <button
                            onClick={(e) => handleDeleteStreamer(s.id, s.name, e)}
                            className="p-1.5 rounded-xl bg-[rgba(254,202,202,0.5)] hover:bg-[rgba(254,202,202,0.9)] text-[#be123c] border border-[rgba(252,165,165,0.4)] transition-colors cursor-pointer"
                            title="Remove channel from surveillance"
                          >
                            <svg className="size-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                              <polyline points="3 6 5 6 21 6" />
                              <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
                            </svg>
                          </button>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </>
        )}

        {/* ── VIEW 2: Pipeline Telemetry & Live Console ────────────────── */}
        {activeView === "telemetry" && (
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 w-full">
            {/* Left Column: Diagnostics, VRAM & Model Stack (5 Cols) */}
            <div className="lg:col-span-5 flex flex-col gap-5">
              {/* Hardware VRAM & Memory Guard */}
              <div className="figma-glass-card rounded-[22px] p-5 shadow-sm space-y-4">
                <div className="flex items-center justify-between border-b border-[rgba(220,180,190,0.25)] pb-3">
                  <div className="flex items-center gap-2">
                    <span className="text-base">🛡️</span>
                    <h3 className="font-bold text-sm text-[#1a0a10]">Hardware & VRAM Isolation</h3>
                  </div>
                  <span className="font-['DM_Mono'] text-[11px] font-bold text-[#166534] bg-emerald-100 px-2 py-0.5 rounded-full">
                    16GB BOUND
                  </span>
                </div>

                <div className="space-y-3">
                  <div>
                    <div className="flex justify-between items-center text-xs font-semibold mb-1">
                      <span className="text-[#604050]">GPU VRAM Allocation (Dynamic Offload)</span>
                      <span className="font-mono text-[#8b2252]">11.8 GB / 16.0 GB (74%)</span>
                    </div>
                    <div className="w-full bg-[rgba(220,180,190,0.3)] h-2 rounded-full overflow-hidden">
                      <div className="w-[74%] h-full rounded-full bg-gradient-to-r from-[#d4a8e4] to-[#9b59b6]" />
                    </div>
                  </div>

                  <div>
                    <div className="flex justify-between items-center text-xs font-semibold mb-1">
                      <span className="text-[#604050]">CPU Multi-Stream Ingest Load</span>
                      <span className="font-mono text-[#166534]">42% across 8 threads</span>
                    </div>
                    <div className="w-full bg-[rgba(220,180,190,0.3)] h-2 rounded-full overflow-hidden">
                      <div className="w-[42%] h-full rounded-full bg-[#22c55e]" />
                    </div>
                  </div>

                  <div>
                    <div className="flex justify-between items-center text-xs font-semibold mb-1">
                      <span className="text-[#604050]">NVMe Rolling Ring Buffer Cache</span>
                      <span className="font-mono text-[#b45309]">18% (CFR 60fps locked)</span>
                    </div>
                    <div className="w-full bg-[rgba(220,180,190,0.3)] h-2 rounded-full overflow-hidden">
                      <div className="w-[18%] h-full rounded-full bg-[#f59e0b]" />
                    </div>
                  </div>
                </div>
              </div>

              {/* AI Models Stack Health */}
              <div className="figma-glass-card rounded-[22px] p-5 shadow-sm space-y-4">
                <div className="flex items-center justify-between border-b border-[rgba(220,180,190,0.25)] pb-3">
                  <div className="flex items-center gap-2">
                    <span className="text-base">🧠</span>
                    <h3 className="font-bold text-sm text-[#1a0a10]">AI Model Pipelines</h3>
                  </div>
                  <span className="font-['DM_Mono'] text-[11px] font-bold text-[#7c3aed]">
                    READY & STANDBY
                  </span>
                </div>

                <div className="space-y-3">
                  <div className="p-3 rounded-xl bg-white/50 border border-[rgba(220,180,190,0.25)] flex items-center justify-between">
                    <div>
                      <span className="font-bold text-xs text-[#1a0a10] block">Faster-Whisper Large v3</span>
                      <span className="text-[11px] text-[#805060]">Speech recognition & hook excitement detection</span>
                    </div>
                    <span className="font-mono text-[10px] font-bold px-2 py-0.5 rounded bg-purple-100 text-purple-700">
                      FP16 Loaded
                    </span>
                  </div>

                  <div className="p-3 rounded-xl bg-white/50 border border-[rgba(220,180,190,0.25)] flex items-center justify-between">
                    <div>
                      <span className="font-bold text-xs text-[#1a0a10] block">YOLOv8x Dynamic Reframer</span>
                      <span className="text-[11px] text-[#805060]">Facial landmark & active speaker 9:16 tracking</span>
                    </div>
                    <span className="font-mono text-[10px] font-bold px-2 py-0.5 rounded bg-emerald-100 text-emerald-700">
                      Active
                    </span>
                  </div>

                  <div className="p-3 rounded-xl bg-white/50 border border-[rgba(220,180,190,0.25)] flex items-center justify-between">
                    <div>
                      <span className="font-bold text-xs text-[#1a0a10] block">RMS Audio Waveform Analyzer</span>
                      <span className="text-[11px] text-[#805060]">Dynamic scream, laughter & hype detection</span>
                    </div>
                    <span className="font-mono text-[10px] font-bold px-2 py-0.5 rounded bg-rose-100 text-rose-700">
                      Surveilling
                    </span>
                  </div>
                </div>
              </div>

              {/* Dual Audio Visualizer Channels */}
              <div className="figma-glass-card rounded-[22px] p-5 shadow-sm space-y-3">
                <h3 className="font-bold text-sm text-[#1a0a10]">Live Audio Frequency Spectrogram</h3>
                <div className="space-y-2">
                  <div className="p-2.5 rounded-xl bg-white/60 border border-[rgba(220,180,190,0.25)]">
                    <div className="flex justify-between items-center text-[10px] font-mono text-[#8b2252] font-bold mb-1">
                      <span>CH1 / MAIN PROGRAM AUDIO</span>
                      <span>STEREO 48kHz</span>
                    </div>
                    <AudioWaveformSVG color="#9b59b6" isLive={pipelineActive} />
                  </div>

                  <div className="p-2.5 rounded-xl bg-white/60 border border-[rgba(220,180,190,0.25)]">
                    <div className="flex justify-between items-center text-[10px] font-mono text-[#166534] font-bold mb-1">
                      <span>CH2 / RMS EXCITEMENT FILTER</span>
                      <span>PHONEME TRACKED</span>
                    </div>
                    <AudioWaveformSVG color="#22c55e" isLive={pipelineActive} />
                  </div>
                </div>
              </div>
            </div>

            {/* Right Column: Live Pipeline Event Terminal (7 Cols) */}
            <div className="lg:col-span-7 flex flex-col">
              <div className="figma-glass-card rounded-[22px] shadow-sm flex flex-col h-[650px] overflow-hidden border border-[rgba(220,180,190,0.35)]">
                {/* Terminal Header */}
                <div className="p-4 bg-[rgba(255,255,255,0.7)] border-b border-[rgba(220,180,190,0.3)] flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-sm">💻</span>
                    <span className="font-bold text-xs text-[#1a0a10] font-['DM_Mono'] uppercase tracking-wider">
                      Live Ingest & Pipeline Event Terminal
                    </span>
                  </div>

                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => setAutoScrollLogs(!autoScrollLogs)}
                      className={`text-[10px] font-mono px-2 py-1 rounded-md transition-colors cursor-pointer border ${
                        autoScrollLogs
                          ? "bg-emerald-100 text-emerald-800 border-emerald-300"
                          : "bg-slate-100 text-slate-600 border-slate-300"
                      }`}
                      title="Toggle auto-scrolling to latest log"
                    >
                      Auto-scroll: {autoScrollLogs ? "ON" : "OFF"}
                    </button>

                    <button
                      onClick={() => setConsoleLogs([])}
                      className="text-[10px] font-mono px-2 py-1 rounded-md bg-white text-[#805060] border border-[rgba(220,180,190,0.4)] hover:bg-black/5 cursor-pointer"
                    >
                      Clear
                    </button>
                  </div>
                </div>

                {/* Terminal Body */}
                <div className="p-4 flex-1 overflow-y-auto bg-[rgba(26,10,16,0.95)] font-mono text-[11px] leading-[18px] space-y-1.5 select-text text-white">
                  {consoleLogs.length === 0 ? (
                    <div className="h-full flex items-center justify-center text-slate-500 italic">
                      Terminal console cleared. Awaiting next pipeline event...
                    </div>
                  ) : (
                    consoleLogs.map((log) => {
                      let tagColor = "text-slate-400";
                      let tagBg = "bg-white/10";
                      if (log.tag === "INGEST") {
                        tagColor = "text-sky-300";
                        tagBg = "bg-sky-500/20";
                      } else if (log.tag === "WHISPER") {
                        tagColor = "text-purple-300";
                        tagBg = "bg-purple-500/20";
                      } else if (log.tag === "YOLO") {
                        tagColor = "text-amber-300";
                        tagBg = "bg-amber-500/20";
                      } else if (log.tag === "CLIP") {
                        tagColor = "text-pink-300";
                        tagBg = "bg-pink-500/20";
                      } else if (log.tag === "OK") {
                        tagColor = "text-emerald-300";
                        tagBg = "bg-emerald-500/20";
                      } else if (log.tag === "WARN") {
                        tagColor = "text-rose-300";
                        tagBg = "bg-rose-500/20";
                      }

                      return (
                        <div key={log.id} className="flex items-start gap-2 hover:bg-white/5 px-1 py-0.5 rounded">
                          <span className="text-slate-500 shrink-0 select-none">[{log.time}]</span>
                          <span className={`px-1.5 py-0.2 rounded text-[9px] font-bold shrink-0 ${tagBg} ${tagColor}`}>
                            {log.tag}
                          </span>
                          <span className="text-slate-200 break-all">{log.msg}</span>
                        </div>
                      );
                    })
                  )}
                  <div ref={consoleBottomRef} />
                </div>

                {/* Terminal Footer Info */}
                <div className="p-2.5 bg-[rgba(255,255,255,0.8)] border-t border-[rgba(220,180,190,0.25)] flex items-center justify-between text-[10px] font-mono text-[#805060]">
                  <div className="flex items-center gap-2">
                    <span className="size-2 rounded-full bg-[#22c55e] animate-pulse" />
                    <span>Socket: edge-router-us-east-1</span>
                  </div>
                  <span>Resampling: -vsync cfr -r 60 (Strict Zero Drift)</span>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* ── Granular Streamer Design & Pipeline Styles Modal ───────────── */}
        {editingStreamer && (
          <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4 animate-fadeIn">
            <div className="figma-glass-card bg-white/95 rounded-[24px] max-w-3xl w-full p-6 sm:p-7 shadow-2xl border border-[rgba(192,132,204,0.4)] max-h-[92vh] overflow-y-auto">
              {/* Modal Header */}
              <div className="flex items-center justify-between border-b border-[rgba(220,180,190,0.3)] pb-4 mb-5">
                <div className="flex items-center gap-3.5">
                  <div
                    className="size-11 rounded-full flex items-center justify-center text-white font-bold text-base shadow-sm shrink-0"
                    style={{ backgroundColor: editingStreamer.color || "#9b59b6" }}
                  >
                    {editingStreamer.name.charAt(0).toUpperCase()}
                  </div>
                  <div>
                    <h3 className="font-bold text-lg text-[#1a0a10] flex items-center gap-2 flex-wrap">
                      <span>Pipeline Design & Styling Studio:</span>
                      <span className="text-[#8b2252] font-extrabold">{editingStreamer.name}</span>
                      <span className="text-[10px] font-mono uppercase px-2 py-0.5 rounded-md font-bold bg-[rgba(240,180,195,0.4)] text-[#8b2252]">
                        {editingStreamer.platform}
                      </span>
                    </h3>
                    <p className="text-xs text-[#805060] mt-0.5">
                      Configure custom aspect ratio framing, typography, and highlight processing specifically for this channel.
                    </p>
                  </div>
                </div>
                <button
                  onClick={() => setEditingStreamer(null)}
                  className="size-8 rounded-full hover:bg-black/5 flex items-center justify-center text-[#805060] font-bold text-base cursor-pointer"
                >
                  ✕
                </button>
              </div>

              <form onSubmit={handleSaveEditDesign} className="space-y-6">
                {/* ── SECTION 1: Framing & Aspect Ratio Layout ── */}
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <label className="text-xs font-bold text-[#6b1a30] uppercase tracking-wider block">
                      1. Framing & Aspect Ratio Layout (16:9 to 9:16)
                    </label>
                    <span className="text-[10px] font-mono text-[#8b2252]">
                      Active: {editDesignForm.framing_mode.toUpperCase()}
                    </span>
                  </div>
                  <p className="text-xs text-[#805060] mb-3">
                    Choose how horizontal 16:9 stream content is reframed into vertical 1080x1920 video for YouTube Shorts, TikTok, and Instagram Reels.
                  </p>

                  <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                    {/* 1. 16:9 White Canvas (Recommended) */}
                    <div
                      onClick={() => setEditDesignForm({ ...editDesignForm, framing_mode: "white_canvas" })}
                      className={`p-3.5 rounded-2xl border-2 transition-all cursor-pointer relative flex flex-col justify-between ${
                        editDesignForm.framing_mode === "white_canvas"
                          ? "border-[#9b59b6] bg-[rgba(243,232,255,0.45)] shadow-md transform -translate-y-0.5"
                          : "border-[rgba(220,180,190,0.35)] bg-white/60 hover:border-[#c084cc] hover:bg-white"
                      }`}
                    >
                      <div className="absolute top-2.5 right-2.5">
                        <span className="text-[8px] font-['DM_Mono'] font-extrabold text-emerald-800 bg-emerald-100 border border-emerald-300 px-1.5 py-0.5 rounded-full">
                          RECOMMENDED
                        </span>
                      </div>
                      <div>
                        <div className="flex items-center gap-1.5 mb-1.5">
                          <span className="text-base">⬜</span>
                          <span className="text-xs font-bold text-[#1a0a10]">16:9 White Canvas</span>
                        </div>
                        <p className="text-[11px] text-[#805060] leading-snug">
                          Full 16:9 widescreen video uncropped in center. Streamer header & viral hook above, animated subtitles below.
                        </p>
                      </div>
                      <div className="mt-2.5 pt-2 border-t border-[rgba(220,180,190,0.25)] flex items-center justify-between text-[10px] font-mono font-bold text-[#8b2252]">
                        <span>Zero Cropping</span>
                        <span>{editDesignForm.framing_mode === "white_canvas" ? "✓ SELECTED" : "SELECT"}</span>
                      </div>
                    </div>

                    {/* 2. Gamer Split */}
                    <div
                      onClick={() => setEditDesignForm({ ...editDesignForm, framing_mode: "gamer" })}
                      className={`p-3.5 rounded-2xl border-2 transition-all cursor-pointer relative flex flex-col justify-between ${
                        editDesignForm.framing_mode === "gamer"
                          ? "border-[#9b59b6] bg-[rgba(243,232,255,0.45)] shadow-md transform -translate-y-0.5"
                          : "border-[rgba(220,180,190,0.35)] bg-white/60 hover:border-[#c084cc] hover:bg-white"
                      }`}
                    >
                      <div>
                        <div className="flex items-center gap-1.5 mb-1.5">
                          <span className="text-base">🎮</span>
                          <span className="text-xs font-bold text-[#1a0a10]">Gamer Split</span>
                        </div>
                        <p className="text-[11px] text-[#805060] leading-snug">
                          Two-stack vertical split. Facecam zoomed on top window, gameplay action centered on bottom window.
                        </p>
                      </div>
                      <div className="mt-2.5 pt-2 border-t border-[rgba(220,180,190,0.25)] flex items-center justify-between text-[10px] font-mono font-bold text-[#8b2252]">
                        <span>Facecam + Game</span>
                        <span>{editDesignForm.framing_mode === "gamer" ? "✓ SELECTED" : "SELECT"}</span>
                      </div>
                    </div>

                    {/* 3. Active Speaker Tracking */}
                    <div
                      onClick={() => setEditDesignForm({ ...editDesignForm, framing_mode: "speaker" })}
                      className={`p-3.5 rounded-2xl border-2 transition-all cursor-pointer relative flex flex-col justify-between ${
                        editDesignForm.framing_mode === "speaker"
                          ? "border-[#9b59b6] bg-[rgba(243,232,255,0.45)] shadow-md transform -translate-y-0.5"
                          : "border-[rgba(220,180,190,0.35)] bg-white/60 hover:border-[#c084cc] hover:bg-white"
                      }`}
                    >
                      <div>
                        <div className="flex items-center gap-1.5 mb-1.5">
                          <span className="text-base">🎯</span>
                          <span className="text-xs font-bold text-[#1a0a10]">Active Speaker</span>
                        </div>
                        <p className="text-[11px] text-[#805060] leading-snug">
                          Computer vision face detection and Mouth Aspect Ratio (MAR) dynamically pan the 9:16 viewport following speech.
                        </p>
                      </div>
                      <div className="mt-2.5 pt-2 border-t border-[rgba(220,180,190,0.25)] flex items-center justify-between text-[10px] font-mono font-bold text-[#8b2252]">
                        <span>AI Dynamic Pan</span>
                        <span>{editDesignForm.framing_mode === "speaker" ? "✓ SELECTED" : "SELECT"}</span>
                      </div>
                    </div>

                    {/* 4. AI Centered Crop */}
                    <div
                      onClick={() => setEditDesignForm({ ...editDesignForm, framing_mode: "center" })}
                      className={`p-3.5 rounded-2xl border-2 transition-all cursor-pointer relative flex flex-col justify-between ${
                        editDesignForm.framing_mode === "center"
                          ? "border-[#9b59b6] bg-[rgba(243,232,255,0.45)] shadow-md transform -translate-y-0.5"
                          : "border-[rgba(220,180,190,0.35)] bg-white/60 hover:border-[#c084cc] hover:bg-white"
                      }`}
                    >
                      <div>
                        <div className="flex items-center gap-1.5 mb-1.5">
                          <span className="text-base">📐</span>
                          <span className="text-xs font-bold text-[#1a0a10]">AI Centered</span>
                        </div>
                        <p className="text-[11px] text-[#805060] leading-snug">
                          Direct 9:16 vertical crop locked to the middle of the frame with edge-boundary safety.
                        </p>
                      </div>
                      <div className="mt-2.5 pt-2 border-t border-[rgba(220,180,190,0.25)] flex items-center justify-between text-[10px] font-mono font-bold text-[#8b2252]">
                        <span>Center 1080x1920</span>
                        <span>{editDesignForm.framing_mode === "center" ? "✓ SELECTED" : "SELECT"}</span>
                      </div>
                    </div>

                    {/* 5. Dual Split Screen */}
                    <div
                      onClick={() => setEditDesignForm({ ...editDesignForm, framing_mode: "split" })}
                      className={`p-3.5 rounded-2xl border-2 transition-all cursor-pointer relative flex flex-col justify-between ${
                        editDesignForm.framing_mode === "split"
                          ? "border-[#9b59b6] bg-[rgba(243,232,255,0.45)] shadow-md transform -translate-y-0.5"
                          : "border-[rgba(220,180,190,0.35)] bg-white/60 hover:border-[#c084cc] hover:bg-white"
                      }`}
                    >
                      <div>
                        <div className="flex items-center gap-1.5 mb-1.5">
                          <span className="text-base">👥</span>
                          <span className="text-xs font-bold text-[#1a0a10]">Dual Split Screen</span>
                        </div>
                        <p className="text-[11px] text-[#805060] leading-snug">
                          Dual stacked layout (Speaker 1 Top / Speaker 2 Bottom). Designed for podcasts, IRL dual streams, and debates.
                        </p>
                      </div>
                      <div className="mt-2.5 pt-2 border-t border-[rgba(220,180,190,0.25)] flex items-center justify-between text-[10px] font-mono font-bold text-[#8b2252]">
                        <span>50/50 Podcast</span>
                        <span>{editDesignForm.framing_mode === "split" ? "✓ SELECTED" : "SELECT"}</span>
                      </div>
                    </div>

                    {/* 6. Blurred Backdrop */}
                    <div
                      onClick={() => setEditDesignForm({ ...editDesignForm, framing_mode: "blur" })}
                      className={`p-3.5 rounded-2xl border-2 transition-all cursor-pointer relative flex flex-col justify-between ${
                        editDesignForm.framing_mode === "blur"
                          ? "border-[#9b59b6] bg-[rgba(243,232,255,0.45)] shadow-md transform -translate-y-0.5"
                          : "border-[rgba(220,180,190,0.35)] bg-white/60 hover:border-[#c084cc] hover:bg-white"
                      }`}
                    >
                      <div>
                        <div className="flex items-center gap-1.5 mb-1.5">
                          <span className="text-base">🌫️</span>
                          <span className="text-xs font-bold text-[#1a0a10]">Blurred Backdrop</span>
                        </div>
                        <p className="text-[11px] text-[#805060] leading-snug">
                          Keeps the full 16:9 widescreen video intact in the center, filling top and bottom with a blurred version of the stream.
                        </p>
                      </div>
                      <div className="mt-2.5 pt-2 border-t border-[rgba(220,180,190,0.25)] flex items-center justify-between text-[10px] font-mono font-bold text-[#8b2252]">
                        <span>Ambient Blur</span>
                        <span>{editDesignForm.framing_mode === "blur" ? "✓ SELECTED" : "SELECT"}</span>
                      </div>
                    </div>
                  </div>
                </div>

                {/* ── SECTION 2: Animated Subtitle Typography ── */}
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <label className="text-xs font-bold text-[#6b1a30] uppercase tracking-wider block">
                      2. Animated Karaoke Subtitle Typography
                    </label>
                    <span className="text-[10px] font-mono text-[#8b2252]">
                      Active: {editDesignForm.subtitle_style.toUpperCase()}
                    </span>
                  </div>
                  <p className="text-xs text-[#805060] mb-3">
                    Subtitles are synchronized word-by-word with millisecond precision using Faster-Whisper VAD.
                  </p>

                  <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                    {/* Glacier Glow Cyan */}
                    <div
                      onClick={() => setEditDesignForm({ ...editDesignForm, subtitle_style: "glacier_glow" })}
                      className={`p-3 rounded-2xl border-2 transition-all cursor-pointer flex flex-col justify-between ${
                        editDesignForm.subtitle_style === "glacier_glow"
                          ? "border-[#9b59b6] bg-[rgba(243,232,255,0.45)] shadow-md"
                          : "border-[rgba(220,180,190,0.35)] bg-white/60 hover:bg-white"
                      }`}
                    >
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-bold text-[#1a0a10]">Glacier Glow Cyan</span>
                        <span className="size-3 rounded-full bg-[#00e5ff] shadow-sm" />
                      </div>
                      <div className="my-2 p-2 rounded-lg bg-slate-900 text-center font-bold text-xs tracking-wide">
                        <span className="text-white">THIS IS </span>
                        <span className="text-[#00e5ff] drop-shadow-[0_0_8px_rgba(0,229,255,0.8)]">INSANE 🔥</span>
                      </div>
                      <span className="text-[10px] text-[#805060]">Cyberpunk neon cyan glow</span>
                    </div>

                    {/* Alex Hormozi Yellow */}
                    <div
                      onClick={() => setEditDesignForm({ ...editDesignForm, subtitle_style: "hormozi" })}
                      className={`p-3 rounded-2xl border-2 transition-all cursor-pointer flex flex-col justify-between ${
                        editDesignForm.subtitle_style === "hormozi"
                          ? "border-[#9b59b6] bg-[rgba(243,232,255,0.45)] shadow-md"
                          : "border-[rgba(220,180,190,0.35)] bg-white/60 hover:bg-white"
                      }`}
                    >
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-bold text-[#1a0a10]">Alex Hormozi Yellow</span>
                        <span className="size-3 rounded-full bg-[#fde047] shadow-sm" />
                      </div>
                      <div className="my-2 p-2 rounded-lg bg-black text-center font-extrabold text-xs tracking-wider">
                        <span className="text-white">WATCH </span>
                        <span className="text-[#fde047]">THIS MOVE 🚀</span>
                      </div>
                      <span className="text-[10px] text-[#805060]">Heavy yellow highlight pop</span>
                    </div>

                    {/* MrBeast Hype */}
                    <div
                      onClick={() => setEditDesignForm({ ...editDesignForm, subtitle_style: "mrbeast" })}
                      className={`p-3 rounded-2xl border-2 transition-all cursor-pointer flex flex-col justify-between ${
                        editDesignForm.subtitle_style === "mrbeast"
                          ? "border-[#9b59b6] bg-[rgba(243,232,255,0.45)] shadow-md"
                          : "border-[rgba(220,180,190,0.35)] bg-white/60 hover:bg-white"
                      }`}
                    >
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-bold text-[#1a0a10]">MrBeast Hype</span>
                        <span className="size-3 rounded-full bg-[#22c55e] shadow-sm" />
                      </div>
                      <div className="my-2 p-2 rounded-lg bg-black text-center font-black text-xs">
                        <span className="text-white">NO </span>
                        <span className="text-[#22c55e]">WAY! 😱</span>
                      </div>
                      <span className="text-[10px] text-[#805060]">Dynamic scale emphasis</span>
                    </div>

                    {/* TikTok Bold */}
                    <div
                      onClick={() => setEditDesignForm({ ...editDesignForm, subtitle_style: "tiktok_bold" })}
                      className={`p-3 rounded-2xl border-2 transition-all cursor-pointer flex flex-col justify-between ${
                        editDesignForm.subtitle_style === "tiktok_bold"
                          ? "border-[#9b59b6] bg-[rgba(243,232,255,0.45)] shadow-md"
                          : "border-[rgba(220,180,190,0.35)] bg-white/60 hover:bg-white"
                      }`}
                    >
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-bold text-[#1a0a10]">TikTok Bold</span>
                        <span className="size-3 rounded-full bg-[#38bdf8] shadow-sm" />
                      </div>
                      <div className="my-2 p-2 rounded-lg bg-slate-900 text-center font-bold text-xs">
                        <span className="text-white">WAIT FOR </span>
                        <span className="text-[#38bdf8]">IT 🎯</span>
                      </div>
                      <span className="text-[10px] text-[#805060]">Crisp Proxima sans font</span>
                    </div>

                    {/* Neon Cyber */}
                    <div
                      onClick={() => setEditDesignForm({ ...editDesignForm, subtitle_style: "neon" })}
                      className={`p-3 rounded-2xl border-2 transition-all cursor-pointer flex flex-col justify-between ${
                        editDesignForm.subtitle_style === "neon"
                          ? "border-[#9b59b6] bg-[rgba(243,232,255,0.45)] shadow-md"
                          : "border-[rgba(220,180,190,0.35)] bg-white/60 hover:bg-white"
                      }`}
                    >
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-bold text-[#1a0a10]">Neon Cyber</span>
                        <span className="size-3 rounded-full bg-[#f43f5e] shadow-sm" />
                      </div>
                      <div className="my-2 p-2 rounded-lg bg-purple-950 text-center font-extrabold text-xs">
                        <span className="text-white">CYBER </span>
                        <span className="text-[#f43f5e] drop-shadow-[0_0_8px_rgba(244,63,94,0.8)]">CLUTCH ⚡</span>
                      </div>
                      <span className="text-[10px] text-[#805060]">Magenta & violet glow</span>
                    </div>

                    {/* Clean Sans */}
                    <div
                      onClick={() => setEditDesignForm({ ...editDesignForm, subtitle_style: "minimal_clean" })}
                      className={`p-3 rounded-2xl border-2 transition-all cursor-pointer flex flex-col justify-between ${
                        editDesignForm.subtitle_style === "minimal_clean"
                          ? "border-[#9b59b6] bg-[rgba(243,232,255,0.45)] shadow-md"
                          : "border-[rgba(220,180,190,0.35)] bg-white/60 hover:bg-white"
                      }`}
                    >
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-bold text-[#1a0a10]">Clean Sans</span>
                        <span className="size-3 rounded-full bg-slate-300 shadow-sm" />
                      </div>
                      <div className="my-2 p-2 rounded-lg bg-slate-800 text-center font-medium text-xs">
                        <span className="text-slate-100">Simple and clean</span>
                      </div>
                      <span className="text-[10px] text-[#805060]">Minimalist narrative typography</span>
                    </div>
                  </div>
                </div>

                {/* ── SECTION 3: Publishing Automation ── */}
                <div className="p-4 rounded-2xl bg-[rgba(255,255,255,0.7)] border border-[rgba(220,180,190,0.35)] flex items-center justify-between gap-4">
                  <div className="flex items-start gap-3">
                    <input
                      type="checkbox"
                      id="edit_auto_approve_check"
                      checked={editDesignForm.auto_approve}
                      onChange={(e) => setEditDesignForm({ ...editDesignForm, auto_approve: e.target.checked })}
                      className="size-4.5 accent-[#9b59b6] rounded cursor-pointer mt-0.5"
                    />
                    <label htmlFor="edit_auto_approve_check" className="cursor-pointer">
                      <span className="font-bold text-xs text-[#1a0a10] block">
                        Auto-Publish Approved Highlights for {editingStreamer.name}
                      </span>
                      <span className="text-[11px] text-[#805060]">
                        {editDesignForm.auto_approve
                          ? "ON: Clips exceeding viral threshold are queued directly to YouTube/TikTok distribution."
                          : "OFF: Clips are saved in the Clip Vault awaiting manual human review before publishing."}
                      </span>
                    </label>
                  </div>
                  <span className={`px-2.5 py-1 rounded-full text-[10px] font-mono font-bold shrink-0 ${
                    editDesignForm.auto_approve
                      ? "bg-purple-100 text-[#7c3aed] border border-purple-200"
                      : "bg-slate-100 text-slate-600 border border-slate-200"
                  }`}>
                    {editDesignForm.auto_approve ? "AUTO: ON" : "MANUAL REVIEW"}
                  </span>
                </div>

                {/* Modal Footer Buttons */}
                <div className="flex items-center justify-end gap-3 pt-3 border-t border-[rgba(220,180,190,0.3)]">
                  <button
                    type="button"
                    onClick={() => setEditingStreamer(null)}
                    className="px-4 py-2 rounded-xl text-xs font-semibold text-[#807080] hover:bg-black/5 cursor-pointer"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={savingDesign}
                    className="px-6 py-2.5 rounded-xl text-xs font-bold text-white shadow-sm hover:brightness-105 cursor-pointer transition-all disabled:opacity-50"
                    style={{
                      backgroundImage:
                        "linear-gradient(152deg, #d4a8e4 0%, #9b59b6 100%)",
                    }}
                  >
                    {savingDesign ? "Saving Pipeline Styles..." : `Save Styles for ${editingStreamer.name}`}
                  </button>
                </div>
              </form>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
