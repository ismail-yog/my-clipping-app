"use client";

import { useState, useEffect } from "react";
import { connectWebSocket, StatusUpdate } from "@/lib/ws";
import { getStatus } from "@/lib/api";

import Header from "@/components/Header";
import Sidebar from "@/components/Sidebar";
import DashboardTab from "@/components/tabs/DashboardTab";
import ClipGeneratorTab from "@/components/tabs/ClipGeneratorTab";
import StreamersTab from "@/components/tabs/StreamersTab";
import PipelineTab from "@/components/tabs/PipelineTab";
import ClipsTab from "@/components/tabs/ClipsTab";
import UploadsTab from "@/components/tabs/UploadsTab";
import SettingsTab from "@/components/tabs/SettingsTab";

const TAB_TITLES: Record<string, string> = {
  dashboard: "Dashboard",
  generator: "Clip Generator",
  streamers: "Streamers",
  pipeline: "Auto-Mode",
  clips: "Clips",
  uploads: "Uploads",
  settings: "Settings",
};

export default function Dashboard() {
  const [activeTab, setActiveTab] = useState("dashboard");
  const [connected, setConnected] = useState(false);
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const [pendingCount, setPendingCount] = useState(0);
  const [vodProgress, setVodProgress] = useState<Record<string, any>>({});

  // WebSocket for real-time updates
  useEffect(() => {
    const ws = connectWebSocket((data: StatusUpdate) => {
      setConnected(true);
      setPendingCount(data.pending_review);
      if (data.vod_progress) setVodProgress(data.vod_progress);
    });
    return () => { if (ws) ws.close(); };
  }, []);

  // Initial status fetch
  useEffect(() => {
    getStatus()
      .then((data: any) => {
        setConnected(true);
        setPendingCount(data.stats?.pending_review ?? 0);
      })
      .catch(() => setConnected(false));
  }, []);

  const sidebarWidth = isSidebarOpen ? 268 : 0;

  return (
    <div className="dashboard-layout">
      <Sidebar
        isOpen={isSidebarOpen}
        activeTab={activeTab}
        onTabChange={setActiveTab}
        pendingCount={pendingCount}
      />

      <div className="main-content" style={{ marginLeft: sidebarWidth }}>
        <Header
          connected={connected}
          onToggleSidebar={() => setIsSidebarOpen(!isSidebarOpen)}
          title={TAB_TITLES[activeTab] ?? "Dashboard"}
        />

        <main style={{ padding: "40px", maxWidth: "1400px", width: "100%" }}>
          <div className="page-content">
            {activeTab === "dashboard" && <DashboardTab />}
            {activeTab === "generator" && <ClipGeneratorTab />}
            {activeTab === "streamers" && <StreamersTab />}
            {activeTab === "pipeline"  && <PipelineTab />}
            {activeTab === "clips"     && <ClipsTab />}
            {activeTab === "uploads"   && <UploadsTab />}
            {activeTab === "settings"  && <SettingsTab />}
          </div>
        </main>
      </div>
    </div>
  );
}
