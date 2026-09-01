"use client";

import React, { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import confetti from "canvas-confetti";
import {
  Sparkles,
  Play,
  Download,
  Upload,
  CheckCircle2,
  AlertCircle,
  Clock,
  Layers,
  Flame,
  Film,
  Zap,
  Wand2,
  Copy,
  Video,
  Trash2,
  Eye,
  RefreshCw,
} from "lucide-react";
import {
  processVOD,
  getVODProgress,
  getClips,
  approveClip,
  rejectClip,
  getClipVideoUrl,
  getClipThumbnailUrl,
} from "@/lib/api";
import VideoModal from "@/components/VideoModal";

const LAYOUTS = [
  {
    id: "gamer",
    name: "Gamer Split",
    desc: "Top facecam + bottom gameplay reframe",
    badge: "Most Viral",
    preview: "🎮",
  },
  {
    id: "centered",
    name: "AI Centered",
    desc: "Smart 9:16 subject tracking & crop",
    badge: "Clean",
    preview: "🎯",
  },
  {
    id: "cinematic",
    name: "Full Portrait",
    desc: "Full vertical blur backdrop + video",
    badge: "9:16",
    preview: "📱",
  },
];

export default function ClipGeneratorTab() {
  const [url, setUrl] = useState("");
  const [selectedLayout, setSelectedLayout] = useState("gamer");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [activeJob, setActiveJob] = useState<any>(null);
  const [generatedClips, setGeneratedClips] = useState<any[]>([]);
  const [previewClip, setPreviewClip] = useState<any>(null);
  const [copiedId, setCopiedId] = useState<string | null>(null);

  // Poll for job progress
  useEffect(() => {
    let interval: any;
    const checkProgress = async () => {
      try {
        const data = await getVODProgress();
        const jobs = Object.entries(data.progress || {});
        if (jobs.length > 0) {
          const [jobId, jobData]: [string, any] = jobs[jobs.length - 1];
          setActiveJob({ id: jobId, ...jobData });
          if (jobData.progress === 100) {
            setIsSubmitting(false);
            loadRecentClips();
            confetti({ particleCount: 100, spread: 70, origin: { y: 0.6 } });
          }
        }
      } catch (e) {
        // Silently handle polling error
      }
    };

    checkProgress();
    interval = setInterval(checkProgress, 2000);
    return () => clearInterval(interval);
  }, []);

  const loadRecentClips = async () => {
    try {
      const data = await getClips();
      setGeneratedClips((data.clips || []).slice(0, 8));
    } catch (e) {
      console.error(e);
    }
  };

  useEffect(() => {
    loadRecentClips();
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!url.trim()) return;

    setIsSubmitting(true);
    try {
      const res = await processVOD(url, selectedLayout);
      setActiveJob({
        id: res.job_id,
        url,
        progress: 5,
        status: "Initiating stream ingestion...",
      });
    } catch (err: any) {
      setIsSubmitting(false);
      alert(err.message || "Failed to start VOD process");
    }
  };

  const handleApprove = async (clipId: string) => {
    try {
      await approveClip(clipId);
      confetti({ particleCount: 50, spread: 60 });
      loadRecentClips();
    } catch (e) {
      console.error(e);
    }
  };

  const copyTags = (tags: string[], id: string) => {
    navigator.clipboard.writeText(tags.join(" "));
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  return (
    <div className="space-y-8 pb-12">
      {/* ── Hero Banner ──────────────────────────────── */}
      <motion.div
        initial={{ opacity: 0, y: 15 }}
        animate={{ opacity: 1, y: 0 }}
        className="relative overflow-hidden rounded-3xl bg-gradient-to-r from-indigo-950/60 via-purple-950/40 to-slate-950/60 border border-indigo-500/20 p-8 shadow-2xl"
      >
        <div className="absolute top-0 right-0 -mt-12 -mr-12 w-96 h-96 bg-gradient-to-br from-indigo-500/10 to-pink-500/10 rounded-full blur-3xl pointer-events-none" />

        <div className="relative z-10 max-w-2xl space-y-3">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-indigo-500/10 border border-indigo-500/20 text-indigo-400 text-xs font-extrabold tracking-wide uppercase">
            <Wand2 className="w-3.5 h-3.5 text-pink-400" /> Automated Viral Factory
          </div>
          <h2 className="text-3xl sm:text-4xl font-black text-white tracking-tight">
            Turn Any Stream or VOD into{" "}
            <span className="text-transparent bg-clip-text bg-gradient-to-r from-indigo-400 via-purple-300 to-pink-400">
              High-CTR Shorts
            </span>
          </h2>
          <p className="text-sm text-slate-400 leading-relaxed">
            AI-powered transcription (Whisper), instant excitement scoring, CFR 60fps cropping,
            and animated dynamic subtitles ready for YouTube Shorts & TikTok.
          </p>
        </div>
      </motion.div>

      {/* ── Generator Form ────────────────────────────── */}
      <motion.div
        initial={{ opacity: 0, y: 15 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.1 }}
        className="glass-panel p-8 space-y-6"
      >
        <form onSubmit={handleSubmit} className="space-y-6">
          {/* Input URL Box */}
          <div className="space-y-2">
            <label className="text-xs font-extrabold text-slate-300 uppercase tracking-wider flex items-center gap-2">
              <Video className="w-4 h-4 text-red-500" /> Video or Stream URL
            </label>
            <div className="relative flex items-center">
              <input
                type="text"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                placeholder="https://www.youtube.com/watch?v=... or Twitch VOD"
                disabled={isSubmitting}
                className="w-full bg-[#07090e] border border-white/10 focus:border-indigo-500 rounded-2xl px-5 py-4 text-white placeholder-slate-600 focus:outline-none focus:ring-4 focus:ring-indigo-500/20 transition-all font-mono text-sm"
              />
              <button
                type="button"
                onClick={async () => {
                  const text = await navigator.clipboard.readText();
                  if (text) setUrl(text);
                }}
                className="absolute right-3 px-3 py-2 rounded-xl bg-white/5 hover:bg-white/10 text-xs font-bold text-slate-300 transition-colors"
              >
                Paste
              </button>
            </div>
          </div>

          {/* Layout Type Selection */}
          <div className="space-y-3">
            <label className="text-xs font-extrabold text-slate-300 uppercase tracking-wider flex items-center gap-2">
              <Layers className="w-4 h-4 text-indigo-400" /> Framing & Subtitle Style
            </label>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              {LAYOUTS.map((layout) => {
                const isSelected = selectedLayout === layout.id;
                return (
                  <button
                    key={layout.id}
                    type="button"
                    onClick={() => setSelectedLayout(layout.id)}
                    className={`relative p-5 rounded-2xl border text-left transition-all ${
                      isSelected
                        ? "bg-indigo-500/10 border-indigo-500 text-white shadow-lg shadow-indigo-500/10"
                        : "bg-white/[0.02] border-white/5 text-slate-400 hover:border-white/20 hover:text-white"
                    }`}
                  >
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-2xl">{layout.preview}</span>
                      <span
                        className={`text-[10px] font-extrabold px-2 py-0.5 rounded-full ${
                          isSelected
                            ? "bg-indigo-500 text-white"
                            : "bg-white/5 text-slate-400"
                        }`}
                      >
                        {layout.badge}
                      </span>
                    </div>
                    <div className="font-bold text-sm text-white mb-1">{layout.name}</div>
                    <div className="text-xs text-slate-400 leading-snug">{layout.desc}</div>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Submit Button */}
          <div className="pt-2">
            <button
              type="submit"
              disabled={isSubmitting || !url.trim()}
              className="btn-primary-neon w-full py-4 text-base justify-center disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isSubmitting ? (
                <>
                  <RefreshCw className="w-5 h-5 animate-spin" />
                  <span>Processing Stream Pipeline...</span>
                </>
              ) : (
                <>
                  <Sparkles className="w-5 h-5 text-pink-300" />
                  <span>Extract Viral Shorts Now</span>
                </>
              )}
            </button>
          </div>
        </form>

        {/* ── Active Job Progression Bar ─────────────── */}
        <AnimatePresence>
          {activeJob && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: "auto" }}
              exit={{ opacity: 0, height: 0 }}
              className="p-6 rounded-2xl bg-indigo-950/40 border border-indigo-500/30 space-y-4"
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className="w-3 h-3 rounded-full bg-indigo-400 animate-ping" />
                  <span className="font-bold text-sm text-white">{activeJob.status}</span>
                </div>
                <span className="font-mono text-indigo-400 font-extrabold text-sm">
                  {activeJob.progress}%
                </span>
              </div>

              {/* Progress Bar */}
              <div className="w-full bg-slate-900 h-2.5 rounded-full overflow-hidden border border-white/5">
                <motion.div
                  initial={{ width: 0 }}
                  animate={{ width: `${activeJob.progress}%` }}
                  transition={{ duration: 0.4, ease: "easeOut" }}
                  className="h-full bg-gradient-to-r from-indigo-500 via-purple-500 to-pink-500 rounded-full"
                />
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </motion.div>

      {/* ── Generated Clips Showcase ──────────────────── */}
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-xl font-bold text-white tracking-tight">Recent Generated Clips</h3>
            <p className="text-xs text-slate-400">Transcoded in CFR 60fps portrait format</p>
          </div>
          <button
            onClick={loadRecentClips}
            className="btn-secondary-glass py-2 px-3 text-xs"
          >
            <RefreshCw className="w-3.5 h-3.5" /> Refresh Vault
          </button>
        </div>

        {generatedClips.length === 0 ? (
          <div className="glass-panel p-12 text-center space-y-3">
            <Film className="w-12 h-12 text-slate-600 mx-auto" />
            <p className="text-slate-400 font-medium text-sm">No clips generated yet.</p>
            <p className="text-xs text-slate-500">
              Submit a stream or YouTube URL above to automatically generate viral clips.
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
            {generatedClips.map((clip, index) => {
              const scorePct = Math.round((clip.moment_score || 0.8) * 100);
              return (
                <motion.div
                  key={clip.clip_id}
                  initial={{ opacity: 0, y: 15 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: index * 0.05 }}
                  className="group relative glass-panel overflow-hidden flex flex-col justify-between hover:border-indigo-500/50 transition-all duration-300"
                >
                  {/* Thumbnail / Video Preview Top */}
                  <div
                    className="relative aspect-[9/16] bg-black overflow-hidden cursor-pointer"
                    onClick={() => setPreviewClip(clip)}
                  >
                    <img
                      src={getClipThumbnailUrl(clip.clip_id)}
                      alt={clip.title || clip.clip_id}
                      className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500"
                      onError={(e: any) => {
                        e.target.style.display = "none";
                      }}
                    />
                    <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-transparent to-black/30" />

                    {/* Viral Score Badge */}
                    <div className="absolute top-3 left-3">
                      <span className="badge-viral flex items-center gap-1">
                        <Flame className="w-3.5 h-3.5 text-rose-400" /> {scorePct}%
                      </span>
                    </div>

                    {/* Duration Badge */}
                    <div className="absolute top-3 right-3 px-2 py-1 rounded-md bg-black/60 backdrop-blur-md text-[11px] font-mono text-white font-bold">
                      {Math.round(clip.duration || 30)}s
                    </div>

                    {/* Center Play Button Icon */}
                    <div className="absolute inset-0 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity">
                      <div className="w-12 h-12 rounded-full bg-indigo-600/90 text-white flex items-center justify-center shadow-xl transform scale-90 group-hover:scale-100 transition-transform">
                        <Play className="w-5 h-5 fill-current ml-0.5" />
                      </div>
                    </div>

                    {/* Hook Title Snippet */}
                    <div className="absolute bottom-3 left-3 right-3">
                      <h4 className="text-xs font-extrabold text-white line-clamp-2 drop-shadow-md">
                        {clip.title || clip.transcript || "Viral Moment"}
                      </h4>
                    </div>
                  </div>

                  {/* Actions Footer */}
                  <div className="p-4 space-y-3 bg-[#0a0d16]">
                    <div className="flex items-center justify-between text-xs text-slate-400">
                      <span className="capitalize text-slate-300 font-bold">{clip.emotion || "Hype"}</span>
                      <span className="text-[11px] font-mono text-slate-500">CFR 60fps</span>
                    </div>

                    <div className="flex items-center gap-2 pt-1">
                      <button
                        onClick={() => handleApprove(clip.clip_id)}
                        className="flex-1 btn-primary-neon py-2 px-3 text-xs justify-center"
                      >
                        <CheckCircle2 className="w-3.5 h-3.5" /> Approve
                      </button>
                      <button
                        onClick={() => setPreviewClip(clip)}
                        className="p-2 rounded-xl bg-white/5 hover:bg-white/10 text-slate-300 transition-colors"
                        title="Inspect Video & Captions"
                      >
                        <Eye className="w-4 h-4" />
                      </button>
                    </div>
                  </div>
                </motion.div>
              );
            })}
          </div>
        )}
      </div>

      {/* ── Modal Video Player ───────────────────────── */}
      {previewClip && (
        <VideoModal clip={previewClip} onClose={() => setPreviewClip(null)} />
      )}
    </div>
  );
}
