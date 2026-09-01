"use client";

import React, { useState, useEffect } from "react";
import { motion } from "framer-motion";
import {
  Sparkles,
  Flame,
  Radio,
  Tv,
  CheckCircle2,
  Clock,
  TrendingUp,
  Cpu,
  Zap,
  Play,
  ArrowRight,
  Shield,
  Activity,
} from "lucide-react";
import { getStatus, getScores, startPipeline, stopPipeline } from "@/lib/api";

export default function DashboardTab() {
  const [statusData, setStatusData] = useState<any>(null);
  const [scoresData, setScoresData] = useState<any>(null);
  const [pipelineActive, setPipelineActive] = useState(false);
  const [isToggling, setIsToggling] = useState(false);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const [s, sc] = await Promise.all([getStatus(), getScores()]);
        setStatusData(s);
        setScoresData(sc);
        setPipelineActive(s.pipeline?.running || false);
      } catch (e) {
        console.error("Dashboard fetch error:", e);
      }
    };
    fetchData();
    const interval = setInterval(fetchData, 3000);
    return () => clearInterval(interval);
  }, []);

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
    } catch (e) {
      console.error(e);
    } finally {
      setIsToggling(false);
    }
  };

  const stats = statusData?.stats || {};

  return (
    <div className="space-y-8 pb-12">
      {/* ── System Status Banner ──────────────────────── */}
      <div className="glass-panel p-8 relative overflow-hidden flex flex-col md:flex-row items-center justify-between gap-6 border-indigo-500/20">
        <div className="space-y-2 z-10">
          <div className="flex items-center gap-2">
            <span className="live-pulse" />
            <span className="text-xs font-black uppercase tracking-widest text-emerald-400">
              Autonomous Video Engine
            </span>
          </div>
          <h2 className="text-3xl font-black text-white tracking-tight">
            StreamClipper Pipeline is{" "}
            <span className={pipelineActive ? "text-emerald-400" : "text-slate-400"}>
              {pipelineActive ? "Active & Monitoring" : "Standby"}
            </span>
          </h2>
          <p className="text-xs text-slate-400 max-w-xl">
            Live Whisper transcription, VFR-to-CFR audio-sync normalization, and multi-agent AI
            auto-clipping running on background worker threads.
          </p>
        </div>

        <div className="flex items-center gap-4 z-10">
          <button
            onClick={handleTogglePipeline}
            disabled={isToggling}
            className={`px-6 py-3.5 rounded-2xl font-bold text-sm flex items-center gap-2 shadow-lg transition-all ${
              pipelineActive
                ? "bg-rose-500/20 text-rose-300 border border-rose-500/30 hover:bg-rose-500/30"
                : "btn-primary-neon"
            }`}
          >
            <Radio className="w-4 h-4" />
            <span>{pipelineActive ? "Pause Monitoring" : "Start Live Pipeline"}</span>
          </button>
        </div>
      </div>

      {/* ── Key Metrics Cards ─────────────────────────── */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5">
        {[
          {
            label: "Total Viral Clips",
            val: stats.total_clips || 0,
            icon: Flame,
            color: "from-rose-500 to-pink-500",
            sub: "Generated & Transcoded",
          },
          {
            label: "Pending Review",
            val: stats.pending_review || 0,
            icon: Clock,
            color: "from-amber-500 to-orange-500",
            sub: "Awaiting Action",
          },
          {
            label: "Active Streamers",
            val: stats.active_sessions || 0,
            icon: Tv,
            color: "from-cyan-500 to-blue-500",
            sub: "Monitored 24/7",
          },
          {
            label: "Auto-Approved",
            val: stats.approved || 0,
            icon: CheckCircle2,
            color: "from-emerald-500 to-teal-500",
            sub: "Score >= 80%",
          },
        ].map((item, idx) => {
          const Icon = item.icon;
          return (
            <motion.div
              key={item.label}
              initial={{ opacity: 0, y: 15 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: idx * 0.05 }}
              className="glass-panel p-6 space-y-4 hover:border-white/20"
            >
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold text-slate-400">{item.label}</span>
                <div
                  className={`w-9 h-9 rounded-xl bg-gradient-to-tr ${item.color} flex items-center justify-center text-white shadow-md`}
                >
                  <Icon className="w-4 h-4" />
                </div>
              </div>
              <div>
                <span className="text-3xl font-black text-white tracking-tight">{item.val}</span>
                <p className="text-xs text-slate-500 mt-1 font-medium">{item.sub}</p>
              </div>
            </motion.div>
          );
        })}
      </div>

      {/* ── Realtime Audio Reactive Visualizer & Hardware Monitor ── */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Audio Wave & Excitement Radar */}
        <div className="glass-panel p-6 space-y-4 lg:col-span-2">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-base font-bold text-white flex items-center gap-2">
                <Activity className="w-4 h-4 text-indigo-400" /> Realtime Audio Excitement Radar
              </h3>
              <p className="text-xs text-slate-400">RMS Spike & Volume Excitement baseline</p>
            </div>
            <div className="audio-visualizer">
              <span className="wave-bar" />
              <span className="wave-bar" />
              <span className="wave-bar" />
              <span className="wave-bar" />
              <span className="wave-bar" />
              <span className="wave-bar" />
            </div>
          </div>

          <div className="p-6 rounded-2xl bg-[#05070c] border border-white/5 flex items-center justify-around">
            <div className="text-center space-y-1">
              <span className="text-xs text-slate-500 font-bold uppercase">RMS Threshold</span>
              <div className="text-xl font-mono font-black text-cyan-400">+12 dB</div>
            </div>
            <div className="h-10 w-[1px] bg-white/10" />
            <div className="text-center space-y-1">
              <span className="text-xs text-slate-500 font-bold uppercase">Whisper Sync</span>
              <div className="text-xl font-mono font-black text-emerald-400">0.0 ms drift</div>
            </div>
            <div className="h-10 w-[1px] bg-white/10" />
            <div className="text-center space-y-1">
              <span className="text-xs text-slate-500 font-bold uppercase">Video Resampling</span>
              <div className="text-xl font-mono font-black text-purple-400">CFR 60 FPS</div>
            </div>
          </div>
        </div>

        {/* Dream Team Status */}
        <div className="glass-panel p-6 space-y-4">
          <h3 className="text-base font-bold text-white flex items-center gap-2">
            <Sparkles className="w-4 h-4 text-pink-400" /> Dream Team Agents
          </h3>
          <div className="space-y-2.5">
            {[
              { name: "Atlas", role: "Viral Moment Scoring", status: "Active" },
              { name: "Scribe", role: "SEO & High-CTR Titles", status: "Active" },
              { name: "Sentinel", role: "Brand & Profanity Guard", status: "Active" },
              { name: "Pixel", role: "Visual Reframe & Hook", status: "Active" },
            ].map((agent) => (
              <div
                key={agent.name}
                className="flex items-center justify-between p-2.5 rounded-xl bg-white/[0.02] border border-white/5 text-xs"
              >
                <div>
                  <div className="font-bold text-white">{agent.name}</div>
                  <div className="text-[11px] text-slate-400">{agent.role}</div>
                </div>
                <span className="text-[10px] font-extrabold px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                  {agent.status}
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
