"use client";

import React, { useState, useEffect } from "react";
import { createPortal } from "react-dom";
import { motion, AnimatePresence } from "framer-motion";
import {
  X,
  Download,
  CheckCircle2,
  Copy,
  Sparkles,
  Flame,
  FileText,
  Share2,
  Check,
  Film,
  ExternalLink,
} from "lucide-react";
import { getClipVideoUrl, approveClip } from "@/lib/api";
import confetti from "canvas-confetti";

interface VideoModalProps {
  clip: any;
  onClose: () => void;
  onApproveSuccess?: () => void;
}

export default function VideoModal({ clip, onClose, onApproveSuccess }: VideoModalProps) {
  const [mounted, setMounted] = useState(false);
  const [activeSubTab, setActiveSubTab] = useState<"video" | "seo" | "transcript">("video");
  const [copied, setCopied] = useState(false);

  // Mount check for createPortal and lock body scroll while modal is open
  useEffect(() => {
    setMounted(true);
    const originalOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = originalOverflow;
    };
  }, []);

  // Close on Escape key
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onClose();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  if (!clip || !mounted || typeof document === "undefined") return null;

  const clipId = typeof clip === "string" ? clip : clip.clip_id || clip.id;
  const title = clip.title || clip.clip_id || "Viral Highlight Clip";
  const transcript = clip.transcript || "No transcript generated.";
  const tags = clip.tags || ["#shorts", "#viral", "#gaming", "#twitch"];
  const scorePct = Math.round((clip.moment_score || 0.85) * 100);

  const handleCopySEO = () => {
    const text = `${title}\n\n${transcript}\n\n${Array.isArray(tags) ? tags.join(" ") : tags}`;
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleApprove = async () => {
    try {
      await approveClip(clipId);
      confetti({ particleCount: 70, spread: 70, origin: { y: 0.6 } });
      if (onApproveSuccess) onApproveSuccess();
    } catch (e) {
      console.error(e);
    }
  };

  const modalContent = (
    <div
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
      className="fixed inset-0 z-[9999] flex items-center justify-center p-3 sm:p-5 md:p-6 bg-black/85 backdrop-blur-xl animate-in fade-in duration-200"
    >
      <motion.div
        initial={{ opacity: 0, scale: 0.95, y: 10 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.95, y: 10 }}
        transition={{ type: "spring", stiffness: 450, damping: 32 }}
        className="w-full max-w-4xl h-[min(650px,86vh)] bg-[#0b1120] border border-white/10 rounded-2xl overflow-hidden shadow-[0_0_60px_rgba(0,0,0,0.9)] flex flex-col md:flex-row relative z-10"
      >
        {/* Close Button Top-Right (Absolute for instant clickability) */}
        <button
          onClick={onClose}
          className="absolute top-3.5 right-3.5 z-30 p-2 rounded-xl bg-black/60 hover:bg-white/10 text-slate-400 hover:text-white border border-white/10 transition-colors backdrop-blur-md"
          title="Close (Esc)"
        >
          <X className="w-4 h-4" />
        </button>

        {/* Left Pane: 9:16 Vertical Video Player (Height-Constrained, Zero Scroll) */}
        <div className="relative h-[46%] md:h-full aspect-[9/16] bg-black flex-shrink-0 flex items-center justify-center border-b md:border-b-0 md:border-r border-white/10 mx-auto md:mx-0 overflow-hidden">
          <video
            key={clipId}
            src={getClipVideoUrl(clipId)}
            controls
            autoPlay
            loop
            playsInline
            className="w-full h-full object-contain bg-black"
          />

          {/* Top Floating Badge */}
          <div className="absolute top-3 left-3 pointer-events-none flex items-center gap-1.5">
            <span className="bg-black/70 backdrop-blur-md font-mono text-[10px] text-[#7dd3fc] font-bold px-2 py-0.5 rounded-full border border-white/10 flex items-center gap-1">
              <Flame className="w-3 h-3 text-pink-400 fill-current" /> {scorePct}% VIRAL
            </span>
            <span className="bg-black/70 backdrop-blur-md font-mono text-[10px] text-slate-300 px-2 py-0.5 rounded-full border border-white/10">
              CFR 60fps
            </span>
          </div>
        </div>

        {/* Right Pane: Metadata & Controls (Flex-Col with Internal Scroll if needed) */}
        <div className="flex-1 h-[52%] md:h-full flex flex-col justify-between p-5 md:p-6 overflow-hidden space-y-4">
          
          {/* Top Title & Subtabs */}
          <div className="space-y-3 flex-shrink-0 pr-8">
            <div className="space-y-1">
              <div className="flex items-center gap-2">
                <span className="text-[10px] font-mono uppercase tracking-widest text-[#7dd3fc] font-bold">
                  {clip.streamer_name ? `${clip.streamer_name} Highlight` : "Autonomous Clip"}
                </span>
                <span className="text-[10px] font-mono text-slate-500">•</span>
                <span className="text-[10px] font-mono text-slate-400">
                  {Math.round(clip.duration || 30)}s
                </span>
              </div>
              <h3 className="text-base sm:text-lg font-bold text-white line-clamp-2 leading-tight font-['Inter']">
                {title}
              </h3>
            </div>

            {/* Sub-tab Navigation */}
            <div className="flex gap-1.5 border-b border-white/5 pb-2.5">
              {[
                { id: "video", label: "Telemetry", icon: Sparkles },
                { id: "seo", label: "SEO & Tags", icon: Share2 },
                { id: "transcript", label: "Transcript", icon: FileText },
              ].map((tab) => {
                const Icon = tab.icon;
                const isCur = activeSubTab === tab.id;
                return (
                  <button
                    key={tab.id}
                    onClick={() => setActiveSubTab(tab.id as any)}
                    className={`px-3 py-1.5 rounded-xl text-xs font-mono font-medium flex items-center gap-1.5 transition-all ${
                      isCur
                        ? "bg-[#7dd3fc]/15 text-[#7dd3fc] border border-[#7dd3fc]/40 shadow-[0_0_10px_rgba(125,211,252,0.15)]"
                        : "text-slate-400 hover:text-white bg-white/[0.02]"
                    }`}
                  >
                    <Icon className="w-3.5 h-3.5" />
                    <span>{tab.label}</span>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Middle Body Area (Scrolls cleanly if text is long) */}
          <div className="flex-1 overflow-y-auto pr-1 custom-scrollbar space-y-3">
            {activeSubTab === "video" && (
              <div className="space-y-3 text-xs">
                <div className="p-3.5 rounded-xl bg-black/40 border border-white/5 space-y-2 font-mono">
                  <div className="flex justify-between text-slate-400">
                    <span>Clip ID</span>
                    <span className="text-slate-200 truncate max-w-[180px]">{clipId}</span>
                  </div>
                  <div className="flex justify-between text-slate-400">
                    <span>Emotion Intensity</span>
                    <span className="font-bold text-white capitalize">{clip.emotion || "Hype"}</span>
                  </div>
                  <div className="flex justify-between text-slate-400">
                    <span>Target Resolution</span>
                    <span className="text-[#7dd3fc] font-bold">1080×1920 (9:16)</span>
                  </div>
                  <div className="flex justify-between text-slate-400">
                    <span>Pipeline Status</span>
                    <span className="font-bold text-emerald-400 uppercase">{clip.status || "Pending Review"}</span>
                  </div>
                </div>

                {clip.hook_text && (
                  <div className="p-3 rounded-xl bg-[#7dd3fc]/10 border border-[#7dd3fc]/20">
                    <span className="text-[10px] font-mono text-[#7dd3fc] uppercase font-bold">Generated Hook Text</span>
                    <p className="text-xs font-bold text-white mt-0.5">"{clip.hook_text}"</p>
                  </div>
                )}
              </div>
            )}

            {activeSubTab === "seo" && (
              <div className="space-y-3 text-xs">
                <div className="space-y-1.5">
                  <span className="text-[10px] font-mono uppercase tracking-wider text-slate-400">Viral Tags</span>
                  <div className="flex flex-wrap gap-1.5">
                    {(Array.isArray(tags) ? tags : [tags]).map((tag: string, i: number) => (
                      <span
                        key={i}
                        className="px-2.5 py-1 rounded-lg bg-[#7dd3fc]/10 border border-[#7dd3fc]/20 text-[#7dd3fc] font-mono text-[11px]"
                      >
                        {tag.startsWith("#") ? tag : `#${tag}`}
                      </span>
                    ))}
                  </div>
                </div>

                <button
                  onClick={handleCopySEO}
                  className="w-full py-2.5 rounded-xl bg-white/5 hover:bg-white/10 border border-white/10 text-white font-mono text-xs flex items-center justify-center gap-1.5 transition-all"
                >
                  {copied ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                  <span>{copied ? "Copied SEO Block!" : "Copy Full SEO Block"}</span>
                </button>
              </div>
            )}

            {activeSubTab === "transcript" && (
              <div className="p-3.5 rounded-xl bg-black/40 border border-white/5 space-y-1.5">
                <span className="text-[10px] font-mono text-slate-500 uppercase tracking-wider">Whisper Captions</span>
                <p className="text-xs text-slate-200 leading-relaxed font-['Inter']">{transcript}</p>
              </div>
            )}
          </div>

          {/* Action Bar Footer (Always visible at bottom) */}
          <div className="flex items-center gap-2.5 pt-3 border-t border-white/5 flex-shrink-0">
            <button
              onClick={handleApprove}
              className="flex-1 py-2.5 rounded-xl bg-[#7dd3fc]/15 hover:bg-[#7dd3fc]/25 border border-[#7dd3fc]/40 text-[#7dd3fc] font-bold text-xs flex items-center justify-center gap-1.5 transition-all shadow-[0_0_15px_rgba(125,211,252,0.15)] hover:shadow-[0_0_20px_rgba(125,211,252,0.3)]"
            >
              <CheckCircle2 className="w-4 h-4" />
              <span>Approve for Upload</span>
            </button>
            <a
              href={getClipVideoUrl(clipId)}
              download={`clip_${clipId}.mp4`}
              className="p-2.5 rounded-xl bg-white/5 hover:bg-white/10 text-slate-300 hover:text-white border border-white/10 transition-colors flex items-center justify-center"
              title="Download MP4"
            >
              <Download className="w-4 h-4" />
            </a>
          </div>

        </div>
      </motion.div>
    </div>
  );

  return createPortal(modalContent, document.body);
}
