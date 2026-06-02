"use client";

import { useState, useEffect } from "react";
import { getUploads } from "@/lib/api";

type Upload = {
  id?: string;
  title?: string;
  streamer_name?: string;
  success?: boolean;
  uploaded_at?: number;
  video_url?: string;
};

export default function UploadsTab() {
  const [uploads, setUploads] = useState<Upload[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getUploads()
      .then((d: any) => setUploads(d.uploads || d || []))
      .catch(() => setUploads([]))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div>
      <div className="section-header">
        <h2 className="section-title">Uploads</h2>
        <p className="section-sub">History of clips uploaded to YouTube</p>
      </div>

      <div className="card" style={{ overflow: "hidden" }}>
        {loading ? (
          <div style={{ padding: "80px", textAlign: "center", color: "#94a3b8", fontWeight: 700 }}>Loading uploads...</div>
        ) : uploads.length === 0 ? (
          <div style={{ padding: "80px", textAlign: "center", color: "#94a3b8" }}>
            <p style={{ fontSize: "16px", fontWeight: 700, marginBottom: "8px" }}>No uploads yet</p>
            <p style={{ fontSize: "13px" }}>Approved clips will be uploaded automatically</p>
          </div>
        ) : (
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ background: "#f8f9fc", borderBottom: "1px solid #f1f2f7" }}>
                {["Status", "Streamer", "Title", "Date", "Link"].map(h => (
                  <th key={h} style={{ padding: "16px 24px", textAlign: "left", fontSize: "11px", fontWeight: 800, color: "#94a3b8", textTransform: "uppercase", letterSpacing: "0.12em" }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {uploads.map((u, i) => (
                <tr key={i} style={{ borderBottom: "1px solid #f1f2f7" }}
                  onMouseEnter={e => (e.currentTarget.style.background = "#faf9ff")}
                  onMouseLeave={e => (e.currentTarget.style.background = "transparent")}
                >
                  <td style={{ padding: "16px 24px" }}>
                    <span className={`badge ${u.success ? "badge-success" : "badge-failed"}`}>
                      {u.success ? "Uploaded" : "Failed"}
                    </span>
                  </td>
                  <td style={{ padding: "16px 24px", fontSize: "14px", fontWeight: 700, color: "#0f0e17" }}>{u.streamer_name || "—"}</td>
                  <td style={{ padding: "16px 24px", fontSize: "14px", color: "#0f0e17", maxWidth: "280px" }}>
                    <p style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{u.title || "Untitled"}</p>
                  </td>
                  <td style={{ padding: "16px 24px", fontSize: "13px", color: "#94a3b8", fontWeight: 600 }}>
                    {u.uploaded_at ? new Date(u.uploaded_at * 1000).toLocaleDateString() : "—"}
                  </td>
                  <td style={{ padding: "16px 24px" }}>
                    {u.video_url ? (
                      <a href={u.video_url} target="_blank" rel="noopener noreferrer"
                        style={{ fontSize: "13px", fontWeight: 700, color: "#6d4aff", textDecoration: "none", display: "flex", alignItems: "center", gap: "4px" }}
                        onMouseEnter={e => (e.currentTarget.style.textDecoration = "underline")}
                        onMouseLeave={e => (e.currentTarget.style.textDecoration = "none")}
                      >
                        View
                        <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>
                      </a>
                    ) : <span style={{ color: "#cbd5e1", fontSize: "13px" }}>—</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
