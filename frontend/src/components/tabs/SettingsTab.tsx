"use client";

import { useState, useEffect, useRef } from "react";
import { 
  getYouTubeAuthStatus, 
  startYouTubeAuth, 
  getSettings, 
  updateSettings 
} from "@/lib/api";

type YTStatus = {
  connected: boolean;
  channel?: string;
  pending?: boolean;
  error?: string | null;
};

export default function SettingsTab() {
  const [ytStatus, setYtStatus]     = useState<YTStatus | null>(null);
  const [connecting, setConnecting] = useState(false);
  const [connectMsg, setConnectMsg] = useState("");
  const pollRef = useRef<NodeJS.Timeout | null>(null);

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

  // ── Status polling ────────────────────────────────────────────────────────
  const fetchStatus = async () => {
    try {
      const d: YTStatus = await getYouTubeAuthStatus();
      setYtStatus(d);
      if (d.connected) {
        stopPoll();
        setConnecting(false);
        setConnectMsg("");
      }
    } catch {
      setYtStatus({ connected: false, error: "Cannot reach backend" });
    }
  };

  const fetchSettings = async () => {
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

  const startPoll = () => {
    if (pollRef.current) return;
    pollRef.current = setInterval(fetchStatus, 2500);
  };

  const stopPoll = () => {
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
  };

  useEffect(() => {
    fetchStatus();
    fetchSettings();
    return stopPoll;
  }, []);

  // ── Connect button ────────────────────────────────────────────────────────
  const handleConnect = async () => {
    setConnecting(true);
    setConnectMsg("Opening browser — sign in with Google...");
    try {
      await startYouTubeAuth();
      startPoll(); 
    } catch (e: any) {
      setConnectMsg(e.message || "Failed to start auth");
      setConnecting(false);
    }
  };

  const handleDisconnect = () => {
    setYtStatus({ connected: false });
    setConnectMsg("Disconnected from UI. To fully revoke, delete youtube_token.json on the server.");
  };

  const handleSave = async () => {
    setSaved(false);
    setSaveError("");
    try {
      await updateSettings(settings);
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
    } catch (e: any) {
      setSaveError(e.message || "Failed to save settings");
    }
  };

  const updateField = (f: string, v: any) => {
    setSettings(prev => ({ ...prev, [f]: v }));
  };

  /* ── Render ──────────────────────────────────────────────────────────────── */
  const isConnected = ytStatus?.connected === true;
  const isPending   = connecting || ytStatus?.pending === true;

  if (loading) return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "center", padding: "100px" }}>
      <div className="spinner" style={{ borderTopColor: "#6d4aff" }} />
    </div>
  );

  return (
    <div>
      <div className="section-header">
        <h2 className="section-title">Settings</h2>
        <p className="section-sub">Integrations and operational parameters</p>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: "24px", maxWidth: "640px", paddingBottom: "100px" }}>

        {/* .env notice */}
        <div style={{
          display: "flex", gap: "14px", alignItems: "flex-start",
          background: "#fefce8", border: "1px solid #fde68a",
          borderRadius: "16px", padding: "18px 22px",
        }}>
          <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#d97706" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink: 0, marginTop: "1px" }}>
            <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
            <line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>
          </svg>
          <div>
            <p style={{ fontSize: "13px", fontWeight: 700, color: "#92400e", marginBottom: "3px" }}>API keys stored in .env</p>
            <p style={{ fontSize: "12px", color: "#a16207", lineHeight: 1.5 }}>
              Mistral, Twitch, and YouTube credentials are loaded from{" "}
              <code style={{ fontFamily: "monospace", background: "#fef9c3", padding: "1px 5px", borderRadius: "4px" }}>streamclipper/.env</code>.
              Edit that file to change keys.
            </p>
          </div>
        </div>

        {/* YouTube Auth card */}
        <div className="card" style={{ padding: "32px" }}>
          <h3 style={{ fontSize: "16px", fontWeight: 800, color: "#0f0e17", marginBottom: "20px" }}>
            YouTube Authorization
          </h3>

          <div style={{ display: "flex", alignItems: "center", gap: "10px", marginBottom: "24px" }}>
            <div style={{
              width: "10px", height: "10px", borderRadius: "50%", flexShrink: 0,
              background: ytStatus == null ? "#d1d5db"
                : isConnected ? "#22c55e"
                : isPending  ? "#f59e0b"
                : "#ef4444",
              boxShadow: isConnected ? "0 0 0 3px #dcfce7" : isPending ? "0 0 0 3px #fef3c7" : "none",
            }} />
            <p style={{ fontSize: "14px", fontWeight: 600, color: "#64748b" }}>
              {ytStatus == null
                ? "Checking..."
                : isConnected
                ? `Connected — ${ytStatus.channel ?? "YouTube account"}`
                : isPending
                ? "Waiting for Google sign-in..."
                : `Not connected — ${ytStatus.error ?? "click Connect to authorize"}`}
            </p>
          </div>

          {isConnected ? (
            <div style={{ display: "flex", gap: "12px", alignItems: "center" }}>
              <div style={{
                flex: 1, display: "flex", alignItems: "center", gap: "10px",
                background: "#f0fdf4", border: "1px solid #bbf7d0",
                borderRadius: "12px", padding: "14px 18px",
              }}>
                <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#16a34a" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
                <p style={{ fontSize: "13px", fontWeight: 700, color: "#15803d" }}>
                  Authorized. Token auto-renews — no re-login needed.
                </p>
              </div>
              <button className="btn-secondary" onClick={handleDisconnect} style={{ flexShrink: 0 }}>
                Disconnect
              </button>
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
              <div style={{ background: "#f8f9fc", borderRadius: "12px", padding: "16px 18px" }}>
                <p style={{ fontSize: "12px", fontWeight: 700, color: "#374151", marginBottom: "8px" }}>How it works:</p>
                <ol style={{ paddingLeft: "18px", margin: 0, display: "flex", flexDirection: "column", gap: "6px" }}>
                  <li style={{ fontSize: "12px", color: "#64748b", fontWeight: 600 }}>Click Connect — your browser opens Google sign-in automatically</li>
                  <li style={{ fontSize: "12px", color: "#64748b", fontWeight: 600 }}>Sign in with your Google account and click Allow</li>
                  <li style={{ fontSize: "12px", color: "#64748b", fontWeight: 600 }}>Done — token saved permanently, never need to sign in again</li>
                </ol>
              </div>

              <button
                className="btn-primary"
                onClick={handleConnect}
                disabled={isPending}
                style={{ width: "100%" }}
              >
                {isPending ? (
                  <>
                    <span className="spinner" />
                    Waiting for browser sign-in...
                  </>
                ) : (
                  <>
                    <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10"/><polyline points="12 8 16 12 12 16"/><line x1="8" y1="12" x2="16" y2="12"/></svg>
                    Connect YouTube
                  </>
                )}
              </button>
            </div>
          )}
        </div>

        {/* VOD Generation Settings */}
        <div className="card" style={{ padding: "32px" }}>
          <h3 style={{ fontSize: "16px", fontWeight: 800, color: "#0f0e17", marginBottom: "24px" }}>VOD Generation</h3>
          <div style={{ display: "flex", flexDirection: "column", gap: "28px" }}>
            
            {/* Resolution */}
            <div>
              <label className="label">Download Resolution</label>
              <select 
                className="input-field" 
                value={settings.download_resolution} 
                onChange={e => updateField("download_resolution", parseInt(e.target.value))}
                style={{ height: "48px" }}
              >
                <option value={720}>720p (Faster Processing)</option>
                <option value={1080}>1080p (High Quality)</option>
                <option value={1440}>1440p (2K Resolution)</option>
                <option value={2160}>2160p (4K Resolution)</option>
              </select>
            </div>

            {/* Max Clips & Parallel */}
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "20px" }}>
              <div>
                <label className="label">Max Clips per Video</label>
                <input 
                  type="number" className="input-field" 
                  value={settings.max_clips} 
                  onChange={e => updateField("max_clips", parseInt(e.target.value))}
                />
              </div>
              <div>
                <label className="label">Parallel Renders</label>
                <input 
                  type="number" className="input-field" 
                  value={settings.parallel_renders} 
                  onChange={e => updateField("parallel_renders", parseInt(e.target.value))}
                />
              </div>
            </div>

            {/* Threshold */}
            <div>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "12px" }}>
                <div>
                  <label className="label" style={{ marginBottom: "2px" }}>Viral Score Threshold</label>
                  <p style={{ fontSize: "12px", color: "#94a3b8", fontWeight: 600 }}>
                    Clips scoring below this are automatically skipped
                  </p>
                </div>
                <span style={{ fontSize: "20px", fontWeight: 900, color: "#6d4aff" }}>
                  {Math.round(settings.viral_threshold * 100)}%
                </span>
              </div>
              <input
                type="range" min="0.1" max="0.9" step="0.05"
                value={settings.viral_threshold}
                onChange={e => updateField("viral_threshold", parseFloat(e.target.value))}
                style={{ width: "100%", accentColor: "#6d4aff", cursor: "pointer" }}
              />
            </div>

            {/* Burn Captions */}
            <div style={{
              display: "flex", alignItems: "center", justifyContent: "space-between",
              padding: "18px 20px", background: "#f8f9fc", borderRadius: "14px",
            }}>
              <div>
                <p style={{ fontSize: "14px", fontWeight: 700, color: "#0f0e17" }}>Burn Dynamic Captions</p>
                <p style={{ fontSize: "12px", color: "#94a3b8", fontWeight: 600, marginTop: "3px" }}>
                  Automatically add word-level highlighted subtitles to clips
                </p>
              </div>
              <button className={`toggle ${settings.burn_captions ? "on" : "off"}`} onClick={() => updateField("burn_captions", !settings.burn_captions)}>
                <div className="toggle-knob" />
              </button>
            </div>
          </div>
        </div>

        <div style={{ position: "sticky", bottom: "32px", zIndex: 10 }}>
          <div style={{ 
            display: "flex", alignItems: "center", gap: "16px", 
            background: "white", padding: "16px 24px", borderRadius: "20px", 
            boxShadow: "0 10px 40px rgba(0,0,0,0.1)", border: "1px solid rgba(0,0,0,0.05)"
          }}>
            <button className="btn-primary" style={{ minWidth: "160px" }} onClick={handleSave}>
              Save All Settings
            </button>
            {saved && (
              <span style={{ fontSize: "13px", fontWeight: 800, color: "#16a34a", display: "flex", alignItems: "center", gap: "6px" }}>
                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
                Changes Saved Permanently
              </span>
            )}
            {saveError && (
              <span style={{ fontSize: "13px", fontWeight: 700, color: "#ef4444" }}>{saveError}</span>
            )}
          </div>
        </div>
      </div>

      <style>{`
        .spinner {
          width: 16px; height: 16px; border: 2.5px solid rgba(0,0,0,0.1);
          border-top-color: white; border-radius: 50%; animation: spin 0.8s linear infinite;
        }
        @keyframes spin { to { transform: rotate(360deg); } }
      `}</style>
    </div>
  );
}
