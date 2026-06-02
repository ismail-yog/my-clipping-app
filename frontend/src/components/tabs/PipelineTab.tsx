"use client";

import { useState, useEffect } from "react";
import { getStatus, startPipeline, stopPipeline } from "@/lib/api";

export default function PipelineTab() {
  const [isActive, setIsActive] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [fetching, setFetching] = useState(true);

  useEffect(() => {
    getStatus()
      .then((d: any) => setIsActive(!!d.pipeline_active))
      .catch(() => {})
      .finally(() => setFetching(false));
  }, []);

  const handleToggle = async () => {
    setIsLoading(true);
    try {
      if (isActive) await stopPipeline();
      else await startPipeline();
      setIsActive(!isActive);
    } catch (e) { console.error(e); }
    setIsLoading(false);
  };

  return (
    <div>
      <div className="section-header">
        <h2 className="section-title">Auto-Mode</h2>
        <p className="section-sub">Autonomous extraction and clip generation engine</p>
      </div>

      <div className="card" style={{ padding: "60px 40px", textAlign: "center", maxWidth: "560px", margin: "0 auto" }}>
        {/* Status indicator */}
        <div style={{
          width: "100px",
          height: "100px",
          borderRadius: "50%",
          background: isActive ? "linear-gradient(135deg, #6d4aff, #a855f7)" : "#f1f2f7",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          margin: "0 auto 32px",
          boxShadow: isActive ? "0 0 0 16px rgba(109,74,255,0.08), 0 12px 30px rgba(109,74,255,0.25)" : "none",
          transition: "all 0.4s ease",
        }}>
          <svg xmlns="http://www.w3.org/2000/svg" width="40" height="40" viewBox="0 0 24 24" fill="none" stroke={isActive ? "white" : "#cbd5e1"} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/>
          </svg>
        </div>

        <h3 style={{ fontSize: "26px", fontWeight: 900, color: "#0f0e17", marginBottom: "8px" }}>
          {fetching ? "Checking..." : isActive ? "Pipeline Running" : "Pipeline Stopped"}
        </h3>
        <p style={{ fontSize: "14px", color: "#64748b", fontWeight: 600, marginBottom: "40px", lineHeight: 1.6 }}>
          {isActive
            ? "The system is actively monitoring streamers and extracting highlight clips."
            : "Enable auto-mode to start monitoring streamers and generating clips automatically."}
        </p>

        <button
          onClick={handleToggle}
          disabled={isLoading || fetching}
          className="btn-primary"
          style={{
            width: "100%",
            height: "56px",
            fontSize: "16px",
            background: isActive ? "#1e1b4b" : undefined,
            boxShadow: isActive ? "none" : undefined,
          }}
        >
          {isLoading ? "Please wait..." : isActive ? "Stop Pipeline" : "Start Pipeline"}
        </button>
      </div>
    </div>
  );
}
