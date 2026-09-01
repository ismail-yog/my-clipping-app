"use client";

import React, { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Tv,
  Plus,
  Trash2,
  Play,
  CheckCircle2,
  ExternalLink,
  Radio,
  Sparkles,
  Zap,
} from "lucide-react";
import {
  getStreamers,
  addStreamer,
  processStreamerVOD,
  deleteStreamer,
  updateStreamer,
} from "@/lib/api";

export default function StreamersTab() {
  const [streamers, setStreamers] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ name: "", platform: "twitch", channel: "", url: "" });
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  const load = async () => {
    setLoading(true);
    try {
      const data = await getStreamers();
      setStreamers(data.streamers || data || []);
    } catch (e) {
      setStreamers([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const handleAdd = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.name || !form.channel) return;
    setSubmitting(true);
    setError("");
    try {
      await addStreamer({ ...form, enabled: true });
      setForm({ name: "", platform: "twitch", channel: "", url: "" });
      setShowForm(false);
      load();
    } catch (err: any) {
      setError(err.message || "Failed to add streamer");
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = async (id: number) => {
    try {
      await deleteStreamer(id);
      load();
    } catch (e) {
      console.error(e);
    }
  };

  const handleToggle = async (s: any) => {
    try {
      await updateStreamer(s.id, { enabled: !s.enabled });
      load();
    } catch (e) {
      console.error(e);
    }
  };

  return (
    <div className="space-y-8 pb-12">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-black text-white tracking-tight">Monitored Streamers</h2>
          <p className="text-xs text-slate-400">
            {streamers.length} channel{streamers.length !== 1 ? "s" : ""} active in rolling buffer
          </p>
        </div>
        <button
          onClick={() => setShowForm(!showForm)}
          className="btn-primary-neon py-2.5 px-4 text-xs"
        >
          <Plus className="w-4 h-4" /> Add Channel
        </button>
      </div>

      {/* ── Add Streamer Modal / Dropdown ─────────── */}
      <AnimatePresence>
        {showForm && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            className="glass-panel p-6 border-indigo-500/30"
          >
            <form onSubmit={handleAdd} className="space-y-4">
              <h3 className="text-sm font-bold text-white">Add Channel to Continuous Monitoring</h3>
              {error && <div className="text-xs text-rose-400">{error}</div>}

              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                <div>
                  <label className="text-[11px] font-bold text-slate-400 uppercase">Streamer Name</label>
                  <input
                    type="text"
                    value={form.name}
                    onChange={(e) => setForm({ ...form, name: e.target.value })}
                    placeholder="e.g. Kai Cenat"
                    className="w-full mt-1 bg-[#05070c] border border-white/10 rounded-xl px-4 py-2.5 text-xs text-white focus:outline-none focus:border-indigo-500"
                  />
                </div>
                <div>
                  <label className="text-[11px] font-bold text-slate-400 uppercase">Platform</label>
                  <select
                    value={form.platform}
                    onChange={(e) => setForm({ ...form, platform: e.target.value })}
                    className="w-full mt-1 bg-[#05070c] border border-white/10 rounded-xl px-4 py-2.5 text-xs text-white focus:outline-none focus:border-indigo-500"
                  >
                    <option value="twitch">Twitch</option>
                    <option value="kick">Kick</option>
                    <option value="youtube">YouTube</option>
                  </select>
                </div>
                <div>
                  <label className="text-[11px] font-bold text-slate-400 uppercase">Channel / URL</label>
                  <input
                    type="text"
                    value={form.channel}
                    onChange={(e) =>
                      setForm({
                        ...form,
                        channel: e.target.value,
                        url: form.url || `https://${form.platform}.tv/${e.target.value}`,
                      })
                    }
                    placeholder="username or URL"
                    className="w-full mt-1 bg-[#05070c] border border-white/10 rounded-xl px-4 py-2.5 text-xs text-white focus:outline-none focus:border-indigo-500"
                  />
                </div>
              </div>

              <div className="flex justify-end gap-3 pt-2">
                <button
                  type="button"
                  onClick={() => setShowForm(false)}
                  className="btn-secondary-glass py-2 px-4 text-xs"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={submitting}
                  className="btn-primary-neon py-2 px-5 text-xs"
                >
                  {submitting ? "Adding..." : "Save Streamer"}
                </button>
              </div>
            </form>
          </motion.div>
        )}
      </AnimatePresence>

      {/* ── Streamer Cards Grid ──────────────────────── */}
      {loading ? (
        <div className="glass-panel p-16 text-center text-slate-400 font-bold text-sm">
          Loading Streamers...
        </div>
      ) : streamers.length === 0 ? (
        <div className="glass-panel p-16 text-center space-y-3">
          <Tv className="w-12 h-12 text-slate-600 mx-auto" />
          <p className="text-slate-300 font-bold text-sm">No streamers configured.</p>
          <p className="text-xs text-slate-500">Click "Add Channel" to start 24/7 stream monitoring.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
          {streamers.map((s) => (
            <div
              key={s.id}
              className="glass-panel p-6 space-y-4 hover:border-indigo-500/40 transition-all flex flex-col justify-between"
            >
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-[10px] font-extrabold uppercase px-2.5 py-1 rounded-lg bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
                    {s.platform}
                  </span>
                  <div className="flex items-center gap-2">
                    <span
                      className={`w-2 h-2 rounded-full ${
                        s.is_live ? "bg-emerald-400 animate-ping" : "bg-slate-600"
                      }`}
                    />
                    <span className="text-xs font-bold text-slate-400">
                      {s.is_live ? "LIVE" : "OFFLINE"}
                    </span>
                  </div>
                </div>

                <div>
                  <h3 className="text-lg font-bold text-white">{s.name}</h3>
                  <p className="text-xs font-mono text-slate-400 truncate">{s.url}</p>
                </div>
              </div>

              <div className="flex items-center justify-between pt-4 border-t border-white/5">
                <button
                  onClick={() => handleToggle(s)}
                  className={`text-xs font-bold px-3 py-1.5 rounded-xl border transition-all ${
                    s.enabled
                      ? "bg-emerald-500/10 text-emerald-300 border-emerald-500/30"
                      : "bg-slate-800 text-slate-400 border-slate-700"
                  }`}
                >
                  {s.enabled ? "Active" : "Paused"}
                </button>

                <div className="flex items-center gap-2">
                  <a
                    href={s.url}
                    target="_blank"
                    rel="noreferrer"
                    className="p-2 rounded-xl bg-white/5 hover:bg-white/10 text-slate-300 transition-colors"
                  >
                    <ExternalLink className="w-3.5 h-3.5" />
                  </a>
                  <button
                    onClick={() => handleDelete(s.id)}
                    className="p-2 rounded-xl bg-rose-500/10 hover:bg-rose-500/20 text-rose-400 border border-rose-500/20 transition-colors"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
