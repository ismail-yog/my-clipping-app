"use client";

import React, { useState, useEffect } from "react";
import { motion } from "framer-motion";
import {
  Radio,
  Zap,
  Activity,
  Cpu,
  Volume2,
  Sparkles,
  ShieldCheck,
  RefreshCw,
} from "lucide-react";
import { getStatus, startPipeline, stopPipeline } from "@/lib/api";

export default function PipelineTab() {
  const [isActive, setIsActive] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [fetching, setFetching] = useState(true);

  useEffect(() => {
    getStatus()
      .then((d: any) => setIsActive(!!(d.pipeline?.running || d.pipeline_active)))
      .catch(() => {})
      .finally(() => setFetching(false));
  }, []);

  const handleToggle = async () => {
    setIsLoading(true);
    try {
      if (isActive) await stopPipeline();
      else await startPipeline();
      setIsActive(!isActive);
    } catch (e) {
      console.error(e);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="space-y-8 pb-12">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-black text-white tracking-tight">Autonomous Live Engine</h2>
          <p className="text-xs text-slate-400">
            24/7 stream capture, real-time Whisper detection, and automated viral clipping
          </p>
        </div>
      </div>

      <div className="max-w-2xl mx-auto glass-panel p-10 text-center space-y-8 relative overflow-hidden border-indigo-500/20">
        <div className="absolute top-0 right-0 -mt-16 -mr-16 w-64 h-64 bg-indigo-500/10 rounded-full blur-3xl pointer-events-none" />

        {/* Dynamic Pulse Orb */}
        <div className="relative inline-flex items-center justify-center">
          <motion.div
            animate={{
              scale: isActive ? [1, 1.15, 1] : 1,
              boxShadow: isActive
                ? [
                    "0 0 0 0 rgba(99, 102, 241, 0.4)",
                    "0 0 0 25px rgba(99, 102, 241, 0)",
                    "0 0 0 0 rgba(99, 102, 241, 0)",
                  ]
                : "none",
            }}
            transition={{ repeat: Infinity, duration: 2.2, ease: "easeInOut" }}
            className={`w-28 h-28 rounded-3xl flex items-center justify-center shadow-2xl transition-all ${
              isActive
                ? "bg-gradient-to-tr from-indigo-600 via-purple-600 to-pink-500 text-white"
                : "bg-slate-800/80 text-slate-500 border border-white/5"
            }`}
          >
            <Zap className={`w-12 h-12 ${isActive ? "text-white fill-current" : ""}`} />
          </motion.div>
        </div>

        <div className="space-y-2">
          <h3 className="text-3xl font-black text-white">
            {fetching ? "Inspecting Pipeline..." : isActive ? "Autonomous Engine Active" : "Engine Standby"}
          </h3>
          <p className="text-sm text-slate-400 max-w-md mx-auto leading-relaxed">
            {isActive
              ? "All enabled streamer streams are being ingested, converted to CFR 60fps, scored via Whisper & RMS excitement, and saved to SQLite."
              : "Activate auto-mode to continuously monitor streams and generate clips in real-time."}
          </p>
        </div>

        {/* Live Metrics Grid */}
        <div className="grid grid-cols-3 gap-3 p-4 rounded-2xl bg-black/40 border border-white/5 text-xs">
          <div>
            <span className="text-[10px] font-bold text-slate-500 uppercase">Frame Normalization</span>
            <div className="font-mono font-bold text-indigo-400 mt-0.5">CFR 60fps</div>
          </div>
          <div>
            <span className="text-[10px] font-bold text-slate-500 uppercase">VRAM Isolation</span>
            <div className="font-mono font-bold text-emerald-400 mt-0.5">16GB Bound</div>
          </div>
          <div>
            <span className="text-[10px] font-bold text-slate-500 uppercase">Worker Queue</span>
            <div className="font-mono font-bold text-cyan-400 mt-0.5">SQLite Threaded</div>
          </div>
        </div>

        {/* Big Action Button */}
        <div>
          <button
            onClick={handleToggle}
            disabled={isLoading || fetching}
            className={`w-full py-4 rounded-2xl font-bold text-sm flex items-center justify-center gap-2 shadow-xl transition-all ${
              isActive
                ? "bg-rose-500/20 text-rose-300 border border-rose-500/30 hover:bg-rose-500/30"
                : "btn-primary-neon justify-center text-base"
            }`}
          >
            {isLoading ? (
              <>
                <RefreshCw className="w-5 h-5 animate-spin" />
                <span>Processing...</span>
              </>
            ) : isActive ? (
              <>
                <Radio className="w-5 h-5" />
                <span>Halt Live Pipeline</span>
              </>
            ) : (
              <>
                <Zap className="w-5 h-5 text-pink-300" />
                <span>Engage Autonomous Pipeline</span>
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
