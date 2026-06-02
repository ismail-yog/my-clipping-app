"use client";

import { useState } from "react";
import { processVOD } from "@/lib/api";

export default function VODTab({ progressData }: { progressData: Record<string, any> }) {
  const [url, setUrl] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [success, setSuccess] = useState(false);
  const [error, setError] = useState("");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!url.trim()) return;
    setIsLoading(true);
    setError(""); setSuccess(false);
    try {
      await processVOD(url.trim());
      setSuccess(true);
      setUrl("");
    } catch (e: any) {
      setError(e.message || "Failed to queue VOD");
    }
    setIsLoading(false);
  };

  const jobs = Object.entries(progressData);

  return (
    <div>
      <div className="section-header">
        <h2 className="section-title">VOD Processing</h2>
        <p className="section-sub">Submit a video URL for AI highlight extraction</p>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "32px", alignItems: "start" }}>
        {/* Submit form */}
        <div className="card" style={{ padding: "36px" }}>
          <h3 style={{ fontSize: "18px", fontWeight: 800, color: "#0f0e17", marginBottom: "6px" }}>Submit VOD</h3>
          <p style={{ fontSize: "13px", color: "#94a3b8", fontWeight: 600, marginBottom: "28px" }}>YouTube, Twitch, or Kick archive URL</p>

          <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
            <div>
              <label className="label">Video URL</label>
              <input
                className="input-field"
                value={url}
                onChange={e => setUrl(e.target.value)}
                placeholder="https://youtube.com/watch?v=..."
                required
              />
            </div>

            {error && <p style={{ color: "#ef4444", fontSize: "13px", fontWeight: 600 }}>{error}</p>}
            {success && <p style={{ color: "#16a34a", fontSize: "13px", fontWeight: 600 }}>VOD queued successfully!</p>}

            <button type="submit" className="btn-primary" disabled={isLoading || !url.trim()} style={{ width: "100%" }}>
              {isLoading ? "Submitting..." : "Process VOD"}
            </button>
          </form>
        </div>

        {/* Progress queue */}
        <div>
          <h3 style={{ fontSize: "16px", fontWeight: 800, color: "#0f0e17", marginBottom: "16px" }}>
            Processing Queue {jobs.length > 0 && <span style={{ color: "#6d4aff" }}>({jobs.length})</span>}
          </h3>

          {jobs.length === 0 ? (
            <div className="card" style={{ padding: "40px", textAlign: "center", color: "#94a3b8" }}>
              <p style={{ fontSize: "14px", fontWeight: 700 }}>Queue is empty</p>
              <p style={{ fontSize: "12px", marginTop: "4px" }}>Submit a VOD to see progress</p>
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
              {jobs.map(([id, data]) => (
                <div key={id} className="card" style={{ padding: "24px" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "12px" }}>
                    <p style={{ fontSize: "12px", fontWeight: 700, color: "#94a3b8", fontFamily: "monospace" }}>{id.slice(0, 16)}...</p>
                    <span style={{ fontSize: "16px", fontWeight: 900, color: "#6d4aff" }}>{data.progress ?? 0}%</span>
                  </div>
                  <div className="progress-track">
                    <div className="progress-fill" style={{ width: `${data.progress ?? 0}%` }} />
                  </div>
                  <p style={{ fontSize: "12px", fontWeight: 600, color: "#94a3b8", marginTop: "8px", textTransform: "capitalize" }}>
                    {data.status || "Processing"}
                  </p>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
