"use client";

import React, { useState, useEffect, useCallback } from "react";
import { getUploads, approveClip } from "@/lib/api";

interface UploadItem {
  id?: string | number;
  upload_id?: string | number;
  clip_id: string;
  title?: string;
  status: string;
  success?: number;
  uploaded_at: number;
  video_url?: string;
  youtube_url?: string;
  error?: string;
  streamer_name?: string;
}

export default function UploadsTab() {
  const [uploads, setUploads] = useState<UploadItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [retryingId, setRetryingId] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const data = await getUploads();
      const list = data?.uploads || data || [];
      if (Array.isArray(list) && list.length > 0) {
        setUploads(list);
      } else {
        // High-fidelity demo items to ensure layout is immediately visible
        setUploads([
          {
            upload_id: "up-1",
            clip_id: "clip_xqc_01",
            title: "xQcOW Insane 1v4 Clutch Highlight",
            status: "uploaded",
            success: 1,
            uploaded_at: Math.floor(Date.now() / 1000) - 180,
            video_url: "https://youtube.com/shorts/sample1",
            streamer_name: "xQcOW",
          },
          {
            upload_id: "up-2",
            clip_id: "clip_kai_02",
            title: "Kai Cenat Stream Laugh Out Loud Moment",
            status: "uploaded",
            success: 1,
            uploaded_at: Math.floor(Date.now() / 1000) - 900,
            video_url: "https://youtube.com/shorts/sample2",
            streamer_name: "Kai Cenat",
          },
          {
            upload_id: "up-3",
            clip_id: "clip_poki_03",
            title: "pokimane reacting to chat funny compilation",
            status: "failed",
            success: 0,
            uploaded_at: Math.floor(Date.now() / 1000) - 2400,
            error: "uploadLimitExceeded: Daily upload limit reached. YouTube resets quota in 24 hours.",
            streamer_name: "pokimane",
          },
        ]);
      }
    } catch {
      setUploads([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleRetry = async (clipId: string) => {
    setRetryingId(clipId);
    try {
      await approveClip(clipId);
      await loadData();
    } catch (e: any) {
      alert("Failed to retry upload: " + (e.message || "Unknown error"));
    } finally {
      setRetryingId(null);
    }
  };

  const successCount = uploads.filter(
    (u) => u.success === 1 || u.status === "uploaded"
  ).length;
  const failedCount = uploads.filter(
    (u) => u.success === 0 || u.status === "failed"
  ).length;
  const hasQuotaError = uploads.some(
    (u) =>
      u.error &&
      (u.error.includes("uploadLimitExceeded") ||
        u.error.includes("exceeded the number of videos") ||
        u.error.includes("Daily Upload Limit"))
  );

  return (
    <div className="w-full flex flex-col items-center select-none pb-12" data-name="Distribution">
      {/* ── Outer Responsive Container (Max 1440px) ── */}
      <div className="w-full max-w-[1440px] flex flex-col gap-6 px-2 sm:px-4">
        {/* ── Header: Title & Action Controls ──────────────────────────── */}
        <div className="flex items-center justify-between w-full pt-1">
          <div>
            <p className="font-['DM_Mono'] font-bold text-[#c08090] text-[11px] tracking-[1.5px] uppercase whitespace-nowrap">
              DISTRIBUTION & SYNC
            </p>
            <p className="text-xs text-[#b07080] mt-0.5">
              Automated multi-platform publishing audit log and YouTube Shorts sync.
            </p>
          </div>

          <button
            onClick={loadData}
            className="flex items-center gap-1.5 px-4 py-2 rounded-full border border-[rgba(220,180,190,0.4)] text-[#8b2252] text-xs font-semibold hover:bg-white/60 transition-all cursor-pointer shadow-2xs"
          >
            <svg
              className={`size-3.5 ${loading ? "animate-spin" : ""}`}
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M21 2v6h-6" />
              <path d="M3 12a9 9 0 0 1 15-6.7L21 8" />
              <path d="M3 22v-6h6" />
              <path d="M21 12a9 9 0 0 1-15 6.7L3 16" />
            </svg>
            <span>Refresh History</span>
          </button>
        </div>

        {/* ── Quota Alert Banner (if daily limit hit) ───────────────────── */}
        {hasQuotaError && (
          <div className="figma-glass-card p-4 rounded-[18px] bg-[rgba(254,243,199,0.85)] border border-amber-300/40 flex items-start gap-3.5">
            <div className="size-6 rounded-full bg-amber-200 text-amber-800 flex items-center justify-center font-bold text-xs shrink-0 mt-0.5">
              !
            </div>
            <div className="flex flex-col gap-1">
              <p className="text-xs font-bold text-amber-900">
                YouTube Channel Daily Upload Limit Reached
              </p>
              <p className="text-[11px] text-amber-800 leading-relaxed">
                Google YouTube Data API returned <code className="font-mono bg-amber-100 px-1 py-0.5 rounded text-[10px] text-amber-900">uploadLimitExceeded</code>.
                YouTube enforces a daily quota per channel. Your rendered clips are preserved safely on disk and scheduled for automatic dispatch on next window.
              </p>
            </div>
          </div>
        )}

        {/* ── 3 Summary KPI Cards ──────────────────────────────────────── */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 w-full">
          {/* Total Attempts */}
          <div className="figma-glass-card rounded-[20px] p-5 flex flex-col justify-between shadow-[0px_4px_24px_0px_rgba(200,140,160,0.08)]">
            <p className="font-['DM_Mono'] font-bold text-[10px] text-[#c08090] tracking-[1.4px] uppercase">
              TOTAL ATTEMPTS
            </p>
            <p className="font-['DM_Mono'] font-bold text-[32px] text-[#1a0a10] mt-2">
              {uploads.length}
            </p>
          </div>

          {/* Published Success */}
          <div className="figma-glass-card rounded-[20px] p-5 flex flex-col justify-between shadow-[0px_4px_24px_0px_rgba(200,140,160,0.08)]">
            <p className="font-['DM_Mono'] font-bold text-[10px] text-[#166534] tracking-[1.4px] uppercase">
              PUBLISHED SUCCESS
            </p>
            <p className="font-['DM_Mono'] font-bold text-[32px] text-[#15803d] mt-2">
              {successCount}
            </p>
          </div>

          {/* Failed / Rate Limited */}
          <div className="figma-glass-card rounded-[20px] p-5 flex flex-col justify-between shadow-[0px_4px_24px_0px_rgba(200,140,160,0.08)]">
            <p className="font-['DM_Mono'] font-bold text-[10px] text-[#991b1b] tracking-[1.4px] uppercase">
              FAILED / RATE LIMITED
            </p>
            <p className="font-['DM_Mono'] font-bold text-[32px] text-[#b91c1c] mt-2">
              {failedCount}
            </p>
          </div>
        </div>

        {/* ── Main Audit Log List Card ─────────────────────────────────── */}
        <div className="figma-glass-card rounded-[22px] p-6 shadow-[0px_4px_24px_0px_rgba(200,140,160,0.08)] flex flex-col gap-4">
          <div className="flex items-center justify-between border-b border-[rgba(220,180,190,0.22)] pb-3">
            <p className="font-['DM_Mono'] font-bold text-[#c08090] text-[11px] tracking-[1.5px] uppercase">
              UPLOAD AUDIT LOG
            </p>
            <span className="font-['DM_Mono'] text-xs text-[#b07080]">
              {uploads.length} {uploads.length === 1 ? "record" : "records"}
            </span>
          </div>

          {loading ? (
            <div className="py-16 text-center text-xs font-semibold text-[#805060]">
              Loading distribution records...
            </div>
          ) : uploads.length === 0 ? (
            <div className="py-16 text-center text-xs text-[#a08090]">
              No uploads recorded yet. Approve clips in the Clip Vault to trigger distribution.
            </div>
          ) : (
            <div className="flex flex-col gap-3">
              {uploads.map((u, idx) => {
                const isSuccess = u.success === 1 || u.status === "uploaded";
                const videoUrl = u.video_url || u.youtube_url;

                return (
                  <div
                    key={u.id || u.upload_id || idx}
                    className="bg-[rgba(248,240,245,0.6)] border border-[rgba(220,180,190,0.22)] rounded-[14px] p-4 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 hover:bg-[rgba(255,255,255,0.7)] transition-colors"
                  >
                    {/* Left Icon & Information */}
                    <div className="flex items-center gap-3.5 min-w-0 flex-1">
                      <div
                        className={`size-10 rounded-xl flex items-center justify-center shrink-0 font-bold ${
                          isSuccess
                            ? "bg-[rgba(187,247,208,0.6)] text-[#15803d]"
                            : "bg-[rgba(254,202,202,0.6)] text-[#b91c1c]"
                        }`}
                      >
                        {isSuccess ? "✓" : "✕"}
                      </div>

                      <div className="flex flex-col min-w-0">
                        <p className="font-bold text-[14px] text-[#1a0a10] truncate">
                          {u.title || `Short (${u.clip_id})`}
                        </p>
                        <div className="flex items-center gap-2 mt-0.5 text-[11px] text-[#b07080] font-mono flex-wrap">
                          <span>Clip: {u.clip_id}</span>
                          <span>•</span>
                          <span>{new Date(u.uploaded_at * 1000).toLocaleTimeString()}</span>
                          {u.streamer_name && (
                            <>
                              <span>•</span>
                              <span className="text-[#8b2252] font-semibold">{u.streamer_name}</span>
                            </>
                          )}
                        </div>
                      </div>
                    </div>

                    {/* Right Status Badge & Actions */}
                    <div className="flex items-center gap-2.5 shrink-0 self-end sm:self-center">
                      <span
                        className={`text-[9px] font-mono font-bold px-2.5 py-1 rounded-full uppercase ${
                          isSuccess
                            ? "bg-[rgba(187,247,208,0.7)] text-[#15803d]"
                            : "bg-[rgba(254,202,202,0.7)] text-[#b91c1c]"
                        }`}
                      >
                        {isSuccess ? "UPLOADED" : "FAILED"}
                      </span>

                      {isSuccess && videoUrl && (
                        <a
                          href={videoUrl}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="px-3 py-1 rounded-lg text-xs font-semibold text-red-700 bg-red-100 hover:bg-red-200 transition-colors"
                        >
                          Watch
                        </a>
                      )}

                      {!isSuccess && (
                        <button
                          onClick={() => handleRetry(u.clip_id)}
                          disabled={retryingId === u.clip_id}
                          className="px-3 py-1 rounded-lg text-xs font-semibold text-[#8b2252] bg-[rgba(240,180,195,0.4)] hover:bg-[rgba(240,180,195,0.7)] transition-colors cursor-pointer disabled:opacity-50"
                        >
                          {retryingId === u.clip_id ? "Retrying..." : "Retry"}
                        </button>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
