"use client";

import { getClipVideoUrl } from "@/lib/api";

type Props = {
  clipId: string;
  title: string;
  onClose: () => void;
};

export default function VideoModal({ clipId, title, onClose }: Props) {
  return (
    <div style={{
      position: "fixed", top: 0, left: 0, right: 0, bottom: 0,
      background: "rgba(0,0,0,0.85)", backdropFilter: "blur(8px)",
      display: "flex", alignItems: "center", justifyContent: "center",
      zIndex: 9999, padding: "20px"
    }}>
      <div className="card animate-in" style={{ 
        width: "100%", maxWidth: "500px", padding: "0", background: "#000",
        overflow: "hidden", borderRadius: "24px", boxShadow: "0 20px 50px rgba(0,0,0,0.5)"
      }}>
        <div style={{ 
          padding: "16px 24px", background: "white", display: "flex", 
          justifyContent: "space-between", alignItems: "center" 
        }}>
          <h3 style={{ fontSize: "16px", fontWeight: 800, color: "#0f0e17" }}>{title}</h3>
          <button onClick={onClose} className="icon-btn" style={{ background: "#f1f2f7" }}>
            <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><path d="M18 6 6 18M6 6l12 12"/></svg>
          </button>
        </div>
        
        <div style={{ position: "relative", width: "100%", aspectRatio: "9/16" }}>
          <video 
            src={getClipVideoUrl(clipId)} 
            controls 
            autoPlay 
            style={{ width: "100%", height: "100%", objectFit: "contain" }}
          />
        </div>
      </div>

      <style>{`
        .animate-in { animation: zoomIn 0.3s ease-out; }
        @keyframes zoomIn {
          from { opacity: 0; transform: scale(0.95); }
          to { opacity: 1; transform: scale(1); }
        }
      `}</style>
    </div>
  );
}
