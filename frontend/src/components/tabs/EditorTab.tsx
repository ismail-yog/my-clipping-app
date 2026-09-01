"use client";

import React, { useState, useRef, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Play,
  Pause,
  RotateCcw,
  Volume2,
  VolumeX,
  Sparkles,
  Sliders,
  Type,
  Crop,
  Layers,
  Share2,
  Download,
  Flame,
  Check,
  Smile,
  Clock,
  Send,
  Radio,
  Tv,
  Eye,
  Settings2
} from "lucide-react";

interface SubtitleWord {
  word: string;
  start_ms: number;
  end_ms: number;
  emoji?: string;
}

interface SubtitleBlock {
  start_ms: number;
  end_ms: number;
  text: string;
  words: SubtitleWord[];
}

const PRESET_STYLES = [
  {
    id: "hormozi",
    name: "Alex Hormozi",
    font: "font-black tracking-tight",
    baseColor: "text-white",
    highlightColor: "text-[#FFE600] drop-shadow-[0_4px_12px_rgba(0,0,0,0.9)]",
    border: "border-yellow-400",
    bgBadge: "from-yellow-500/20 to-amber-500/20 border-yellow-500/30",
    preview: "STOP SCROLLING 💀"
  },
  {
    id: "mrbeast",
    name: "MrBeast Hype",
    font: "font-extrabold tracking-normal uppercase",
    baseColor: "text-white",
    highlightColor: "text-[#00FF66] drop-shadow-[0_4px_14px_rgba(0,255,102,0.6)]",
    border: "border-emerald-400",
    bgBadge: "from-emerald-500/20 to-teal-500/20 border-emerald-500/30",
    preview: "UNBELIEVABLE 🏆"
  },
  {
    id: "neon",
    name: "Cyber Neon",
    font: "font-black tracking-wider uppercase",
    baseColor: "text-cyan-200",
    highlightColor: "text-fuchsia-400 drop-shadow-[0_0_16px_rgba(232,121,249,0.9)]",
    border: "border-fuchsia-400",
    bgBadge: "from-fuchsia-500/20 to-purple-500/20 border-fuchsia-500/30",
    preview: "INSANE CLUTCH ⚡"
  },
  {
    id: "minimal_clean",
    name: "Minimal Clean",
    font: "font-semibold tracking-tight",
    baseColor: "text-zinc-300",
    highlightColor: "text-white bg-black/60 px-2 py-0.5 rounded-md",
    border: "border-zinc-400",
    bgBadge: "from-zinc-500/20 to-stone-500/20 border-zinc-500/30",
    preview: "Clean Subtitle"
  },
];

const LAYOUT_MODES = [
  { id: "single_speaker", label: "Active Speaker 9:16", desc: "MediaPipe speaker face-lock with EMA smoothing", icon: Eye },
  { id: "split_screen", label: "Podcast / Interview", desc: "Top / Bottom 2-speaker auto stack", icon: Layers },
  { id: "gamer", label: "Gamer Split View", desc: "Facecam top, gameplay bottom", icon: Tv },
  { id: "blurred_background", label: "Blurred 16:9 Canvas", desc: "Original 16:9 box over 9:16 blur", icon: Crop },
];

