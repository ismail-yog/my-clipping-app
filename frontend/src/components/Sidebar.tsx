"use client";

const TABS = [
  { id: "dashboard",  label: "Dashboard",       icon: <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><rect width="7" height="9" x="3" y="3" rx="1"/><rect width="7" height="5" x="14" y="3" rx="1"/><rect width="7" height="9" x="14" y="12" rx="1"/><rect width="7" height="5" x="3" y="16" rx="1"/></svg> },
  { id: "generator",  label: "Clip Generator",  icon: <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><polygon points="23 7 16 12 23 17 23 7"/><rect x="1" y="5" width="15" height="14" rx="2" ry="2"/></svg> },
  { id: "clips",      label: "Clips",           icon: <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><rect width="18" height="18" x="3" y="3" rx="2" ry="2"/><circle cx="9" cy="9" r="2"/><path d="m21 15-3.086-3.086a2 2 0 0 0-2.828 0L6 21"/></svg> },
  { id: "streamers",  label: "Streamers",       icon: <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="m22 8-6 4 6 4V8Z"/><rect width="14" height="12" x="2" y="6" rx="2" ry="2"/></svg> },
  { id: "pipeline",   label: "Auto-Mode",       icon: <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/></svg> },
  { id: "uploads",    label: "Uploads",         icon: <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M17.5 19a3.5 3.5 0 0 0 .5-6.912a5 5 0 1 0-9.398-2.076a3.502 3.502 0 0 0-1.107 6.838"/><path d="M12 12v9"/><path d="m15 18-3 3-3-3"/></svg> },
  { id: "settings",   label: "Settings",        icon: <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"/><circle cx="12" cy="12" r="3"/></svg> },
];

type Props = {
  activeTab: string;
  onTabChange: (tab: string) => void;
  pendingCount: number;
  isOpen: boolean;
};

export default function Sidebar({ activeTab, onTabChange, pendingCount, isOpen }: Props) {
  if (!isOpen) return null;
  return (
    <aside className="sidebar">
      <div className="sidebar-logo">
        <h1>Stream<br/><span>Clip AI</span></h1>
        <p>Automation Hub</p>
      </div>

      {/* CTA — Clip Generator highlight */}
      <div style={{ padding: "0 20px 24px" }}>
        <button
          className="sidebar-new-btn"
          onClick={() => onTabChange("generator")}
          style={{
            background: activeTab === "generator"
              ? "linear-gradient(135deg, #5b3cc4, #6d4aff)"
              : "linear-gradient(135deg, #6d4aff, #a78bfa)",
            opacity: 1
          }}
        >
          <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><polygon points="5 3 19 12 5 21 5 3"/></svg>
          Paste URL to Generate Clips
        </button>
      </div>

      <nav className="sidebar-nav">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            onClick={() => onTabChange(tab.id)}
            className={`sidebar-nav-item ${activeTab === tab.id ? "active" : ""}`}
          >
            <span className="nav-icon">{tab.icon}</span>
            <span style={{ flex: 1 }}>{tab.label}</span>
            {tab.id === "clips" && pendingCount > 0 && (
              <span style={{
                background: "#ef4444",
                color: "white",
                fontSize: "10px",
                fontWeight: 800,
                padding: "2px 7px",
                borderRadius: "100px",
                lineHeight: 1.5,
              }}>
                {pendingCount}
              </span>
            )}
          </button>
        ))}
      </nav>

      <div className="sidebar-footer">
        <div className="sidebar-user">
          <div className="sidebar-avatar">A</div>
          <div>
            <div style={{ fontSize: "13px", fontWeight: 800, color: "#0f0e17" }}>Admin</div>
            <div style={{ fontSize: "11px", fontWeight: 700, color: "#94a3b8", marginTop: "2px" }}>Dashboard Root</div>
          </div>
        </div>
      </div>
    </aside>
  );
}
