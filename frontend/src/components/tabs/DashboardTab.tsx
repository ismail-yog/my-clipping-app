"use client";

import { useState, useEffect } from "react";
import { getStatus, getVODProgress, cancelVODJob } from "@/lib/api";
import { connectWebSocket, StatusUpdate } from "@/lib/ws";

type Stats = {
  total_clips: number;
  pending_review: number;
  approved: number;
  uploaded: number;
  rejected: number;
  failed: number;
  total_uploads: number;
  uploads_today: number;
  pending_jobs: number;
  active_sessions: number;
  total_streamers: number;
  enabled_streamers: number;
};

export default function DashboardTab() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [vodJobs, setVodJobs] = useState<Record<string, any>>({});
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const load = async () => {
      try {
        const [statusData, vodData] = await Promise.all([
          getStatus(),
          getVODProgress()
        ]);
        setStats(statusData.stats);
        setVodJobs(vodData.jobs || {});
      } catch (e) {
        console.error("Failed to load dashboard stats", e);
      } finally {
        setLoading(false);
      }
    };

    load();

    // Listen for real-time updates
    const ws = connectWebSocket((data: StatusUpdate) => {
      if (data.vod_progress) setVodJobs(data.vod_progress);
      // Refresh stats on message too
      getStatus().then(d => setStats(d.stats)).catch(() => {});
    });

    return () => { if (ws) ws.close(); };
  }, []);

  if (loading && !stats) {
    return (
      <div style={{ display: "flex", justifyContent: "center", alignItems: "center", height: "400px" }}>
        <div className="spinner" style={{ width: "40px", height: "40px", borderTopColor: "#6d4aff" }} />
      </div>
    );
  }

  const statCards = [
    { label: "Pending Review", value: stats?.pending_review ?? 0, icon: "👀", color: "#7c3aed" },
    { label: "Total Clips", value: stats?.total_clips ?? 0, icon: "🎬", color: "#2563eb" },
    { label: "Approved", value: stats?.approved ?? 0, icon: "✅", color: "#16a34a" },
    { label: "Uploaded", value: stats?.uploaded ?? 0, icon: "📤", color: "#0891b2" },
    { label: "Today's Uploads", value: stats?.uploads_today ?? 0, icon: "🚀", color: "#f59e0b" },
    { label: "Active Streamers", value: stats?.enabled_streamers ?? 0, icon: "📡", color: "#dc2626" },
  ];

  return (
    <div className="animate-in">
      <div className="section-header">
        <h2 className="section-title">Command Center</h2>
        <p className="section-sub">Overview of your automated clipping pipeline and performance</p>
      </div>

      {/* Stats Grid */}
      <div className="grid-3" style={{ marginBottom: "40px" }}>
        {statCards.map(stat => (
          <div key={stat.label} className="card" style={{ padding: "24px", display: "flex", alignItems: "center", gap: "20px" }}>
            <div style={{ 
              width: "56px", height: "56px", borderRadius: "16px", background: `${stat.color}15`,
              display: "flex", alignItems: "center", justifyContent: "center", fontSize: "24px"
            }}>
              {stat.icon}
            </div>
            <div>
              <p style={{ fontSize: "13px", fontWeight: 700, color: "#94a3b8", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: "4px" }}>
                {stat.label}
              </p>
              <p style={{ fontSize: "28px", fontWeight: 900, color: "#0f0e17" }}>{stat.value}</p>
            </div>
          </div>
        ))}
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr", gap: "32px" }}>
        {/* Active Jobs */}
        <div>
          <h3 style={{ fontSize: "18px", fontWeight: 900, color: "#0f0e17", marginBottom: "20px" }}>Active Processing Tasks</h3>
          {Object.keys(vodJobs).length > 0 ? (
            <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
              {Object.entries(vodJobs).map(([id, job]: [string, any]) => (
                <div key={id} className="card" style={{ padding: "20px" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "12px" }}>
                    <div style={{ display: "flex", gap: "12px", alignItems: "center" }}>
                      <div className="spinner" style={{ width: "16px", height: "16px", borderTopColor: "#6d4aff" }} />
                      <span style={{ fontSize: "14px", fontWeight: 800, color: "#0f0e17", maxWidth: "300px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                        {job.url}
                      </span>
                    </div>
                    <span style={{ fontSize: "14px", fontWeight: 900, color: "#6d4aff" }}>{job.progress}%</span>
                  </div>
                  <div className="progress-track" style={{ height: "8px" }}>
                    <div className="progress-fill" style={{ width: `${job.progress}%` }} />
                  </div>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: "8px" }}>
                    <p style={{ fontSize: "12px", color: "#94a3b8", fontWeight: 700, margin: 0, textTransform: "capitalize" }}>
                      Status: {job.status}
                    </p>
                    {job.progress < 100 && job.status !== "Cancelled" && job.status !== "failed" && (
                      <button
                        onClick={async () => {
                          if (confirm("Are you sure you want to cancel this processing job?")) {
                            try {
                              await cancelVODJob(id);
                              setVodJobs(prev => {
                                const next = { ...prev };
                                if (next[id]) {
                                  next[id] = { ...next[id], status: "Cancelled", progress: 0 };
                                }
                                return next;
                              });
                            } catch (e: any) {
                              alert(`Failed to cancel: ${e.message}`);
                            }
                          }
                        }}
                        style={{
                          background: "#fee2e2",
                          color: "#ef4444",
                          border: "none",
                          borderRadius: "6px",
                          padding: "4px 12px",
                          fontSize: "11px",
                          fontWeight: 800,
                          cursor: "pointer",
                          transition: "all 0.2s"
                        }}
                        onMouseOver={(e) => {
                          e.currentTarget.style.background = "#fecaca";
                        }}
                        onMouseOut={(e) => {
                          e.currentTarget.style.background = "#fee2e2";
                        }}
                      >
                        Cancel Task
                      </button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div style={{ padding: "40px", textAlign: "center", background: "#f8f9fc", borderRadius: "24px", border: "2px dashed #e2e8f0" }}>
              <p style={{ fontSize: "14px", color: "#94a3b8", fontWeight: 700 }}>No active processing tasks at the moment.</p>
            </div>
          )}
        </div>

        {/* Pipeline Health */}
        <div>
          <h3 style={{ fontSize: "18px", fontWeight: 900, color: "#0f0e17", marginBottom: "20px" }}>System Health</h3>
          <div className="card" style={{ padding: "24px" }}>
            <div style={{ display: "flex", flexDirection: "column", gap: "20px" }}>
              <HealthItem label="API Server" status="online" />
              <HealthItem label="Transcription Engine" status={stats ? "online" : "checking"} />
              <HealthItem label="Ollama AI" status={stats ? "online" : "checking"} />
              <HealthItem label="Worker Thread" status={stats && stats.active_sessions > 0 ? "active" : "idle"} />
            </div>
            
            <div style={{ marginTop: "32px", padding: "16px", background: "#f0fdf4", borderRadius: "14px", border: "1px solid #bbf7d0" }}>
              <p style={{ fontSize: "13px", fontWeight: 800, color: "#166534", display: "flex", alignItems: "center", gap: "8px" }}>
                <span style={{ width: "8px", height: "8px", borderRadius: "50%", background: "#22c55e" }} />
                Pipeline is fully operational
              </p>
            </div>
          </div>
        </div>
      </div>

      <style>{`
        .animate-in {
          animation: slideUp 0.4s ease-out;
        }
        @keyframes slideUp {
          from { opacity: 0; transform: translateY(10px); }
          to { opacity: 1; transform: translateY(0); }
        }
        .spinner {
          width: 20px; height: 20px; border: 3px solid #f1f2f7;
          border-top-color: #6d4aff; border-radius: 50%; animation: spin 1s linear infinite;
        }
        @keyframes spin { to { transform: rotate(360deg); } }
      `}</style>
    </div>
  );
}

function HealthItem({ label, status }: { label: string; status: string }) {
  const colors: Record<string, string> = {
    online: "#22c55e",
    active: "#6d4aff",
    checking: "#f59e0b",
    idle: "#94a3b8",
    offline: "#ef4444"
  };
  return (
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
      <span style={{ fontSize: "14px", fontWeight: 700, color: "#475569" }}>{label}</span>
      <span style={{ 
        fontSize: "11px", fontWeight: 900, textTransform: "uppercase", letterSpacing: "0.05em",
        padding: "4px 10px", borderRadius: "100px", background: `${colors[status] || "#94a3b8"}15`,
        color: colors[status] || "#94a3b8"
      }}>
        {status}
      </span>
    </div>
  );
}
