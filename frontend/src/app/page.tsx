"use client";

import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { connectWebSocket, StatusUpdate } from "@/lib/ws";
import { getStatus } from "@/lib/api";

import Header from "@/components/Header";
import Sidebar from "@/components/Sidebar";
import DashboardTab from "@/components/tabs/DashboardTab";
import EditorTab from "@/components/tabs/EditorTab";
import ClipGeneratorTab from "@/components/tabs/ClipGeneratorTab";
import StreamersTab from "@/components/tabs/StreamersTab";
import PipelineTab from "@/components/tabs/PipelineTab";
import ClipsTab from "@/components/tabs/ClipsTab";
import UploadsTab from "@/components/tabs/UploadsTab";
import SettingsTab from "@/components/tabs/SettingsTab";

const TAB_TITLES: Record<string, string> = {
  dashboard: "Overview & Realtime Radar",
  editor: "LumiClip Studio & Interactive Editor",
  generator: "AI Viral Clip Factory",
  streamers: "Stream Channels Hub",
  pipeline: "Autonomous Engine & Audio Wave",
  clips: "Review Vault & High-CTR Shorts",
  uploads: "YouTube & Multi-Platform Uploads",
  settings: "Engine & Hardware Configuration",
};

export default function Dashboard() {
  const [activeTab, setActiveTab] = useState("generator");
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
    return () => {
      if (ws) ws.close();
    };
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

  const sidebarWidth = isSidebarOpen ? 280 : 80;

  return (
    <div className="dashboard-layout">
      {/* ── Ambient Motion Backdrop ─────────────────── */}
      <div className="ambient-bg">
        <div className="ambient-orb ambient-orb-1" />
        <div className="ambient-orb ambient-orb-2" />
        <div className="ambient-orb ambient-orb-3" />
      </div>
      <div className="cyber-grid" />

      {/* ── Sidebar Navigation ──────────────────────── */}
      <Sidebar
        isOpen={isSidebarOpen}
        activeTab={activeTab}
        onTabChange={setActiveTab}
        pendingCount={pendingCount}
        onToggle={() => setIsSidebarOpen(!isSidebarOpen)}
      />

      {/* ── Main Layout Viewport ────────────────────── */}
      <div
        className="main-content relative z-10"
        style={{ marginLeft: `${sidebarWidth}px` }}
      >
        <Header
          connected={connected}
          onToggleSidebar={() => setIsSidebarOpen(!isSidebarOpen)}
          title={TAB_TITLES[activeTab] ?? "Dashboard"}
        />

        <main className="p-6 md:p-10 max-w-7xl w-full mx-auto">
          <AnimatePresence mode="wait">
            <motion.div
              key={activeTab}
              initial={{ opacity: 0, y: 12, filter: "blur(4px)" }}
              animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
              exit={{ opacity: 0, y: -12, filter: "blur(4px)" }}
              transition={{ duration: 0.25, ease: "easeOut" }}
            >
              {activeTab === "dashboard" && <DashboardTab />}
              {activeTab === "editor" && <EditorTab />}
              {activeTab === "generator" && <ClipGeneratorTab />}
              {activeTab === "streamers" && <StreamersTab />}
              {activeTab === "pipeline" && <PipelineTab />}
              {activeTab === "clips" && <ClipsTab />}
              {activeTab === "uploads" && <UploadsTab />}
              {activeTab === "settings" && <SettingsTab />}
            </motion.div>
          </AnimatePresence>
        </main>
      </div>
    </div>
  );
}
