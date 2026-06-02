"use client";

import { useState, useEffect } from "react";
import { getClips, approveClip, rejectClip } from "@/lib/api";
import VideoModal from "@/components/VideoModal";

type Clip = {
  clip_id: string;
  title: string;
  streamer_name: string;
  status: string;
  duration?: number;
  thumbnail?: string;
  moment_score?: number;
  created_at?: number;
};

export default function ClipsTab() {
  const [clips, setClips] = useState<Clip[]>([]);
  const [filter, setFilter] = useState("all");
  const [loading, setLoading] = useState(true);
  const [playingClip, setPlayingClip] = useState<Clip | null>(null);

  const load = (status?: string) => {
    setLoading(true);
    getClips(status)
      .then((d: any) => {
        const list = d.clips || d || [];
        setClips(list);
      })
      .catch(() => setClips([]))
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, []);

  const handleFilter = (f: string) => {
    setFilter(f);
    load(f === "all" ? undefined : f);
  };

  const handleApprove = async (id: string) => {
    try {
      await approveClip(id);
      // Immediately remove from the current view if we are in 'pending_review' filter
      if (filter === "pending_review") {
        setClips(prev => prev.filter(c => c.clip_id !== id));
      } else {
        setClips(prev => prev.map(c => c.clip_id === id ? { ...c, status: "approved" } : c));
      }
    } catch (e) { console.error(e); }
  };

  const handleReject = async (id: string) => {
    try {
      await rejectClip(id);
      // Always remove from view because it is physically deleted
      setClips(prev => prev.filter(c => c.clip_id !== id));
    } catch (e) { console.error(e); }
  };

  const filters = [
    { id: "all", label: "All" },
    { id: "pending_review", label: "Pending" },
    { id: "approved", label: "Approved" },
  ];

  return (
    <div>
      <div className="section-header" style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "32px" }}>
        <div>
          <h2 className="section-title" style={{ fontSize: "24px" }}>Review Station</h2>
          <p className="section-sub">{clips.length} clip{clips.length !== 1 ? "s" : ""} in view</p>
        </div>
        <div className="tab-pills" style={{ background: "#f1f2f7", padding: "4px", borderRadius: "12px" }}>
          {filters.map(f => (
            <button 
              key={f.id} 
              className={`tab-pill ${filter === f.id ? "active" : ""}`} 
              onClick={() => handleFilter(f.id)}
              style={{ padding: "6px 16px", fontSize: "13px", fontWeight: 700 }}
            >
              {f.label}
            </button>
          ))}
        </div>
      </div>

      {loading ? (
        <div style={{ padding: "80px", textAlign: "center", color: "#94a3b8", fontWeight: 700 }}>Loading...</div>
      ) : clips.length === 0 ? (
        <div className="card" style={{ padding: "80px", textAlign: "center", color: "#94a3b8" }}>
          <p style={{ fontSize: "16px", fontWeight: 700, marginBottom: "8px" }}>No clips found</p>
          <p style={{ fontSize: "13px" }}>Check back later for new highlights</p>
        </div>
      ) : (
        <div className="grid-4">
          {clips.map((clip) => (
            <div key={clip.clip_id} className="clip-card" style={{ padding: "0", overflow: "hidden", borderRadius: "16px" }}>
              {/* Preview Area (Smaller) */}
              <div 
                style={{ aspectRatio: "9/16", background: "#000", position: "relative", cursor: "pointer" }}
                onClick={() => setPlayingClip(clip)}
              >
                <div style={{ width: "100%", height: "100%", display: "flex", alignItems: "center", justifyContent: "center" }}>
                  <div className="play-btn-tiny">
                    <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="white" stroke="none"><polygon points="5 3 19 12 5 21 5 3"/></svg>
                  </div>
                </div>
                {clip.moment_score != null && (
                  <span style={{ 
                    position: "absolute", top: "10px", right: "10px", 
                    background: clip.moment_score >= 0.8 ? "#ef4444" : "rgba(0,0,0,0.6)", 
                    color: "white", fontSize: "10px", fontWeight: 900, padding: "2px 8px", borderRadius: "100px",
                    boxShadow: clip.moment_score >= 0.8 ? "0 4px 10px rgba(239,68,68,0.4)" : "none"
                  }}>
                    {Math.round(clip.moment_score * 100)}%
                  </span>
                )}
                <span className={`badge ${clip.status === "approved" ? "badge-success" : clip.status === "rejected" ? "badge-failed" : "badge-processing"}`}
                  style={{ position: "absolute", top: "10px", left: "10px", fontSize: "9px", padding: "2px 6px" }}>
                  {clip.status}
                </span>
              </div>

              {/* Minimal Info */}
              <div style={{ padding: "12px" }}>
                <p style={{ fontSize: "10px", fontWeight: 800, color: "#6d4aff", textTransform: "uppercase", marginBottom: "4px" }}>
                  {clip.streamer_name}
                </p>
                <h3 style={{ fontSize: "13px", fontWeight: 800, color: "#0f0e17", lineHeight: 1.3, marginBottom: "12px", height: "34px", overflow: "hidden" }}>
                  {clip.title || "Untitled"}
                </h3>

                <div style={{ display: "flex", gap: "6px" }}>
                  {clip.status === "pending_review" && (
                    <>
                      <button 
                        className="btn-approve" 
                        style={{ flex: 1, height: "32px", fontSize: "11px", padding: "0" }} 
                        onClick={(e) => { e.stopPropagation(); handleApprove(clip.clip_id); }}
                      >
                        Approve
                      </button>
                      <button 
                        className="btn-reject" 
                        style={{ flex: 1, height: "32px", fontSize: "11px", padding: "0" }} 
                        onClick={(e) => { e.stopPropagation(); handleReject(clip.clip_id); }}
                      >
                        Reject
                      </button>
                    </>
                  )}
                  {clip.status !== "pending_review" && (
                     <button className="btn-secondary" style={{ flex: 1, height: "32px", fontSize: "11px" }} onClick={() => setPlayingClip(clip)}>
                        Watch
                     </button>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {playingClip && (
        <VideoModal 
          clipId={playingClip.clip_id} 
          title={playingClip.title} 
          onClose={() => setPlayingClip(null)} 
        />
      )}

      <style>{`
        .grid-4 {
          display: grid;
          grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
          gap: 20px;
        }
        .play-btn-tiny {
          width: 40px; height: 40px; border-radius: 50%; background: rgba(109,74,255,0.8);
          display: flex; alignItems: center; justifyContent: center;
          transition: all 0.2s;
        }
        .clip-card:hover .play-btn-tiny { transform: scale(1.1); background: #6d4aff; }
      `}</style>
    </div>
  );
}
