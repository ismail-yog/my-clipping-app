"use client";

import React, { useState, useEffect } from "react";
import { motion } from "framer-motion";
import {
  Bell,
  User,
  Clock,
  Sparkles,
  Zap,
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
    <header className="sticky top-0 z-40 h-16 bg-[#0b1120]/60 backdrop-blur-2xl border-b border-white/[0.05] flex items-center justify-between px-8">
      {/* ── Title ───────────────────────────────── */}
      <div className="flex items-center gap-4">
        <motion.h1
          key={title}
          initial={{ opacity: 0, y: -4 }}
          animate={{ opacity: 1, y: 0 }}
          className="text-xl font-bold text-white tracking-tight font-['Geist']"
        >
          {title}
        </motion.h1>
      </div>

      {/* ── Right Actions ─────────────────────────── */}
      <div className="flex items-center gap-4">
        <div className="hidden md:flex items-center gap-2 px-3 py-1 glacier-glass rounded-xl font-mono text-xs text-slate-400">
          <Clock className="w-3.5 h-3.5 text-[#7dd3fc]" />
          <span>{timeStr || "00:00:00"}</span>
        </div>

        <div className="relative p-2 rounded-full hover:bg-white/10 cursor-pointer transition-colors text-slate-400 hover:text-white">
          <Bell className="w-4 h-4" />
          <span className="absolute top-1.5 right-1.5 w-2 h-2 bg-[#7dd3fc] rounded-full shadow-[0_0_8px_rgba(125,211,252,0.8)]" />
        </div>

        <div className="w-8 h-8 rounded-full bg-[#7dd3fc]/20 flex items-center justify-center cursor-pointer hover:ring-2 ring-[#7dd3fc]/40 transition-all border border-[#7dd3fc]/30">
          <User className="w-4 h-4 text-[#7dd3fc]" />
        </div>
      </div>
    </header>
  );
}
