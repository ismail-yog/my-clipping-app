"use client";

import React, { useState } from "react";
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
} from "lucide-react";
import { getClipVideoUrl, approveClip } from "@/lib/api";
import confetti from "canvas-confetti";

interface VideoModalProps {
  clip: any;
  onClose: () => void;
  onApproveSuccess?: () => void;
}

export default function VideoModal({ clip, onClose, onApproveSuccess }: VideoModalProps) {
  const [activeSubTab, setActiveSubTab] = useState<"video" | "seo" | "transcript">("video");
  const [copied, setCopied] = useState(false);

  if (!clip) return null;

  const clipId = typeof clip === "string" ? clip : clip.clip_id || clip.id;
  const title = clip.title || "Viral Short Preview";
  const transcript = clip.transcript || "No transcript available.";
  const tags = clip.tags || ["#shorts", "#viral", "#gaming"];
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
      confetti({ particleCount: 80, spread: 70, origin: { y: 0.6 } });
      if (onApproveSuccess) onApproveSuccess();
    } catch (e) {
      console.error(e);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6 bg-black/85 backdrop-blur-xl">
      <motion.div
        initial={{ opacity: 0, scale: 0.92, y: 20 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.92, y: 20 }}
        transition={{ type: "spring", stiffness: 350, damping: 28 }}
        className="w-full max-w-4xl max-h-[90vh] bg-[#0c0f1d] border border-indigo-500/30 rounded-3xl overflow-hidden shadow-2xl flex flex-col md:flex-row"
      >
        {/* Left: 9:16 Video Player */}
        <div className="relative w-full md:w-[400px] aspect-[9/16] bg-black flex-shrink-0 flex items-center justify-center border-b md:border-b-0 md:border-r border-white/10">
          <video
            src={getClipVideoUrl(clipId)}
            controls
            autoPlay
            loop
            playsInline
            className="w-full h-full object-contain"
          />
          <div className="absolute top-4 left-4">
            <span className="badge-viral flex items-center gap-1 shadow-lg">
              <Flame className="w-3.5 h-3.5 text-rose-400" /> {scorePct}%
            </span>
          </div>
        </div>

        {/* Right: Metadata, SEO & Action Controls */}
        <div className="flex-1 flex flex-col justify-between p-6 md:p-8 overflow-y-auto space-y-6">
          {/* Header */}
          <div className="space-y-4">
            <div className="flex items-start justify-between gap-4">
              <div className="space-y-1">
                <span className="text-[10px] font-extrabold uppercase tracking-widest text-indigo-400">
                  Transcoded Clip • CFR 60 FPS
                </span>
                <h3 className="text-xl font-bold text-white leading-snug">{title}</h3>
              </div>
              <button
                onClick={onClose}
                className="p-2 rounded-xl bg-white/5 hover:bg-white/10 text-slate-400 hover:text-white transition-colors flex-shrink-0"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Sub-tab Navigation */}
            <div className="flex gap-2 border-b border-white/5 pb-3">
              {[
                { id: "video", label: "Overview", icon: Sparkles },
                { id: "seo", label: "SEO & Tags", icon: Share2 },
                { id: "transcript", label: "Transcript", icon: FileText },
              ].map((tab) => {
                const Icon = tab.icon;
                return (
                  <button
                    key={tab.id}
                    onClick={() => setActiveSubTab(tab.id as any)}
                    className={`px-3 py-1.5 rounded-xl text-xs font-bold flex items-center gap-1.5 transition-all ${
                      activeSubTab === tab.id
                        ? "bg-indigo-500/20 text-indigo-300 border border-indigo-500/40"
                        : "text-slate-400 hover:text-white"
                    }`}
                  >
                    <Icon className="w-3.5 h-3.5" />
                    <span>{tab.label}</span>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Sub-tab Content Area */}
          <div className="flex-1 space-y-4">
            {activeSubTab === "video" && (
              <div className="space-y-4 text-xs">
                <div className="p-4 rounded-2xl bg-white/[0.02] border border-white/5 space-y-2">
                  <div className="flex justify-between text-slate-400">
                    <span>Emotion Intensity</span>
                    <span className="font-bold text-white capitalize">{clip.emotion || "Hype"}</span>
                  </div>
                  <div className="flex justify-between text-slate-400">
                    <span>Duration</span>
                    <span className="font-mono text-white font-bold">{Math.round(clip.duration || 30)} seconds</span>
                  </div>
                  <div className="flex justify-between text-slate-400">
                    <span>Status</span>
                    <span className="font-bold text-emerald-400 uppercase">{clip.status || "Pending"}</span>
                  </div>
                </div>

                <div className="p-4 rounded-2xl bg-gradient-to-r from-purple-950/20 to-indigo-950/20 border border-purple-500/20">
                  <span className="text-[10px] font-bold text-purple-300 uppercase">Hook Text Overlay</span>
                  <p className="text-sm font-extrabold text-white mt-1">"{clip.hook_text || title}"</p>
                </div>
              </div>
            )}

            {activeSubTab === "seo" && (
              <div className="space-y-4 text-xs">
                <div className="space-y-2">
                  <span className="text-slate-400 font-bold">Suggested Description</span>
                  <p className="p-3 rounded-xl bg-black/40 border border-white/5 text-slate-300 text-xs">
                    {clip.description || transcript.slice(0, 200)}
                  </p>
                </div>
                <div className="space-y-2">
                  <span className="text-slate-400 font-bold">Viral Tags</span>
                  <div className="flex flex-wrap gap-1.5">
                    {(Array.isArray(tags) ? tags : [tags]).map((tag: string, i: number) => (
                      <span
                        key={i}
                        className="px-2.5 py-1 rounded-lg bg-indigo-500/10 border border-indigo-500/20 text-indigo-300 font-mono text-[11px]"
                      >
                        {tag.startsWith("#") ? tag : `#${tag}`}
                      </span>
                    ))}
                  </div>
                </div>
                <button
                  onClick={handleCopySEO}
                  className="btn-secondary-glass w-full py-2.5 text-xs justify-center"
                >
                  <Copy className="w-3.5 h-3.5" />
                  <span>{copied ? "Copied to Clipboard!" : "Copy Full SEO Block"}</span>
                </button>
              </div>
            )}

            {activeSubTab === "transcript" && (
              <div className="p-4 rounded-2xl bg-black/40 border border-white/5 max-h-52 overflow-y-auto space-y-2">
                <span className="text-[10px] font-mono text-slate-500 uppercase">Whisper Captions</span>
                <p className="text-xs text-slate-200 leading-relaxed">{transcript}</p>
              </div>
            )}
          </div>

          {/* Action Bar Footer */}
          <div className="flex items-center gap-3 pt-4 border-t border-white/5">
            <button
              onClick={handleApprove}
              className="flex-1 btn-primary-neon py-3 text-xs justify-center"
            >
              <CheckCircle2 className="w-4 h-4" />
              <span>Approve & Schedule Upload</span>
            </button>
            <a
              href={getClipVideoUrl(clipId)}
              download={`clip_${clipId}.mp4`}
              className="btn-secondary-glass py-3 px-4 text-xs"
              title="Download MP4"
            >
              <Download className="w-4 h-4" />
            </a>
          </div>
        </div>
      </motion.div>
    </div>
  );
}
