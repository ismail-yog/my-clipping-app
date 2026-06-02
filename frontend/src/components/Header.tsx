"use client";

type Props = {
  connected: boolean;
  onToggleSidebar: () => void;
  title: string;
};

export default function Header({ connected, onToggleSidebar, title }: Props) {
  return (
    <header className="top-header">
      <div style={{ display: "flex", alignItems: "center", gap: "16px" }}>
        <button
          onClick={onToggleSidebar}
          className="icon-btn"
          title="Toggle sidebar"
        >
          <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><line x1="4" x2="20" y1="12" y2="12"/><line x1="4" x2="20" y1="6" y2="6"/><line x1="4" x2="20" y1="18" y2="18"/></svg>
        </button>
        <h2 className="header-title">{title}</h2>
      </div>

      <div className="header-search">
        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/></svg>
        <input placeholder="Search clips, streamers..." />
      </div>

      <div className="header-actions">
        <div className="status-pill">
          <div className="status-dot" style={{ background: connected ? "#22c55e" : "#ef4444", boxShadow: connected ? "0 0 0 3px #dcfce7" : "0 0 0 3px #fee2e2" }} />
          {connected ? "Backend Connected" : "Offline"}
        </div>

        <button className="icon-btn">
          <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9"/><path d="M10.3 21a1.94 1.94 0 0 0 3.4 0"/></svg>
          <span className="badge-dot" />
        </button>

        <button className="header-profile">
          <div className="profile-avatar">A</div>
          <span style={{ fontSize: "13px", fontWeight: 700, color: "#0f0e17" }}>Admin</span>
        </button>
      </div>
    </header>
  );
}