export default function EditorTab() {
  const [selectedStyle, setSelectedStyle] = useState("hormozi");
  const [selectedLayout, setSelectedLayout] = useState("single_speaker");
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTimeMs, setCurrentTimeMs] = useState(1200);
  const [durationMs, setDurationMs] = useState(24000);
  const [isMuted, setIsMuted] = useState(false);
  const [activeTab, setActiveTab] = useState<"captions" | "layout" | "publish">("captions");

  // Sample transcript blocks
  const [blocks, setBlocks] = useState<SubtitleBlock[]>([
    {
      start_ms: 0,
      end_ms: 3200,
      text: "OMG I JUST WON THE 1V5 CLUTCH NO WAY BRO",
      words: [
        { word: "OMG", start_ms: 0, end_ms: 600, emoji: "😱" },
        { word: "I", start_ms: 600, end_ms: 900 },
        { word: "JUST", start_ms: 900, end_ms: 1300 },
        { word: "WON", start_ms: 1300, end_ms: 1800, emoji: "🏆" },
        { word: "THE", start_ms: 1800, end_ms: 2100 },
        { word: "1V5", start_ms: 2100, end_ms: 2600, emoji: "⚔️" },
        { word: "CLUTCH", start_ms: 2600, end_ms: 3200, emoji: "👑" },
      ]
    },
    {
      start_ms: 3300,
      end_ms: 7500,
      text: "THEY SAID IT WAS IMPOSSIBLE AND CHAT WENT CRAZY",
      words: [
        { word: "THEY", start_ms: 3300, end_ms: 3800 },
        { word: "SAID", start_ms: 3800, end_ms: 4200 },
        { word: "IT", start_ms: 4200, end_ms: 4500 },
        { word: "WAS", start_ms: 4500, end_ms: 4900 },
        { word: "IMPOSSIBLE", start_ms: 4900, end_ms: 5800, emoji: "🤯" },
        { word: "AND", start_ms: 5800, end_ms: 6200 },
        { word: "CHAT", start_ms: 6200, end_ms: 6700 },
        { word: "WENT", start_ms: 6700, end_ms: 7000 },
        { word: "CRAZY", start_ms: 7000, end_ms: 7500, emoji: "🔥" },
      ]
    }
  ]);

  // Find active block and word for current playback time
  const currentBlock = blocks.find(b => currentTimeMs >= b.start_ms && currentTimeMs <= b.end_ms);
  const currentWord = currentBlock?.words.find(w => currentTimeMs >= w.start_ms && currentTimeMs <= w.end_ms);

  // Playback timer simulation
  useEffect(() => {
    let interval: any = null;
    if (isPlaying) {
      interval = setInterval(() => {
        setCurrentTimeMs(prev => {
          if (prev >= durationMs) return 0;
          return prev + 100;
        });
      }, 100);
    }
    return () => clearInterval(interval);
  }, [isPlaying, durationMs]);

  const currentStyleObj = PRESET_STYLES.find(s => s.id === selectedStyle) || PRESET_STYLES[0];

  return (
    <div className="space-y-8 animate-fadeIn pb-16">
      {/* ── Header ────────────────────────────────────────── */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-white/10 pb-6">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-3xl font-extrabold tracking-tight text-white flex items-center gap-2">
              LumiClip Studio Editor
            </h1>
            <span className="px-3 py-1 text-xs font-bold uppercase tracking-wider rounded-full bg-gradient-to-r from-amber-500/20 to-orange-500/20 text-amber-400 border border-amber-500/30">
              Interactive Pro
            </span>
          </div>
          <p className="text-zinc-400 text-sm mt-1">
            Real-time active speaker tracking, word-level animated karaoke captions, and multi-platform export.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <button className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-gradient-to-r from-indigo-600 via-purple-600 to-pink-600 text-white font-bold text-sm shadow-lg shadow-indigo-500/25 hover:shadow-indigo-500/40 hover:scale-[1.02] transition-all">
            <Share2 className="w-4 h-4" />
            Publish & Render Short
          </button>
        </div>
      </div>

      {/* ── Main Workspace Grid ─────────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
        
        {/* ── 9:16 Video Canvas Preview ─────────────────── */}
        <div className="lg:col-span-5 flex flex-col items-center">
          <div className="relative w-full max-w-[340px] aspect-[9/16] rounded-3xl overflow-hidden bg-black border-2 border-white/10 shadow-2xl shadow-purple-950/40 flex flex-col justify-between p-6">
            
            {/* Background Simulated Video Content */}
            <div className="absolute inset-0 bg-gradient-to-b from-zinc-900 via-[#101424] to-black flex items-center justify-center">
              <div className="text-center p-6 space-y-3">
                <div className="w-24 h-24 mx-auto rounded-2xl bg-indigo-600/20 border border-indigo-500/30 flex items-center justify-center">
                  <Flame className="w-12 h-12 text-indigo-400 animate-pulse" />
                </div>
                <p className="text-xs font-mono text-indigo-300/80 uppercase tracking-widest">
                  Layout: {selectedLayout}
                </p>
              </div>
            </div>

            {/* Top Badges */}
            <div className="relative z-10 flex items-center justify-between">
              <span className="px-2.5 py-1 rounded-lg bg-black/60 backdrop-blur-md text-[11px] font-bold text-white border border-white/10 flex items-center gap-1.5">
                <span className="w-2 h-2 rounded-full bg-emerald-500 animate-ping" />
                9:16 CFR 60 FPS
              </span>
              <span className="px-2.5 py-1 rounded-lg bg-black/60 backdrop-blur-md text-[11px] font-mono text-zinc-300 border border-white/10">
                {(currentTimeMs / 1000).toFixed(1)}s / {(durationMs / 1000).toFixed(1)}s
              </span>
            </div>

            {/* Animated Word-Level Subtitles Overlay */}
            <div className="relative z-10 text-center px-2 py-4">
              <AnimatePresence mode="wait">
                {currentBlock && (
                  <motion.div
                    key={currentBlock.start_ms}
                    initial={{ opacity: 0, y: 8, scale: 0.95 }}
                    animate={{ opacity: 1, y: 0, scale: 1 }}
                    exit={{ opacity: 0, y: -8 }}
                    transition={{ duration: 0.15 }}
                    className="flex flex-wrap items-center justify-center gap-2"
                  >
                    {currentBlock.words.map((w, idx) => {
                      const isWordActive = currentTimeMs >= w.start_ms && currentTimeMs <= w.end_ms;
                      return (
                        <motion.span
                          key={idx}
                          animate={isWordActive ? { scale: 1.15 } : { scale: 1 }}
                          transition={{ type: "spring", stiffness: 400, damping: 20 }}
                          className={`text-2xl ${currentStyleObj.font} ${
                            isWordActive ? currentStyleObj.highlightColor : currentStyleObj.baseColor
                          }`}
                        >
                          {w.word}
                          {w.emoji && <span className="ml-1 text-2xl">{w.emoji}</span>}
                        </motion.span>
                      );
                    })}
                  </motion.div>
                )}
              </AnimatePresence>
            </div>

            {/* In-Canvas Playback Controls Bar */}
            <div className="relative z-10 p-3 rounded-2xl bg-black/70 backdrop-blur-xl border border-white/10 space-y-2">
              {/* Progress Scrubber */}
              <input
                type="range"
                min="0"
                max={durationMs}
                value={currentTimeMs}
                onChange={(e) => setCurrentTimeMs(Number(e.target.value))}
                className="w-full h-1.5 bg-zinc-800 rounded-lg appearance-none cursor-pointer accent-indigo-500"
              />

              <div className="flex items-center justify-between text-white">
                <button
                  onClick={() => setCurrentTimeMs(0)}
                  className="p-1.5 hover:bg-white/10 rounded-lg transition-colors"
                >
                  <RotateCcw className="w-4 h-4" />
                </button>
                <button
                  onClick={() => setIsPlaying(!isPlaying)}
                  className="p-2 rounded-xl bg-indigo-600 hover:bg-indigo-500 transition-colors shadow-md"
                >
                  {isPlaying ? <Pause className="w-4 h-4" /> : <Play className="w-4 h-4 ml-0.5" />}
                </button>
                <button
                  onClick={() => setIsMuted(!isMuted)}
                  className="p-1.5 hover:bg-white/10 rounded-lg transition-colors"
                >
                  {isMuted ? <VolumeX className="w-4 h-4" /> : <Volume2 className="w-4 h-4" />}
                </button>
              </div>
            </div>

          </div>
        </div>

        {/* ── Studio Controls & Timeline Tweaker ────────── */}
        <div className="lg:col-span-7 space-y-6">
          
          {/* Tabs Selector */}
          <div className="flex items-center gap-2 p-1.5 rounded-2xl bg-[#121624] border border-white/10">
            <button
              onClick={() => setActiveTab("captions")}
              className={`flex-1 py-2.5 px-4 rounded-xl text-xs font-bold transition-all flex items-center justify-center gap-2 ${
                activeTab === "captions"
                  ? "bg-indigo-600 text-white shadow-lg shadow-indigo-500/25"
                  : "text-zinc-400 hover:text-white"
              }`}
            >
              <Type className="w-4 h-4" />
              Caption Styles & Words
            </button>
            <button
              onClick={() => setActiveTab("layout")}
              className={`flex-1 py-2.5 px-4 rounded-xl text-xs font-bold transition-all flex items-center justify-center gap-2 ${
                activeTab === "layout"
                  ? "bg-indigo-600 text-white shadow-lg shadow-indigo-500/25"
                  : "text-zinc-400 hover:text-white"
              }`}
            >
              <Crop className="w-4 h-4" />
              9:16 Speaker Tracking
            </button>
            <button
              onClick={() => setActiveTab("publish")}
              className={`flex-1 py-2.5 px-4 rounded-xl text-xs font-bold transition-all flex items-center justify-center gap-2 ${
                activeTab === "publish"
                  ? "bg-indigo-600 text-white shadow-lg shadow-indigo-500/25"
                  : "text-zinc-400 hover:text-white"
              }`}
            >
              <Send className="w-4 h-4" />
              Multi-Platform Publish
            </button>
          </div>

          {/* ── Tab 1: Caption Presets & Transcript Editor ── */}
          {activeTab === "captions" && (
            <div className="space-y-6 animate-fadeIn">
              
              {/* Presets Grid */}
              <div className="space-y-3">
                <label className="text-xs font-bold uppercase tracking-wider text-zinc-400 flex items-center gap-1.5">
                  <Sparkles className="w-3.5 h-3.5 text-indigo-400" />
                  Viral Subtitle Styles
                </label>
                <div className="grid grid-cols-2 gap-3">
                  {PRESET_STYLES.map((style) => (
                    <button
                      key={style.id}
                      onClick={() => setSelectedStyle(style.id)}
                      className={`p-4 rounded-2xl border text-left transition-all relative overflow-hidden ${
                        selectedStyle === style.id
                          ? "bg-[#181d30] border-indigo-500 ring-2 ring-indigo-500/30"
                          : "bg-[#101424] border-white/5 hover:border-white/20"
                      }`}
                    >
                      <div className="flex items-center justify-between mb-2">
                        <span className="text-sm font-bold text-white">{style.name}</span>
                        {selectedStyle === style.id && (
                          <span className="w-5 h-5 rounded-full bg-indigo-600 flex items-center justify-center text-white text-xs">
                            <Check className="w-3 h-3" />
                          </span>
                        )}
                      </div>
                      <div className={`text-xs px-2.5 py-1.5 rounded-lg bg-black/40 border border-white/5 inline-block ${style.highlightColor}`}>
                        {style.preview}
                      </div>
                    </button>
                  ))}
                </div>
              </div>

              {/* Word-by-Word Timeline Editor */}
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <label className="text-xs font-bold uppercase tracking-wider text-zinc-400 flex items-center gap-1.5">
                    <Clock className="w-3.5 h-3.5 text-indigo-400" />
                    Word-Level Karaoke Timeline
                  </label>
                  <span className="text-xs text-zinc-500">Click word to seek</span>
                </div>

                <div className="space-y-3 max-h-[300px] overflow-y-auto pr-2 custom-scrollbar">
                  {blocks.map((block, bIdx) => (
                    <div
                      key={bIdx}
                      className="p-4 rounded-2xl bg-[#101424] border border-white/5 space-y-3"
                    >
                      <div className="flex items-center justify-between text-xs text-zinc-400 border-b border-white/5 pb-2">
                        <span>Block #{bIdx + 1}</span>
                        <span className="font-mono">{(block.start_ms / 1000).toFixed(1)}s - {(block.end_ms / 1000).toFixed(1)}s</span>
                      </div>
                      <div className="flex flex-wrap gap-2">
                        {block.words.map((word, wIdx) => {
                          const isActive = currentTimeMs >= word.start_ms && currentTimeMs <= word.end_ms;
                          return (
                            <button
                              key={wIdx}
                              onClick={() => setCurrentTimeMs(word.start_ms)}
                              className={`px-3 py-1.5 rounded-xl text-xs font-bold transition-all flex items-center gap-1 ${
                                isActive
                                  ? "bg-gradient-to-r from-amber-500 to-orange-500 text-black scale-105 shadow-md shadow-amber-500/30"
                                  : "bg-white/5 hover:bg-white/10 text-white"
                              }`}
                            >
                              {word.word}
                              {word.emoji && <span>{word.emoji}</span>}
                            </button>
                          );
                        })}
                      </div>
                    </div>
                  ))}
                </div>
              </div>

            </div>
          )}

          {/* ── Tab 2: 9:16 Aspect & Active Speaker Tracking ── */}
          {activeTab === "layout" && (
            <div className="space-y-4 animate-fadeIn">
              <label className="text-xs font-bold uppercase tracking-wider text-zinc-400 flex items-center gap-1.5">
                <Crop className="w-3.5 h-3.5 text-indigo-400" />
                MediaPipe Dynamic Reframing Modes
              </label>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {LAYOUT_MODES.map((mode) => {
                  const Icon = mode.icon;
                  return (
                    <button
                      key={mode.id}
                      onClick={() => setSelectedLayout(mode.id)}
                      className={`p-5 rounded-2xl border text-left transition-all space-y-2 ${
                        selectedLayout === mode.id
                          ? "bg-[#181d30] border-indigo-500 ring-2 ring-indigo-500/30"
                          : "bg-[#101424] border-white/5 hover:border-white/20"
                      }`}
                    >
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2 text-white font-bold text-sm">
                          <Icon className="w-4 h-4 text-indigo-400" />
                          {mode.label}
                        </div>
                        {selectedLayout === mode.id && (
                          <span className="w-5 h-5 rounded-full bg-indigo-600 flex items-center justify-center text-white text-xs">
                            <Check className="w-3 h-3" />
                          </span>
                        )}
                      </div>
                      <p className="text-xs text-zinc-400 leading-relaxed">{mode.desc}</p>
                    </button>
                  );
                })}
              </div>
            </div>
          )}

          {/* ── Tab 3: Multi-Platform Publishing ──────────── */}
          {activeTab === "publish" && (
            <div className="space-y-5 animate-fadeIn p-6 rounded-2xl bg-[#101424] border border-white/5">
              <h3 className="text-base font-bold text-white flex items-center gap-2">
                <Send className="w-4 h-4 text-indigo-400" />
                One-Click Distribution Hub
              </h3>
              
              <div className="space-y-3">
                <div className="flex items-center justify-between p-4 rounded-xl bg-black/40 border border-white/5">
                  <div className="flex items-center gap-3">
                    <div className="w-8 h-8 rounded-lg bg-red-600/20 text-red-400 flex items-center justify-center font-bold text-xs">
                      YT
                    </div>
                    <div>
                      <p className="text-sm font-bold text-white">YouTube Shorts</p>
                      <p className="text-xs text-zinc-500">Connected via OAuth 2.0</p>
                    </div>
                  </div>
                  <input type="checkbox" defaultChecked className="w-4 h-4 accent-indigo-500" />
                </div>

                <div className="flex items-center justify-between p-4 rounded-xl bg-black/40 border border-white/5">
                  <div className="flex items-center gap-3">
                    <div className="w-8 h-8 rounded-lg bg-cyan-600/20 text-cyan-400 flex items-center justify-center font-bold text-xs">
                      TT
                    </div>
                    <div>
                      <p className="text-sm font-bold text-white">TikTok Direct Publishing</p>
                      <p className="text-xs text-zinc-500">Content Posting API v2</p>
                    </div>
                  </div>
                  <input type="checkbox" defaultChecked className="w-4 h-4 accent-indigo-500" />
                </div>

                <div className="flex items-center justify-between p-4 rounded-xl bg-black/40 border border-white/5">
                  <div className="flex items-center gap-3">
                    <div className="w-8 h-8 rounded-lg bg-pink-600/20 text-pink-400 flex items-center justify-center font-bold text-xs">
                      IG
                    </div>
                    <div>
                      <p className="text-sm font-bold text-white">Instagram Reels</p>
                      <p className="text-xs text-zinc-500">Meta Graph API v20.0</p>
                    </div>
                  </div>
                  <input type="checkbox" defaultChecked className="w-4 h-4 accent-indigo-500" />
                </div>
              </div>

              <button className="w-full py-3.5 rounded-xl bg-gradient-to-r from-indigo-600 via-purple-600 to-pink-600 text-white font-bold text-sm shadow-xl shadow-indigo-500/25 hover:scale-[1.01] transition-all">
                Queue Multi-Target Publishing Job
              </button>
            </div>
          )}

        </div>
      </div>
    </div>
  );
}
