"use client";

import React, { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import confetti from "canvas-confetti";
import {
  Film,
  Flame,
  CheckCircle2,
  XCircle,
  Play,
  Search,
  RefreshCw,
  Eye,
  Trash2,
  Sparkles,
} from "lucide-react";
import { getClips, approveClip, rejectClip, getClipThumbnailUrl } from "@/lib/api";
import VideoModal from "@/components/VideoModal";

export default function ClipsTab() {
  const [clips, setClips] = useState<any[]>([]);
  const [filter, setFilter] = useState("all");
  const [searchQuery, setSearchQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [selectedClip, setSelectedClip] = useState<any | null>(null);

  const load = async (status?: string) => {
    setLoading(true);
    try {
      const data = await getClips(status);
      setClips(data.clips || data || []);
    } catch (e) {
      setClips([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const handleFilter = (f: string) => {
    setFilter(f);
    load(f === "all" ? undefined : f);
  };

  const handleApprove = async (id: string) => {
    try {
      await approveClip(id);
      confetti({ particleCount: 60, spread: 60 });
      setClips((prev) =>
        prev.map((c) => (c.clip_id === id ? { ...c, status: "approved" } : c))
      );
    } catch (e) {
      console.error(e);
    }
  };

  const handleReject = async (id: string) => {
    try {
      await rejectClip(id);
      setClips((prev) => prev.filter((c) => c.clip_id !== id));
    } catch (e) {
      console.error(e);
    }
  };

  const filteredClips = clips.filter((c) => {
    const titleMatch = (c.title || c.clip_id || "").toLowerCase().includes(searchQuery.toLowerCase());
    const transcriptMatch = (c.transcript || "").toLowerCase().includes(searchQuery.toLowerCase());
    return titleMatch || transcriptMatch;
  });

  const FILTERS = [
    { id: "all", label: "All Clips" },
    { id: "pending_review", label: "Pending Review" },
    { id: "approved", label: "Approved" },
    { id: "uploaded", label: "Uploaded" },
  ];

  return (
    <div className="space-y-8 pb-12">
      {/* ── Top Controls ────────────────────────────── */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-2xl font-black text-white tracking-tight">Clip Review Vault</h2>
          <p className="text-xs text-slate-400">
            {filteredClips.length} clip{filteredClips.length !== 1 ? "s" : ""} available
          </p>
        </div>

        {/* Filter & Search */}
        <div className="flex flex-wrap items-center gap-3 w-full sm:w-auto">
          {/* Search Box */}
          <div className="relative flex-1 sm:w-64">
            <Search className="w-4 h-4 text-slate-500 absolute left-3.5 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search transcript or title..."
              className="w-full bg-[#0c0f1d] border border-white/10 rounded-xl pl-10 pr-4 py-2 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500 transition-colors"
            />
          </div>

          {/* Filter Pills */}
          <div className="flex items-center p-1 rounded-xl bg-white/[0.03] border border-white/5">
            {FILTERS.map((f) => (
              <button
                key={f.id}
                onClick={() => handleFilter(f.id)}
                className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all ${
                  filter === f.id
                    ? "bg-indigo-600 text-white shadow-md shadow-indigo-600/30"
                    : "text-slate-400 hover:text-white"
                }`}
              >
                {f.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* ── Clips Grid ───────────────────────────────── */}
      {loading ? (
        <div className="glass-panel p-16 text-center space-y-3">
          <RefreshCw className="w-8 h-8 text-indigo-400 animate-spin mx-auto" />
          <p className="text-sm font-bold text-slate-400">Loading Clip Vault...</p>
        </div>
      ) : filteredClips.length === 0 ? (
        <div className="glass-panel p-16 text-center space-y-3">
          <Film className="w-12 h-12 text-slate-600 mx-auto" />
          <p className="text-sm font-bold text-slate-300">No clips found in this view.</p>
          <p className="text-xs text-slate-500">Try changing filter or generating new VOD clips.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
          <AnimatePresence>
            {filteredClips.map((clip, idx) => {
              const scorePct = Math.round((clip.moment_score || 0.85) * 100);
              return (
                <motion.div
                  key={clip.clip_id}
                  layout
                  initial={{ opacity: 0, scale: 0.9 }}
                  animate={{ opacity: 1, scale: 1 }}
                  exit={{ opacity: 0, scale: 0.9 }}
                  transition={{ delay: idx * 0.03 }}
                  className="group glass-panel overflow-hidden flex flex-col justify-between hover:border-indigo-500/50 transition-all duration-300"
                >
                  {/* Thumbnail Video Top */}
                  <div
                    className="relative aspect-[9/16] bg-black cursor-pointer overflow-hidden"
                    onClick={() => setSelectedClip(clip)}
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

                    {/* Viral Badge */}
                    <div className="absolute top-3 left-3">
                      <span className="badge-viral">
                        <Flame className="w-3.5 h-3.5 text-rose-400" /> {scorePct}%
                      </span>
                    </div>

                    {/* Duration */}
                    <div className="absolute top-3 right-3 px-2 py-0.5 rounded-md bg-black/60 backdrop-blur-md text-[11px] font-mono font-bold text-white">
                      {Math.round(clip.duration || 30)}s
                    </div>

                    {/* Play Icon on Hover */}
                    <div className="absolute inset-0 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity">
                      <div className="w-12 h-12 rounded-full bg-indigo-600/90 text-white flex items-center justify-center shadow-xl transform scale-90 group-hover:scale-100 transition-transform">
                        <Play className="w-5 h-5 fill-current ml-0.5" />
                      </div>
                    </div>

                    {/* Title */}
                    <div className="absolute bottom-3 left-3 right-3">
                      <h4 className="text-xs font-bold text-white line-clamp-2 drop-shadow-md">
                        {clip.title || clip.transcript || "Viral Highlight"}
                      </h4>
                    </div>
                  </div>

                  {/* Actions Footer */}
                  <div className="p-4 space-y-3 bg-[#0a0d16]">
                    <div className="flex items-center justify-between text-xs text-slate-400">
                      <span className="capitalize text-slate-300 font-bold">
                        {clip.emotion || "Hype"}
                      </span>
                      <span
                        className={`text-[10px] font-bold uppercase px-2 py-0.5 rounded-full ${
                          clip.status === "approved"
                            ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
                            : clip.status === "uploaded"
                            ? "bg-cyan-500/10 text-cyan-400 border border-cyan-500/20"
                            : "bg-amber-500/10 text-amber-400 border border-amber-500/20"
                        }`}
                      >
                        {clip.status || "Pending"}
                      </span>
                    </div>

                    <div className="flex items-center gap-2 pt-1">
                      {clip.status !== "approved" && clip.status !== "uploaded" ? (
                        <>
                          <button
                            onClick={() => handleApprove(clip.clip_id)}
                            className="flex-1 btn-primary-neon py-2 px-3 text-xs justify-center"
                          >
                            <CheckCircle2 className="w-3.5 h-3.5" /> Approve
                          </button>
                          <button
                            onClick={() => handleReject(clip.clip_id)}
                            className="p-2 rounded-xl bg-rose-500/10 hover:bg-rose-500/20 text-rose-400 border border-rose-500/20 transition-colors"
                            title="Reject & Delete"
                          >
                            <Trash2 className="w-4 h-4" />
                          </button>
                        </>
                      ) : (
                        <button
                          onClick={() => setSelectedClip(clip)}
                          className="w-full btn-secondary-glass py-2 px-3 text-xs justify-center"
                        >
                          <Eye className="w-3.5 h-3.5" /> View Details & SEO
                        </button>
                      )}
                    </div>
                  </div>
                </motion.div>
              );
            })}
          </AnimatePresence>
        </div>
      )}

      {/* ── Video Modal ─────────────────────────────── */}
      {selectedClip && (
        <VideoModal
          clip={selectedClip}
          onClose={() => setSelectedClip(null)}
          onApproveSuccess={() => {
            load(filter === "all" ? undefined : filter);
            setSelectedClip(null);
          }}
        />
      )}
    </div>
  );
}
