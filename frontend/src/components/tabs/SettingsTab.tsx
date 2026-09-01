"use client";

import React, { useState, useEffect, useRef } from "react";
import { motion } from "framer-motion";
import {
  Settings,
  Video,
  Cpu,
  Sliders,
  CheckCircle2,
  AlertCircle,
  Save,
  RefreshCw,
  ExternalLink,
  Sparkles,
} from "lucide-react";
import {
  getYouTubeAuthStatus,
  startYouTubeAuth,
  getSettings,
  updateSettings,
} from "@/lib/api";

export default function SettingsTab() {
  const [ytStatus, setYtStatus] = useState<any>(null);
  const [connecting, setConnecting] = useState(false);
  const [connectMsg, setConnectMsg] = useState("");
  const pollRef = useRef<any>(null);

  const [settings, setSettings] = useState({
    max_clips: 3,
    clip_duration: 45,
    download_resolution: 1080,
    parallel_renders: 2,
    use_fast_whisper: true,
    burn_captions: true,
    viral_threshold: 0.4,
    auto_publish: false,
  });
  const [loading, setLoading] = useState(true);
  const [saved, setSaved] = useState(false);
  const [saveError, setSaveError] = useState("");

  const fetchStatus = async () => {
    try {
      const d = await getYouTubeAuthStatus();
      setYtStatus(d);
      if (d.connected) {
        if (pollRef.current) clearInterval(pollRef.current);
        setConnecting(false);
        setConnectMsg("");
      }
    } catch {
      setYtStatus({ connected: false, error: "Cannot reach backend" });
    }
  };

  const fetchConfig = async () => {
    setLoading(true);
    try {
      const d = await getSettings();
      setSettings(d);
    } catch (e: any) {
      console.error("Failed to fetch settings:", e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchStatus();
    fetchConfig();
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  const handleConnectYouTube = async () => {
    setConnecting(true);
    setConnectMsg("Opening Google Authorization in your browser...");
    try {
      const res = await startYouTubeAuth();
      if (res.auth_url) {
        window.open(res.auth_url, "_blank");
      }
      pollRef.current = setInterval(fetchStatus, 3000);
    } catch (e: any) {
      setConnectMsg("Failed to start OAuth flow: " + (e.message || ""));
      setConnecting(false);
    }
  };

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaved(false);
    setSaveError("");
    try {
      await updateSettings(settings);
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
    } catch (err: any) {
      setSaveError(err.message || "Failed to update configuration");
    }
  };

  return (
    <div className="space-y-8 pb-12">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-black text-white tracking-tight">Engine Settings</h2>
          <p className="text-xs text-slate-400">Configure AI models, rendering presets, and OAuth credentials</p>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        {/* Left 2 Cols: Pipeline & Rendering Config */}
        <div className="lg:col-span-2 space-y-6">
          <form onSubmit={handleSave} className="glass-panel p-8 space-y-6 border-indigo-500/20">
            <h3 className="text-base font-bold text-white flex items-center gap-2">
              <Sliders className="w-4 h-4 text-indigo-400" /> Pipeline & Video Parameters
            </h3>

            {saveError && <div className="text-xs text-rose-400">{saveError}</div>}
            {saved && (
              <div className="p-3 rounded-xl bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-xs font-bold flex items-center gap-2">
                <CheckCircle2 className="w-4 h-4" /> Configuration saved successfully!
              </div>
            )}

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
              <div>
                <label className="text-xs font-bold text-slate-400 uppercase">Max Clips per VOD</label>
                <input
                  type="number"
                  min="1"
                  max="10"
                  value={settings.max_clips}
                  onChange={(e) => setSettings({ ...settings, max_clips: parseInt(e.target.value) || 1 })}
                  className="w-full mt-2 bg-[#05070c] border border-white/10 rounded-xl px-4 py-3 text-sm text-white focus:outline-none focus:border-indigo-500"
                />
              </div>

              <div>
                <label className="text-xs font-bold text-slate-400 uppercase">Clip Duration (Seconds)</label>
                <input
                  type="number"
                  min="15"
                  max="90"
                  value={settings.clip_duration}
                  onChange={(e) => setSettings({ ...settings, clip_duration: parseInt(e.target.value) || 45 })}
                  className="w-full mt-2 bg-[#05070c] border border-white/10 rounded-xl px-4 py-3 text-sm text-white focus:outline-none focus:border-indigo-500"
                />
              </div>

              <div>
                <label className="text-xs font-bold text-slate-400 uppercase">Download Resolution</label>
                <select
                  value={settings.download_resolution}
                  onChange={(e) => setSettings({ ...settings, download_resolution: parseInt(e.target.value) || 1080 })}
                  className="w-full mt-2 bg-[#05070c] border border-white/10 rounded-xl px-4 py-3 text-sm text-white focus:outline-none focus:border-indigo-500"
                >
                  <option value={1080}>1080p (FHD)</option>
                  <option value={720}>720p (HD Fast)</option>
                </select>
              </div>

              <div>
                <label className="text-xs font-bold text-slate-400 uppercase">Parallel Render Workers</label>
                <input
                  type="number"
                  min="1"
                  max="4"
                  value={settings.parallel_renders}
                  onChange={(e) => setSettings({ ...settings, parallel_renders: parseInt(e.target.value) || 2 })}
                  className="w-full mt-2 bg-[#05070c] border border-white/10 rounded-xl px-4 py-3 text-sm text-white focus:outline-none focus:border-indigo-500"
                />
              </div>
            </div>

            {/* Checkbox Toggles */}
            <div className="pt-4 border-t border-white/5 space-y-4">
              <label className="flex items-center gap-3 cursor-pointer">
                <input
                  type="checkbox"
                  checked={settings.burn_captions}
                  onChange={(e) => setSettings({ ...settings, burn_captions: e.target.checked })}
                  className="w-4 h-4 rounded text-indigo-600 bg-slate-900 border-white/20 focus:ring-indigo-500"
                />
                <span className="text-sm font-semibold text-slate-200">
                  Burn Animated Captions (Arial Black + Yellow Word Highlights)
                </span>
              </label>

              <label className="flex items-center gap-3 cursor-pointer">
                <input
                  type="checkbox"
                  checked={settings.auto_publish}
                  onChange={(e) => setSettings({ ...settings, auto_publish: e.target.checked })}
                  className="w-4 h-4 rounded text-indigo-600 bg-slate-900 border-white/20 focus:ring-indigo-500"
                />
                <span className="text-sm font-semibold text-slate-200">
                  Auto-Publish Viral Highlights (Score &ge; 80%) to YouTube Shorts
                </span>
              </label>
            </div>

            <div className="flex justify-end pt-4">
              <button type="submit" className="btn-primary-neon py-3 px-6 text-sm">
                <Save className="w-4 h-4" /> Save Engine Settings
              </button>
            </div>
          </form>
        </div>

        {/* Right Col: YouTube OAuth Connection */}
        <div className="space-y-6">
          <div className="glass-panel p-6 space-y-4 border-red-500/20">
            <h3 className="text-base font-bold text-white flex items-center gap-2">
              <Video className="w-5 h-5 text-red-500" /> YouTube Shorts Account
            </h3>

            <div className="p-4 rounded-2xl bg-white/[0.02] border border-white/5 space-y-2 text-xs">
              <div className="flex justify-between">
                <span className="text-slate-400">Connection Status</span>
                <span
                  className={`font-bold ${
                    ytStatus?.connected ? "text-emerald-400" : "text-slate-400"
                  }`}
                >
                  {ytStatus?.connected ? "Connected" : "Disconnected"}
                </span>
              </div>
              {ytStatus?.channel && (
                <div className="flex justify-between">
                  <span className="text-slate-400">Channel</span>
                  <span className="font-bold text-white">{ytStatus.channel}</span>
                </div>
              )}
            </div>

            {connectMsg && <p className="text-xs text-indigo-300">{connectMsg}</p>}

            <button
              onClick={handleConnectYouTube}
              disabled={connecting}
              className="w-full btn-secondary-glass py-3 text-xs justify-center font-bold"
            >
              {connecting ? (
                <>
                  <RefreshCw className="w-4 h-4 animate-spin" />
                  <span>Waiting for Google Auth...</span>
                </>
              ) : ytStatus?.connected ? (
                <span>Reconnect YouTube Account</span>
              ) : (
                <span>Connect YouTube Account</span>
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
