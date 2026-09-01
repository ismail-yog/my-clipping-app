"use client";

import React, { useState, useEffect } from "react";
import { motion } from "framer-motion";
import {
  Activity,
  Bell,
  Sparkles,
  Radio,
  Clock,
  ShieldCheck,
  RefreshCw,
} from "lucide-react";

interface HeaderProps {
  connected: boolean;
  onToggleSidebar: () => void;
  title: string;
}

export default function Header({ connected, onToggleSidebar, title }: HeaderProps) {
  const [timeStr, setTimeStr] = useState("");

  useEffect(() => {
    const updateTime = () => {
      const now = new Date();
      setTimeStr(
        now.toLocaleTimeString("en-US", {
          hour: "2-digit",
          minute: "2-digit",
          second: "2-digit",
          hour12: false,
        })
      );
    };
    updateTime();
    const interval = setInterval(updateTime, 1000);
    return () => clearInterval(interval);
  }, []);

  return (
    <header className="sticky top-0 z-30 flex items-center justify-between px-8 py-4 bg-[#07090e]/80 backdrop-blur-xl border-b border-white/5">
      {/* ── Page Title & Breadcrumb ───────────────── */}
      <div className="flex items-center gap-3">
        <motion.h1
          key={title}
          initial={{ opacity: 0, y: -5 }}
          animate={{ opacity: 1, y: 0 }}
          className="text-2xl font-black text-white tracking-tight"
        >
          {title}
        </motion.h1>
        <span className="text-xs font-bold px-2.5 py-0.5 rounded-full bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
          PRO PIPELINE
        </span>
      </div>

      {/* ── Live Hub Indicators ───────────────────── */}
      <div className="flex items-center gap-4">
        {/* Real-time Clock */}
        <div className="hidden sm:flex items-center gap-2 px-3 py-1.5 rounded-xl bg-white/[0.03] border border-white/5 font-mono text-xs text-slate-400">
          <Clock className="w-3.5 h-3.5 text-indigo-400" />
          <span>{timeStr || "00:00:00"}</span>
        </div>

        {/* WebSocket Connection Radar */}
        <div
          className={`flex items-center gap-2 px-3.5 py-1.5 rounded-xl border text-xs font-bold transition-all ${
            connected
              ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-400 shadow-sm shadow-emerald-500/10"
              : "bg-rose-500/10 border-rose-500/30 text-rose-400"
          }`}
        >
          <span className="relative flex h-2 w-2">
            {connected && (
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
            )}
            <span
              className={`relative inline-flex rounded-full h-2 w-2 ${
                connected ? "bg-emerald-500" : "bg-rose-500"
              }`}
            />
          </span>
          <span>{connected ? "LIVE WEBSOCKET" : "CONNECTING"}</span>
        </div>

        {/* Dream Team AI Badge */}
        <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-gradient-to-r from-purple-500/10 to-pink-500/10 border border-purple-500/20 text-xs font-bold text-purple-300">
          <Sparkles className="w-3.5 h-3.5 text-pink-400 animate-spin-slow" />
          <span>Dream Team Active</span>
        </div>
      </div>
    </header>
  );
}
