"use client";

import { useState, useEffect } from "react";
import { getStreamers, addStreamer, processStreamerVOD, deleteStreamer, updateStreamer } from "@/lib/api";

type Streamer = {
  id: number;
  name: string;
  platform: string;
  channel: string;
  url: string;
  enabled: boolean;
  is_live?: boolean;
  total_clips?: number;
};

export default function StreamersTab() {
  const [streamers, setStreamers] = useState<Streamer[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ name: "", platform: "twitch", channel: "", url: "" });
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  const load = () => {
    setLoading(true);
    getStreamers()
      .then((d: any) => setStreamers(d.streamers || d || []))
      .catch(() => setStreamers([]))
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, []);

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
    } catch (e: any) {
      setError(e.message || "Failed to add streamer");
    }
    setSubmitting(false);
  };

  return (
    <div>
      <div className="section-header" style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between" }}>
        <div>
          <h2 className="section-title">Streamers</h2>
          <p className="section-sub">{streamers.length} source{streamers.length !== 1 ? "s" : ""} configured</p>
        </div>
        <button className="btn-primary" onClick={() => setShowForm(!showForm)}>
          <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><path d="M5 12h14"/><path d="M12 5v14"/></svg>
          Add Streamer
        </button>
      </div>

      {showForm && (
        <form onSubmit={handleAdd} className="card" style={{ padding: "32px", marginBottom: "32px" }}>
          <h3 style={{ fontSize: "18px", fontWeight: 800, marginBottom: "24px", color: "#0f0e17" }}>New Streamer</h3>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "16px" }}>
            <div>
              <label className="label">Name</label>
              <input className="input-field" value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} placeholder="Display name" required />
            </div>
            <div>
              <label className="label">Platform</label>
              <select className="input-field" value={form.platform} onChange={e => setForm({ ...form, platform: e.target.value })} style={{ cursor: "pointer" }}>
                <option value="twitch">Twitch</option>
                <option value="youtube">YouTube</option>
                <option value="kick">Kick</option>
              </select>
            </div>
            <div>
              <label className="label">Channel ID / Handle</label>
              <input className="input-field" value={form.channel} onChange={e => setForm({ ...form, channel: e.target.value })} placeholder="Channel name or ID" required />
            </div>
            <div>
              <label className="label">Stream URL (optional)</label>
              <input className="input-field" value={form.url} onChange={e => setForm({ ...form, url: e.target.value })} placeholder="https://..." />
            </div>
          </div>
          {error && <p style={{ color: "#ef4444", fontSize: "13px", fontWeight: 600, marginTop: "12px" }}>{error}</p>}
          <div style={{ display: "flex", gap: "12px", marginTop: "24px" }}>
            <button type="submit" className="btn-primary" disabled={submitting}>{submitting ? "Adding..." : "Add Streamer"}</button>
            <button type="button" className="btn-secondary" onClick={() => setShowForm(false)}>Cancel</button>
          </div>
        </form>
      )}

      {loading ? (
        <div style={{ padding: "80px", textAlign: "center", color: "#94a3b8", fontWeight: 700 }}>Loading streamers...</div>
      ) : streamers.length === 0 ? (
        <div className="card" style={{ padding: "80px", textAlign: "center", color: "#94a3b8" }}>
          <p style={{ fontSize: "16px", fontWeight: 700, marginBottom: "8px" }}>No streamers yet</p>
          <p style={{ fontSize: "13px" }}>Add a streamer to start monitoring</p>
        </div>
      ) : (
        <div className="grid-3">
          {streamers.map((s) => (
            <div key={s.id} className="card" style={{ padding: "28px" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "20px" }}>
                <div>
                  <h3 style={{ fontSize: "18px", fontWeight: 800, color: "#0f0e17", marginBottom: "4px" }}>{s.name}</h3>
                  <p style={{ fontSize: "12px", fontWeight: 700, color: "#94a3b8", textTransform: "uppercase", letterSpacing: "0.1em" }}>{s.platform} · #{s.channel}</p>
                </div>
                <span className={`badge ${s.is_live ? "badge-live" : "badge-offline"}`}>
                  {s.is_live ? (
                    <span style={{ width: 6, height: 6, borderRadius: "50%", background: "currentColor", display: "inline-block" }} />
                  ) : null}
                  {s.is_live ? "Live" : "Offline"}
                </span>
              </div>
              
              <div style={{ display: "flex", justifyContent: "space-between", paddingTop: "16px", borderTop: "1px solid #f1f2f7", alignItems: "center" }}>
                <div>
                  <p style={{ fontSize: "11px", fontWeight: 700, color: "#94a3b8", textTransform: "uppercase", letterSpacing: "0.1em", marginBottom: "4px" }}>Total Clips</p>
                  <p style={{ fontSize: "22px", fontWeight: 900, color: "#0f0e17" }}>{s.total_clips ?? 0}</p>
                </div>
                <div style={{ display: "flex", flexDirection: "column", gap: "8px", alignItems: "flex-end" }}>
                  <button 
                    className="btn-primary" 
                    style={{ height: "32px", fontSize: "10px", padding: "0 10px", borderRadius: "8px" }}
                    onClick={async () => {
                      try {
                        await processStreamerVOD(s.id);
                        alert(`Started clipping latest stream for ${s.name}!`);
                      } catch (e: any) { alert(e.message); }
                    }}
                  >
                    Clip Latest
                  </button>
                  <div style={{ display: "flex", gap: "6px" }}>
                    <button 
                      className="icon-btn" 
                      title={s.enabled ? "Disable" : "Enable"}
                      onClick={async () => {
                        try {
                          await updateStreamer(s.id, { enabled: !s.enabled });
                          load();
                        } catch (e: any) { alert(e.message); }
                      }}
                      style={{ 
                        width: "28px", height: "28px", 
                        background: s.enabled ? "#f0fdf4" : "#fef2f2", 
                        color: s.enabled ? "#16a34a" : "#ef4444" 
                      }}
                    >
                      <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M18.36 6.64a9 9 0 1 1-12.73 0"/><line x1="12" x2="12" y1="2" y2="12"/></svg>
                    </button>
                    <button 
                      className="icon-btn" 
                      title="Delete"
                      onClick={async () => {
                        if (!confirm(`Delete ${s.name}?`)) return;
                        try {
                          await deleteStreamer(s.id);
                          load();
                        } catch (e: any) { alert(e.message); }
                      }}
                      style={{ width: "28px", height: "28px", background: "#fee2e2", color: "#ef4444" }}
                    >
                      <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M3 6h18"/><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"/><path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"/></svg>
                    </button>
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
