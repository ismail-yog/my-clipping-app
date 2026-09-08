"use client";

import React from "react";
import { motion } from "framer-motion";
import {
  LayoutDashboard,
  Film,
  Radio,
  Tv,
  UploadCloud,
  Settings,
  ChevronLeft,
  ChevronRight,
  Zap,
  Cpu,
  Video,
} from "lucide-react";

interface SidebarProps {
  isOpen: boolean;
  activeTab: string;
  onTabChange: (tab: string) => void;
  pendingCount: number;
  onToggle: () => void;
}

const NAV_ITEMS = [
  { id: "dashboard", label: "Dashboard", icon: LayoutDashboard, badge: null },
  { id: "studio", label: "Clip Studio", icon: Video, badge: "PRO" },
  { id: "auto_monitor", label: "Auto Monitor", icon: Radio, badge: "LIVE" },
  { id: "clips", label: "Clip Vault", icon: Film, badgeKey: "pending" },
  { id: "uploads", label: "Distribution", icon: UploadCloud, badge: null },
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
      animate={{ width: isOpen ? 230 : 76 }}
      transition={{ type: "spring", stiffness: 350, damping: 30 }}
      className="fixed top-0 left-0 h-screen z-50 flex flex-col glacier-glass border-r border-white/[0.05] bg-[#0b1120]/95 backdrop-blur-3xl"
    >
      {/* ── Brand Logo Header ───────────────────────── */}
      <div className="p-4 flex items-center justify-between border-b border-white/[0.05]">
        <div className="flex items-center gap-2.5 overflow-hidden">
          <div className="w-9 h-9 rounded-xl bg-gradient-to-tr from-[#7dd3fc] to-[#004b71] flex items-center justify-center shadow-[0_0_20px_rgba(125,211,252,0.3)] flex-shrink-0">
            <Zap className="w-4.5 h-4.5 text-[#00344f] fill-current" />
          </div>
          {isOpen && (
            <motion.div
              initial={{ opacity: 0, x: -10 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -10 }}
              className="flex flex-col"
            >
              <span className="text-xl font-bold tracking-tight text-white flex items-center gap-1 font-['Geist']">
                LumiClip
              </span>
              <span className="text-[10px] font-mono font-bold text-[#7dd3fc] tracking-widest uppercase">
                Glacier Edition
              </span>
            </motion.div>
          )}
        </div>

        <button
          onClick={onToggle}
          className="p-1.5 rounded-lg bg-white/[0.03] hover:bg-white/[0.08] text-slate-400 hover:text-white transition-colors border border-white/[0.05]"
          title={isOpen ? "Collapse Sidebar" : "Expand Sidebar"}
        >
          {isOpen ? <ChevronLeft className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
        </button>
      </div>

      {/* ── Quick Action Button ─────────────────────── */}
      <div className="px-3 pt-4 pb-2">
        <button
          onClick={() => onTabChange("studio")}
          className="w-full relative group overflow-hidden rounded-xl p-[1px] font-bold text-sm"
        >
          <div className="px-3 py-2.5 bg-[#7dd3fc]/10 hover:bg-[#7dd3fc]/20 border border-[#7dd3fc]/30 rounded-xl flex items-center justify-center gap-2 text-[#7dd3fc] shadow-[inset_0_1px_0_rgba(255,255,255,0.2),0_0_15px_rgba(125,211,252,0.15)] transition-all duration-300">
            <Zap className="w-4 h-4 fill-current drop-shadow-[0_0_8px_rgba(125,211,252,0.6)]" />
            {isOpen && <span className="font-['Geist'] font-semibold text-xs tracking-wide">Clip Studio</span>}
          </div>
        </button>
      </div>

      {/* ── Navigation Items ───────────────────────── */}
      <nav className="flex-1 px-2.5 py-2 space-y-1 overflow-y-auto">
        {NAV_ITEMS.map((item) => {
          const Icon = item.icon;
          const isActive = activeTab === item.id;
          const badgeVal =
            item.badgeKey === "pending" ? (pendingCount > 0 ? pendingCount : null) : item.badge;

          return (
            <button
              key={item.id}
              onClick={() => onTabChange(item.id)}
              className={`w-full relative flex items-center gap-2.5 px-3 py-2.5 rounded-xl font-medium text-xs transition-all duration-200 ${
                isActive
                  ? "bg-[#7dd3fc]/10 text-[#7dd3fc] font-semibold border border-[#7dd3fc]/25 shadow-[inset_0_1px_0_rgba(255,255,255,0.1),0_0_15px_rgba(125,211,252,0.1)]"
                  : "text-slate-400 hover:text-white hover:bg-white/[0.04]"
              }`}
            >
              <Icon
                className={`w-5 h-5 flex-shrink-0 relative z-10 transition-transform ${
                  isActive ? "text-[#7dd3fc] drop-shadow-[0_0_8px_rgba(125,211,252,0.5)]" : "text-slate-400"
                }`}
              />

              {isOpen && (
                <span className="relative z-10 flex-1 text-left whitespace-nowrap font-['Inter']">
                  {item.label}
                </span>
              )}

              {isOpen && badgeVal && (
                <span
                  className={`relative z-10 text-[10px] font-extrabold px-2 py-0.5 rounded-full ${
                    item.badge === "LIVE"
                      ? "bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 animate-pulse"
                      : "bg-[#7dd3fc]/20 text-[#7dd3fc] border border-[#7dd3fc]/30 font-mono"
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
        <div className="p-3 m-2.5 rounded-xl glacier-glass space-y-2.5">
          <div className="flex items-center justify-between text-xs">
            <span className="text-slate-400 font-mono text-[10px] uppercase tracking-wider flex items-center gap-1.5">
              <Cpu className="w-3 h-3 text-[#7dd3fc]" /> GPU VRAM
            </span>
            <span className="font-mono text-[#7dd3fc] font-bold text-[11px]">16 GB</span>
          </div>
          <div className="w-full bg-black/40 h-1.5 rounded-full overflow-hidden border border-white/5">
            <motion.div
              initial={{ width: "45%" }}
              animate={{ width: ["45%", "60%", "50%"] }}
              transition={{ repeat: Infinity, duration: 4, ease: "easeInOut" }}
              className="h-full bg-[#7dd3fc] shadow-[0_0_10px_rgba(125,211,252,0.8)] rounded-full"
            />
          </div>
          <div className="flex items-center justify-between text-[9px] text-slate-400 font-mono">
            <span className="flex items-center gap-1 uppercase">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 pulse-green" /> CFR 60fps
            </span>
            <span className="text-slate-500">Pipeline Active</span>
          </div>
        </div>
      )}
    </motion.aside>
  );
}
