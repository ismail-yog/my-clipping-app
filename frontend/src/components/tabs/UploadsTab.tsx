"use client";

import React, { useState, useEffect } from "react";
import { motion } from "framer-motion";
import {
  UploadCloud,
  ExternalLink,
  CheckCircle2,
  XCircle,
  Clock,
  RefreshCw,
  Video,
} from "lucide-react";
import { getUploads } from "@/lib/api";

export default function UploadsTab() {
  const [uploads, setUploads] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    try {
      const data = await getUploads();
      setUploads(data.uploads || data || []);
    } catch (e) {
      setUploads([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  return (
    <div className="space-y-8 pb-12">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-black text-white tracking-tight">Uploads & YouTube Hub</h2>
          <p className="text-xs text-slate-400">History of automated uploads to YouTube Shorts</p>
        </div>
        <button onClick={load} className="btn-secondary-glass py-2 px-3 text-xs">
          <RefreshCw className="w-3.5 h-3.5" /> Refresh Hub
        </button>
      </div>

      <div className="glass-panel overflow-hidden">
        {loading ? (
          <div className="p-16 text-center text-slate-400 font-bold text-sm">
            Loading Upload History...
          </div>
        ) : uploads.length === 0 ? (
          <div className="p-16 text-center space-y-3">
            <UploadCloud className="w-12 h-12 text-slate-600 mx-auto" />
            <p className="text-slate-300 font-bold text-sm">No uploads recorded yet.</p>
            <p className="text-xs text-slate-500">
              Approve viral clips in the review station to trigger automatic YouTube Shorts uploads.
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-white/[0.02] border-b border-white/5 uppercase text-slate-400 font-extrabold tracking-wider">
                <tr>
                  <th className="py-4 px-6">Status</th>
                  <th className="py-4 px-6">Clip Title</th>
                  <th className="py-4 px-6">Streamer</th>
                  <th className="py-4 px-6">Timestamp</th>
                  <th className="py-4 px-6 text-right">Destination</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5 font-medium">
                {uploads.map((u, i) => (
                  <tr key={i} className="hover:bg-white/[0.02] transition-colors">
                    <td className="py-4 px-6">
                      <span
                        className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-bold ${
                          u.success
                            ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
                            : "bg-rose-500/10 text-rose-400 border border-rose-500/20"
                        }`}
                      >
                        {u.success ? (
                          <>
                            <CheckCircle2 className="w-3.5 h-3.5" /> Published
                          </>
                        ) : (
                          <>
                            <XCircle className="w-3.5 h-3.5" /> Failed
                          </>
                        )}
                      </span>
                    </td>
                    <td className="py-4 px-6 font-bold text-white max-w-xs truncate">
                      {u.title || u.clip_id || "Untitled Clip"}
                    </td>
                    <td className="py-4 px-6 text-slate-300 capitalize">{u.streamer_name || "VOD"}</td>
                    <td className="py-4 px-6 text-slate-400 font-mono">
                      {u.uploaded_at
                        ? new Date(u.uploaded_at * 1000).toLocaleString()
                        : "Recent"}
                    </td>
                    <td className="py-4 px-6 text-right">
                      {u.video_url ? (
                        <a
                          href={u.video_url}
                          target="_blank"
                          rel="noreferrer"
                          className="inline-flex items-center gap-1 text-indigo-400 hover:text-indigo-300 font-bold"
                        >
                          <span>Watch Short</span>
                          <ExternalLink className="w-3 h-3" />
                        </a>
                      ) : (
                        <span className="text-slate-500 font-mono">—</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
