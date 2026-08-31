"use client";

import { useState, useEffect, useRef } from "react";
import { processVOD, getVODJobProgress, getClips, getClipVideoUrl, approveClip, rejectClip, cancelVODJob } from "@/lib/api";
import VideoModal from "@/components/VideoModal";

type JobState = {
  jobId: string;
  url: string;
  progress: number;
  status: string;
};

type Clip = {
  clip_id: string;
  moment_score: number;
  emotion: string;
  duration: number;
  title: string;
  transcript: string;
  has_captions: number;
  status: string;
  created_at: number;
  streamer_name: string;
};

export default function ClipGeneratorTab() {
  const [url, setUrl] = useState("");
  const [layoutType, setLayoutType] = useState("gamer");
  const [error, setError] = useState("");
  const [job, setJob] = useState<JobState | null>(null);
  const [generatedClips, setGeneratedClips] = useState<Clip[]>([]);
  const [playingClip, setPlayingClip] = useState<Clip | null>(null);
  const pollRef = useRef<NodeJS.Timeout | null>(null);

  // Poll job progress
  useEffect(() => {
    if (!job || job.progress >= 100) return;

    const check = async () => {
      try {
        const d: any = await getVODJobProgress(job.jobId);
        setJob(prev => prev ? { ...prev, progress: d.progress ?? prev.progress, status: d.status ?? prev.status } : null);
        loadGeneratedClips();

        if (d.progress >= 100 || d.status === "completed") {
          if (pollRef.current) clearInterval(pollRef.current);
        }
      } catch { /* ignore poll errors */ }
    };

    check();
    pollRef.current = setInterval(check, 2000);
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, [job?.jobId, job?.progress]);

  const loadGeneratedClips = async () => {
    try {
      const d: any = await getClips();
      const vodClips = (d.clips || [])
        .filter((c: Clip) => c.streamer_name === "VOD_Clipper")
        .sort((a: Clip, b: Clip) => b.created_at - a.created_at);
      setGeneratedClips(vodClips);
    } catch { /* ignore */ }
  };

  useEffect(() => { loadGeneratedClips(); }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = url.trim();
    if (!trimmed) return;
    setError("");

    try {
      const d: any = await processVOD(trimmed, layoutType);
      setJob({ jobId: d.job_id, url: trimmed, progress: 5, status: "Starting..." });
    } catch (e: any) {
      setError(e.message || "Failed to start processing");
    }
  };

  const copyMetadata = (clip: any) => {
    const text = `Title: ${clip.title || "Viral Clip"}\n\nDescription: ${clip.description || clip.transcript || ""}\n\nTags: ${(clip.tags || ["shorts", "viral"]).join(", ")}`;
    navigator.clipboard.writeText(text);
    alert("Metadata copied to clipboard!");
  };

  const scoreColor = (score: number) => {
    if (score >= 0.8) return "#ef4444";
    if (score >= 0.6) return "#f59e0b";
    return "#94a3b8";
  };

  const emotionLabel = (e: string) => {
    const map: Record<string, string> = {
      joy: "Joy", anger: "Anger", surprise: "Surprise",
      sadness: "Sadness", fear: "Fear", neutral: "Neutral",
    };
    return map[e] || e || "—";
  };

  const handleApprove = async (id: string) => {
    try {
      await approveClip(id);
      setGeneratedClips(prev => prev.map(c => c.clip_id === id ? { ...c, status: "approved" } : c));
    } catch (e: any) { alert(e.message); }
  };

  const handleReject = async (id: string) => {
    try {
      await rejectClip(id);
      setGeneratedClips(prev => prev.filter(c => c.clip_id !== id));
    } catch (e: any) { alert(e.message); }
  };

  return (
    <div>
      <div className="section-header">
        <h2 className="section-title">Manual Clip Generator</h2>
        <p className="section-sub">Paste a YouTube URL to extract viral moments manually</p>
      </div>

      {/* URL Input */}
      <div className="card" style={{ padding: "32px", marginBottom: "32px", background: "linear-gradient(135deg, #ffffff, #faf9ff)" }}>
        <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: "20px" }}>
          <div>
            <label className="label">Video URL</label>
            <div style={{ display: "flex", gap: "12px", marginBottom: "16px" }}>
              <input
                className="input-field"
                value={url}
                onChange={e => setUrl(e.target.value)}
                placeholder="https://www.youtube.com/watch?v=..."
                disabled={!!job && job.progress < 100}
                style={{ flex: 1, height: "56px", fontSize: "15px" }}
              />
              <button
                type="submit"
                className="btn-primary"
                disabled={!url.trim() || (!!job && job.progress < 100)}
                style={{ flexShrink: 0, minWidth: "220px", height: "56px" }}
              >
                {job && job.progress < 100 ? (
                  <>
                    <span className="spinner" />
                    Processing...
                  </>
                ) : "Generate Viral Clips"}
              </button>
            </div>
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
            <label className="label">Layout Style</label>
            <div style={{ display: "flex", gap: "16px" }}>
              <label style={{ 
                flex: 1, display: "flex", alignItems: "center", gap: "12px", 
                padding: "16px 20px", border: `2px solid ${layoutType === "gamer" ? "#6d4aff" : "#e2e8f0"}`, 
                borderRadius: "14px", cursor: "pointer", background: layoutType === "gamer" ? "#f5f3ff" : "white",
                transition: "all 0.2s", fontWeight: 700
              }}>
                <input 
                  type="radio" 
                  name="layoutType" 
                  value="gamer" 
                  checked={layoutType === "gamer"} 
                  onChange={() => setLayoutType("gamer")} 
                  style={{ accentColor: "#6d4aff", width: "18px", height: "18px" }}
                />
                <div>
                  <p style={{ fontSize: "14px", color: "#0f0e17", margin: 0 }}>Gamer Style (Split-Screen)</p>
                  <p style={{ fontSize: "12px", color: "#64748b", margin: "2px 0 0 0", fontWeight: 400 }}>Webcam on top, gameplay on bottom</p>
                </div>
              </label>

              <label style={{ 
                flex: 1, display: "flex", alignItems: "center", gap: "12px", 
                padding: "16px 20px", border: `2px solid ${layoutType === "basic" ? "#6d4aff" : "#e2e8f0"}`, 
                borderRadius: "14px", cursor: "pointer", background: layoutType === "basic" ? "#f5f3ff" : "white",
                transition: "all 0.2s", fontWeight: 700
              }}>
                <input 
                  type="radio" 
                  name="layoutType" 
                  value="basic" 
                  checked={layoutType === "basic"} 
                  onChange={() => setLayoutType("basic")} 
                  style={{ accentColor: "#6d4aff", width: "18px", height: "18px" }}
                />
                <div>
                  <p style={{ fontSize: "14px", color: "#0f0e17", margin: 0 }}>Basic 9:16 Crop</p>
                  <p style={{ fontSize: "12px", color: "#64748b", margin: "2px 0 0 0", fontWeight: 400 }}>Standard portrait center crop</p>
                </div>
              </label>
            </div>
          </div>

          {error && (
            <p style={{ fontSize: "13px", fontWeight: 700, color: "#ef4444", background: "#fee2e2", padding: "10px 16px", borderRadius: "10px" }}>{error}</p>
          )}
        </form>
      </div>

      {/* Step-by-Step Progress Tracker */}
      {job && (
        <div className="card" style={{ padding: "32px", marginBottom: "32px", border: "1px solid #c4b5fd", background: "linear-gradient(135deg, #faf5ff, #f3e8ff)", borderRadius: "20px", boxShadow: "0 10px 30px rgba(109,74,255,0.08)" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "20px" }}>
            <div>
              <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
                <span className="live-dot" />
                <h3 style={{ fontSize: "16px", fontWeight: 900, color: "#3b0764", margin: 0 }}>
                  {job.progress >= 100 ? "Processing Complete!" : "Pipeline Execution Active"}
                </h3>
              </div>
              <p style={{ fontSize: "13px", color: "#6b21a8", fontWeight: 600, marginTop: "4px" }}>
                {job.status || "Executing automated clipping steps..."}
              </p>
            </div>

            <div style={{ display: "flex", alignItems: "center", gap: "16px" }}>
              {job.progress < 100 && job.status !== "Cancelled" && (
                <button
                  onClick={async () => {
                    if (confirm("Are you sure you want to cancel this processing job?")) {
                      try {
                        if (job.jobId && job.jobId !== "submitting") await cancelVODJob(job.jobId);
                        setJob(prev => prev ? { ...prev, status: "Cancelled", progress: 0 } : null);
                      } catch (e: any) {
                        alert(`Failed to cancel: ${e.message}`);
                      }
                    }
                  }}
                  style={{
                    background: "#fee2e2", color: "#b91c1c", border: "none",
                    borderRadius: "8px", padding: "8px 16px", fontSize: "12px",
                    fontWeight: 800, cursor: "pointer", transition: "all 0.2s"
                  }}
                >
                  Cancel Task
                </button>
              )}
              <div style={{ textAlign: "right" }}>
                <span style={{ fontSize: "28px", fontWeight: 900, color: "#6d4aff" }}>{job.progress}%</span>
              </div>
            </div>
          </div>

          {/* Progress Bar Track */}
          <div className="progress-track" style={{ background: "#e9d5ff", height: "14px", borderRadius: "100px", overflow: "hidden", marginBottom: "24px" }}>
            <div className="progress-fill" style={{ width: `${job.progress}%`, background: "linear-gradient(90deg, #8b5cf6, #6d4aff, #a855f7)", transition: "width 0.4s ease-out" }} />
          </div>

          {/* Step Pipeline Breakdown */}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: "12px" }}>
            {[
              { step: 1, name: "1. VOD Download", min: 0, max: 25 },
              { step: 2, name: "2. Whisper Audio", min: 25, max: 55 },
              { step: 3, name: "3. Viral Scoring", min: 55, max: 65 },
              { step: 4, name: "4. Clip Rendering", min: 65, max: 90 },
              { step: 5, name: "5. SEO & Thumbnails", min: 90, max: 100 },
            ].map(s => {
              const isDone = job.progress >= s.max;
              const isActive = job.progress >= s.min && job.progress < s.max;
              return (
                <div key={s.step} style={{
                  padding: "12px 14px", borderRadius: "12px",
                  background: isDone ? "#dcfce7" : isActive ? "#ffffff" : "#f3e8ff",
                  border: `1.5px solid ${isDone ? "#86efac" : isActive ? "#9333ea" : "#e9d5ff"}`,
                  boxShadow: isActive ? "0 4px 12px rgba(147,51,234,0.15)" : "none",
                  transition: "all 0.3s ease"
                }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "4px" }}>
                    <span style={{ fontSize: "10px", fontWeight: 900, textTransform: "uppercase", color: isDone ? "#15803d" : isActive ? "#7e22ce" : "#a855f7" }}>
                      {isDone ? "✓ Done" : isActive ? "▶ Active" : "Pending"}
                    </span>
                  </div>
                  <p style={{ fontSize: "12px", fontWeight: 800, color: isDone ? "#166534" : isActive ? "#581c87" : "#7e22ce", margin: 0, lineHeight: 1.2 }}>
                    {s.name}
                  </p>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Generated Clips */}
      {generatedClips.length > 0 && (
        <div>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "24px" }}>
            <h3 style={{ fontSize: "18px", fontWeight: 900, color: "#0f0e17" }}>Extracted Highlights</h3>
            <button className="btn-secondary" onClick={loadGeneratedClips} style={{ height: "36px", fontSize: "12px" }}>Refresh List</button>
          </div>

          <div className="grid-4">
            {generatedClips.map(clip => (
              <div key={clip.clip_id} className="clip-card" style={{ display: "flex", flexDirection: "column", borderRadius: "16px", overflow: "hidden" }}>
                {/* Preview Thumbnail */}
                <div 
                  style={{ position: "relative", width: "100%", aspectRatio: "9/16", background: "#000", cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center" }}
                  onClick={() => setPlayingClip(clip)}
                >
                  <div className="play-btn-tiny">
                    <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="white" stroke="none"><polygon points="5 3 19 12 5 21 5 3"/></svg>
                  </div>
                  <div style={{ 
                    position: "absolute", top: "10px", right: "10px", 
                    background: clip.moment_score >= 0.8 ? "#ef4444" : "rgba(0,0,0,0.6)", 
                    color: "white", fontSize: "10px", fontWeight: 900, padding: "2px 8px", borderRadius: "100px" 
                  }}>
                    {Math.round(clip.moment_score * 100)}%
                  </div>
                  <div style={{ position: "absolute", bottom: "10px", right: "10px", background: "rgba(0,0,0,0.7)", color: "white", fontSize: "10px", fontWeight: 800, padding: "2px 6px", borderRadius: "6px" }}>
                    {Math.floor(clip.duration)}s
                  </div>
                </div>

                {/* Info (Compact) */}
                <div style={{ padding: "14px", flex: 1, display: "flex", flexDirection: "column" }}>
                  <div style={{ display: "flex", gap: "6px", marginBottom: "8px" }}>
                    <span className="badge" style={{ fontSize: "9px", background: "#f3f0ff", color: "#6d4aff" }}>{emotionLabel(clip.emotion)}</span>
                    <span className={`badge ${clip.status === "approved" ? "badge-success" : clip.status === "rejected" ? "badge-failed" : "badge-processing"}`} style={{ fontSize: "9px" }}>
                      {clip.status}
                    </span>
                  </div>

                  <h4 style={{ fontSize: "13px", fontWeight: 800, color: "#0f0e17", marginBottom: "12px", lineHeight: 1.3, height: "34px", overflow: "hidden" }}>
                    {clip.title}
                  </h4>

                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "6px", marginBottom: "6px" }}>
                    <button className="btn-approve" style={{ height: "32px", fontSize: "11px", padding: "0" }} onClick={() => handleApprove(clip.clip_id)}>Approve</button>
                    <button className="btn-reject" style={{ height: "32px", fontSize: "11px", padding: "0" }} onClick={() => handleReject(clip.clip_id)}>Reject</button>
                  </div>

                  <div style={{ display: "flex", gap: "6px" }}>
                    <button className="btn-secondary" style={{ flex: 1, height: "32px", fontSize: "11px", padding: "0" }} onClick={() => copyMetadata(clip)}>Meta</button>
                    <button className="btn-secondary" style={{ flex: 1, height: "32px", fontSize: "11px", padding: "0" }} onClick={() => setPlayingClip(clip)}>Watch</button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {playingClip && (
        <VideoModal clipId={playingClip.clip_id} title={playingClip.title} onClose={() => setPlayingClip(null)} />
      )}

      <style>{`
        .grid-4 {
          display: grid;
          grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
          gap: 20px;
        }
        .play-btn-tiny {
          width: 44px; height: 44px; border-radius: 50%; background: rgba(109,74,255,0.85);
          display: flex; alignItems: center; justifyContent: center;
          box-shadow: 0 8px 20px rgba(109,74,255,0.3); transition: all 0.2s;
        }
        .clip-card:hover .play-btn-tiny { transform: scale(1.1); background: #6d4aff; }
        .spinner { width: 16px; height: 16px; border: 2.5px solid rgba(255,255,255,0.3); border-top-color: white; border-radius: 50%; animation: spin 0.8s linear infinite; margin-right: 8px; }
        @keyframes spin { to { transform: rotate(360deg); } }
      `}</style>
    </div>
  );
}
