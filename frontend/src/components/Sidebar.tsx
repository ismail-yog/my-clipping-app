"use client";

import React from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  LayoutDashboard,
  Sparkles,
  Sliders,
  Tv,
  Radio,
  Film,
  UploadCloud,
  Settings,
  Flame,
  ChevronLeft,
  ChevronRight,
  Zap,
  Activity,
  Cpu,
} from "lucide-react";

interface SidebarProps {
  isOpen: boolean;
  activeTab: string;
  onTabChange: (tab: string) => void;
  pendingCount: number;
  onToggle: () => void;
}

const NAV_ITEMS = [
  { id: "dashboard", label: "Overview", icon: LayoutDashboard, badge: null },
  { id: "editor", label: "Studio Editor", icon: Sliders, badge: "PRO" },
  { id: "generator", label: "Viral Clipper", icon: Sparkles, badge: "AI" },
  { id: "streamers", label: "Streamers", icon: Tv, badge: null },
  { id: "pipeline", label: "Live Engine", icon: Radio, badge: "LIVE" },
  { id: "clips", label: "Clip Vault", icon: Film, badgeKey: "pending" },
  { id: "uploads", label: "Upload Hub", icon: UploadCloud, badge: null },
  { id: "settings", label: "Settings", icon: Settings, badge: null },
];

export default function Sidebar({
  isOpen,
  activeTab,
  onTabChange,
  pendingCount,
  onToggle,
}: SidebarProps) {
  return (
    <motion.aside
      initial={false}
      animate={{ width: isOpen ? 280 : 80 }}
      transition={{ type: "spring", stiffness: 350, damping: 30 }}
      className="fixed top-0 left-0 h-screen z-40 flex flex-col border-r border-white/10 bg-[#0b0e17]/95 backdrop-blur-2xl shadow-2xl"
    >
      {/* ── Brand Logo Header ───────────────────────── */}
      <div className="p-6 flex items-center justify-between border-b border-white/5">
        <div className="flex items-center gap-3 overflow-hidden">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-indigo-600 via-purple-600 to-pink-500 flex items-center justify-center shadow-lg shadow-indigo-500/30 flex-shrink-0">
            <Flame className="w-6 h-6 text-white animate-pulse" />
          </div>
          {isOpen && (
            <motion.div
              initial={{ opacity: 0, x: -10 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -10 }}
              className="flex flex-col"
            >
              <span className="text-lg font-black tracking-tight text-white flex items-center gap-1">
                STREAM<span className="text-transparent bg-clip-text bg-gradient-to-r from-indigo-400 to-pink-400">CLIPPER</span>
              </span>
              <span className="text-[10px] font-bold text-indigo-400/80 tracking-widest uppercase flex items-center gap-1">
                <Zap className="w-3 h-3 text-pink-400" /> Viral Engine 2.0
              </span>
            </motion.div>
          )}
        </div>

        <button
          onClick={onToggle}
          className="p-2 rounded-lg bg-white/5 hover:bg-white/10 text-slate-400 hover:text-white transition-colors"
          title={isOpen ? "Collapse Sidebar" : "Expand Sidebar"}
        >
          {isOpen ? <ChevronLeft className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
        </button>
      </div>

      {/* ── Quick Action Hero Button ────────────────── */}
      <div className="px-4 pt-6 pb-2">
        <button
          onClick={() => onTabChange("generator")}
          className="w-full relative group overflow-hidden rounded-xl p-[1px] font-bold text-sm shadow-xl shadow-indigo-500/20"
        >
          <span className="absolute inset-0 bg-gradient-to-r from-indigo-500 via-purple-500 to-pink-500 rounded-xl animate-gradient" />
          <div className="relative px-4 py-3 bg-[#0f1320] rounded-[11px] flex items-center justify-center gap-2 text-white group-hover:bg-transparent transition-all duration-300">
            <Sparkles className="w-4 h-4 text-pink-400 group-hover:rotate-12 transition-transform" />
            {isOpen && <span>Generate Viral Clips</span>}
          </div>
        </button>
      </div>

      {/* ── Navigation Items ───────────────────────── */}
      <nav className="flex-1 px-3 py-4 space-y-1.5 overflow-y-auto">
        {NAV_ITEMS.map((item) => {
          const Icon = item.icon;
          const isActive = activeTab === item.id;
          const badgeVal = item.badgeKey === "pending" ? (pendingCount > 0 ? pendingCount : null) : item.badge;

          return (
            <button
              key={item.id}
              onClick={() => onTabChange(item.id)}
              className={`w-full relative flex items-center gap-3.5 px-3.5 py-3 rounded-xl font-semibold text-sm transition-all duration-200 ${
                isActive
                  ? "text-white shadow-lg shadow-indigo-500/10"
                  : "text-slate-400 hover:text-slate-200 hover:bg-white/5"
              }`}
            >
              {isActive && (
                <motion.div
                  layoutId="activeTabPill"
                  className="absolute inset-0 bg-gradient-to-r from-indigo-600/30 to-purple-600/20 border border-indigo-500/40 rounded-xl"
                  transition={{ type: "spring", stiffness: 400, damping: 35 }}
                />
              )}

              <Icon
                className={`w-5 h-5 flex-shrink-0 relative z-10 transition-transform ${
                  isActive ? "text-indigo-400 scale-110" : "text-slate-400"
                }`}
              />

              {isOpen && (
                <span className="relative z-10 flex-1 text-left whitespace-nowrap">
                  {item.label}
                </span>
              )}

              {isOpen && badgeVal && (
                <span
                  className={`relative z-10 text-[11px] font-extrabold px-2 py-0.5 rounded-full ${
                    item.badge === "LIVE"
                      ? "bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 animate-pulse"
                      : item.badge === "AI"
                      ? "bg-purple-500/20 text-purple-300 border border-purple-500/30"
                      : "bg-pink-500/20 text-pink-300 border border-pink-500/30 font-mono"
                  }`}
                >
                  {badgeVal}
                </span>
              )}
            </button>
          );
        })}
      </nav>

      {/* ── Hardware / System Monitor Footer ───────── */}
      {isOpen && (
        <div className="p-4 m-3 rounded-2xl bg-white/[0.03] border border-white/5 space-y-3">
          <div className="flex items-center justify-between text-xs">
            <span className="text-slate-400 font-medium flex items-center gap-1.5">
              <Cpu className="w-3.5 h-3.5 text-cyan-400" /> VRAM Boundary
            </span>
            <span className="font-mono text-cyan-400 font-bold">16 GB</span>
          </div>
          <div className="w-full bg-slate-800 h-1.5 rounded-full overflow-hidden">
            <motion.div
              initial={{ width: "35%" }}
              animate={{ width: ["35%", "52%", "40%"] }}
              transition={{ repeat: Infinity, duration: 4, ease: "easeInOut" }}
              className="h-full bg-gradient-to-r from-cyan-400 to-indigo-500 rounded-full"
            />
          </div>
          <div className="flex items-center justify-between text-[11px] text-slate-500">
            <span className="flex items-center gap-1">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-ping" /> CFR 60fps
            </span>
            <span>TaskQueue: Active</span>
          </div>
        </div>
      )}
    </motion.aside>
  );
}
