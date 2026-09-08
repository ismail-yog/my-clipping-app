"use client";

import React, { useState, useEffect, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Settings,
  Video,
  Cpu,
  Sliders,
  CheckCircle2,
  AlertCircle,
  Save,
  RefreshCw,
  ExternalLink,
  Sparkles,
  Shield,
  Layers,
  LogOut,
  Plus,
  X,
  Radio,
  Key,
  Clock,
  Calendar,
  Wand2,
  Tag,
  Hash,
} from "lucide-react";
import {
  getYouTubeAccounts,
  startYouTubeAuth,
  logoutYouTube,
  addYouTubeAccount,
  getSettings,
  updateSettings,
} from "@/lib/api";

interface YouTubeAccount {
  id: string;
  name: string;
  client_id?: string | null;
  secrets_file: string;
  token_file: string;
  secrets_exists: boolean;
  token_exists: boolean;
  connected: boolean;
  channel?: string | null;
  channel_info?: Record<string, any>;
  pending?: boolean;
  error?: string | null;
  uploads_today?: number;
  max_daily_uploads?: number;
  remaining_today?: number;
}

const PROMPT_PRESETS = [
  {
    name: "🔥 Gen-Z Viral",
    text: "Write authentic, viral lowercase titles with emojis (💀, 😭). Reference exact spoken phrases from transcript in quotes (e.g. bro really said \"...\" 💀). Keep it raw, hilarious, and punchy.",
  },
  {
    name: "👀 Clickbait & Mystery",
    text: "Use suspenseful curiosity gaps with high FOMO (e.g. \"he had no idea what was about to happen...\", \"watch till the end\"). Emphasize extreme shock and disbelief.",
  },
  {
    name: "💼 Clean & Punchy",
    text: "Professional, punchy, high-clarity title without excessive emoji spam. Highlight the exact strategic play or clutch action succinctly.",
  },
  {
    name: "🤡 Meme & Sarcastic",
    text: "Highlight the streamer failing, selling the bag, or getting roasted by chat. Sarcastic, unhinged commentary style.",
  },
];

const DESC_TOKENS = [
  { token: "{summary}", label: "Summary" },
  { token: "{streamer}", label: "Streamer" },
  { token: "{title}", label: "Title" },
  { token: "{hashtags}", label: "Hashtags" },
  { token: "{transcript}", label: "Transcript" },
  { token: "{emotion}", label: "Emotion" },
];

/* ── Design tokens from Figma ─────────────────── */
const CARD = "figma-glass-card p-6 overflow-hidden relative";
const SECTION_LABEL = "font-semibold text-[10px] text-[#c08090] tracking-[1.4px] leading-[15px] uppercase";
const BODY_TEXT = "text-[13px] text-[#3a1020] leading-[19.5px]";
const MUTED_TEXT = "text-[12px] text-[#b07080] leading-[18px]";
const VALUE_TEXT = "font-mono text-[13px] text-[#9b59b6] leading-[19.5px]";
const INNER_ROW = "bg-[rgba(248,240,245,0.6)] border border-[rgba(220,180,190,0.2)] rounded-[14px] px-5 py-4";

export default function SettingsTab() {
  const [accounts, setAccounts] = useState<YouTubeAccount[]>([]);
  const [loadingAccounts, setLoadingAccounts] = useState(true);
  const [connectingMap, setConnectingMap] = useState<Record<string, boolean>>({});
  const [loggingOutMap, setLoggingOutMap] = useState<Record<string, boolean>>({});
  const [accountMsgMap, setAccountMsgMap] = useState<Record<string, string>>({});
  const pollRef = useRef<any>(null);

  const [showAddModal, setShowAddModal] = useState(false);
  const [newClientId, setNewClientId] = useState("");
  const [newClientSecret, setNewClientSecret] = useState("");
  const [newAccountName, setNewAccountName] = useState("");
  const [isAddingAccount, setIsAddingAccount] = useState(false);
  const [addAccountError, setAddAccountError] = useState("");

  const [customHourInput, setCustomHourInput] = useState("18:00");

  const [settings, setSettings] = useState({
    max_clips: 3,
    clip_duration: 35,
    download_resolution: 1080,
    parallel_renders: 2,
    use_fast_whisper: true,
    burn_captions: true,
    viral_threshold: 0.65,
    auto_publish: false,
    ai_custom_prompt: "",
    ai_description_template: "",
    upload_schedule_mode: "immediate",
    upload_peak_hours: ["12:00", "16:00", "20:00"] as string[],
    upload_stagger_minutes: 120,
  });
  const [loadingSettings, setLoadingSettings] = useState(true);
  const [saved, setSaved] = useState(false);
  const [saveError, setSaveError] = useState("");
  const [authUrlMap, setAuthUrlMap] = useState<Record<string, string>>({});

  const fetchAccounts = async () => {
    try {
      const res = await getYouTubeAccounts();
      if (res?.accounts) {
        setAccounts(res.accounts);
        const hasPending = res.accounts.some((a: YouTubeAccount) => a.pending);
        if (!hasPending && Object.values(connectingMap).some(Boolean)) {
          setConnectingMap({});
        }
      }
    } catch (err) {
      console.warn("Failed to fetch YouTube accounts:", err);
    } finally {
      setLoadingAccounts(false);
    }
  };

  const fetchConfig = async () => {
    setLoadingSettings(true);
    try {
      const d = await getSettings();
      setSettings((prev) => ({
        ...prev,
        ...d,
        ai_custom_prompt: d.ai_custom_prompt ?? prev.ai_custom_prompt,
        ai_description_template: d.ai_description_template ?? prev.ai_description_template,
        upload_schedule_mode: d.upload_schedule_mode || prev.upload_schedule_mode,
        upload_peak_hours: d.upload_peak_hours && d.upload_peak_hours.length > 0 ? d.upload_peak_hours : prev.upload_peak_hours,
        upload_stagger_minutes: d.upload_stagger_minutes ?? prev.upload_stagger_minutes,
      }));
    } catch (e: any) {
      console.error("Failed to fetch settings:", e);
    } finally {
      setLoadingSettings(false);
    }
  };

  useEffect(() => {
    fetchAccounts();
    fetchConfig();
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  const startPolling = () => {
    if (pollRef.current) clearInterval(pollRef.current);
    pollRef.current = setInterval(fetchAccounts, 3000);
  };

  const handleConnectAccount = async (accountId: string) => {
    setConnectingMap((prev) => ({ ...prev, [accountId]: true }));
    setAccountMsgMap((prev) => ({ ...prev, [accountId]: "Opening Google Authorization in browser..." }));
    try {
      const res = await startYouTubeAuth(accountId);
      if (res?.auth_url) {
        setAuthUrlMap((prev) => ({ ...prev, [accountId]: res.auth_url }));
        window.open(res.auth_url, "_blank");
      }
      startPolling();
    } catch (e: any) {
      setAccountMsgMap((prev) => ({ ...prev, [accountId]: "Failed to launch OAuth: " + (e.message || "Unknown error") }));
      setConnectingMap((prev) => ({ ...prev, [accountId]: false }));
    }
  };

  const handleLogoutAccount = async (accountId: string) => {
    setLoggingOutMap((prev) => ({ ...prev, [accountId]: true }));
    setAccountMsgMap((prev) => ({ ...prev, [accountId]: "Disconnecting account and revoking OAuth token..." }));
    try {
      await logoutYouTube(accountId);
      await fetchAccounts();
      setAccountMsgMap((prev) => ({ ...prev, [accountId]: "Account disconnected successfully." }));
    } catch (e: any) {
      setAccountMsgMap((prev) => ({ ...prev, [accountId]: "Failed to disconnect: " + (e.message || "Error") }));
    } finally {
      setLoggingOutMap((prev) => ({ ...prev, [accountId]: false }));
    }
  };

  const handleAddNewAccount = async (e: React.FormEvent) => {
    e.preventDefault();
    setAddAccountError("");
    if (!newClientId.trim() || !newClientSecret.trim()) {
      setAddAccountError("Both Client ID and Client Secret are required.");
      return;
    }
    setIsAddingAccount(true);
    try {
      const res = await addYouTubeAccount({
        client_id: newClientId.trim(),
        client_secret: newClientSecret.trim(),
        name: newAccountName.trim() || undefined,
      });
      setNewClientId("");
      setNewClientSecret("");
      setNewAccountName("");
      setShowAddModal(false);
      await fetchAccounts();
      if (res?.account_id) handleConnectAccount(res.account_id);
    } catch (err: any) {
      setAddAccountError(err.message || "Failed to add YouTube account.");
    } finally {
      setIsAddingAccount(false);
    }
  };

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaved(false);
    setSaveError("");
    try {
      await updateSettings(settings);
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
    } catch (e: any) {
      setSaveError(e.message || "Failed to update configuration");
    }
  };

  const connectedCount = accounts.filter((a) => a.connected).length;

  /* ── Custom Toggle Switch ──────────────────── */
  const Toggle = ({ checked, onChange }: { checked: boolean; onChange: (v: boolean) => void }) => (
    <div
      onClick={() => onChange(!checked)}
      className="relative w-[44px] h-[24px] rounded-full cursor-pointer transition-colors duration-200 shrink-0"
      style={{
        background: checked
          ? "linear-gradient(151deg, #84cc84 0%, #22c55e 100%)"
          : "rgba(220,180,190,0.4)",
      }}
    >
      <div
        className="absolute top-[3px] w-[18px] h-[18px] rounded-[9px] bg-white shadow-[0_1px_4px_rgba(0,0,0,0.2)] transition-[left] duration-200"
        style={{ left: checked ? "23px" : "3px" }}
      />
    </div>
  );

  /* ── Range Slider ──────────────────────────── */
  const SliderRow = ({
    label,
    value,
    min,
    max,
    step,
    display,
    onChange,
  }: {
    label: string;
    value: number;
    min: number;
    max: number;
    step: number;
    display: string;
    onChange: (v: number) => void;
  }) => {
    const pct = ((value - min) / (max - min)) * 100;
    return (
      <div className="pt-5 space-y-2">
        <div className="flex items-center justify-between pb-1">
          <span className={BODY_TEXT}>{label}</span>
          <span className={VALUE_TEXT}>{display}</span>
        </div>
        <div className="relative h-6 flex items-center">
          <div className="absolute w-full h-[4px] rounded-full" style={{ background: `linear-gradient(to right, #c084cc ${pct}%, #e5d0f0 ${pct}%)` }} />
          <input
            type="range"
            min={min}
            max={max}
            step={step}
            value={value}
            onChange={(e) => onChange(Number(e.target.value))}
            className="absolute w-full h-6 opacity-0 cursor-pointer"
          />
          <div
            className="absolute w-[14px] h-[14px] rounded-full border-2 border-[#c084cc] bg-white shadow-sm pointer-events-none"
            style={{ left: `calc(${pct}% - 7px)` }}
          />
        </div>
      </div>
    );
  };

  return (
    <div className="space-y-5 pb-12 page-enter">
      {saved && (
        <div className="flex items-center gap-2 text-xs font-semibold text-emerald-700 bg-emerald-50 border border-emerald-200 px-4 py-2 rounded-[14px]">
          <CheckCircle2 className="w-3.5 h-3.5" /> Settings saved successfully
        </div>
      )}

      <form onSubmit={handleSave} className="space-y-5">
        {/* ═══ Row 1: YouTube OAuth + Video Pipeline ═══ */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
          {/* ── YouTube API OAuth ─────────────────────── */}
          <div className={CARD}>
            <div className="shimmer-active" />
            <div className="flex items-center gap-2">
              <p className={SECTION_LABEL}>YOUTUBE API OAUTH</p>
              <span className="text-[10px] font-mono text-[#c08090] tracking-wide">
                {connectedCount}/{accounts.length}
              </span>
            </div>

            {/* Multi-Account Quota Summary Banner */}
            <div className="mt-3 p-3 rounded-[12px] bg-gradient-to-r from-purple-950/85 via-indigo-950/80 to-purple-900/85 text-white border border-purple-400/30 flex items-center justify-between gap-3 flex-wrap">
              <div className="flex items-center gap-2.5">
                <span className="text-base">⚡</span>
                <div>
                  <p className="font-['DM_Mono'] text-xs font-bold text-purple-200 uppercase tracking-wide">
                    MULTI-ACCOUNT LOAD BALANCING (18 SHORTS / DAY)
                  </p>
                  <p className="text-[10px] text-purple-300/80">
                    6 uploads per account daily across 3 channels with automatic quota failover.
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-1.5 bg-white/10 px-2.5 py-1 rounded-lg border border-white/15">
                <span className="text-[11px] font-mono font-bold text-white">
                  {accounts.reduce((sum, a) => sum + (a.uploads_today || 0), 0)} / 18
                </span>
                <span className="text-[9px] font-mono text-purple-200">TODAY</span>
              </div>
            </div>

            <div className="pt-4 space-y-4">
              {loadingAccounts ? (
                <div className="flex items-center justify-center gap-2 py-8">
                  <RefreshCw className="w-4 h-4 animate-spin text-[#c08090]" />
                  <span className={MUTED_TEXT}>Scanning accounts...</span>
                </div>
              ) : accounts.length === 0 ? (
                <div className="bg-[rgba(254,202,202,0.3)] border border-[rgba(239,68,68,0.2)] rounded-[12px] px-[18px] py-4 flex items-center gap-3">
                  <div className="bg-[rgba(239,68,68,0.15)] rounded-[14px] w-7 h-7 flex items-center justify-center shrink-0">
                    <X className="w-3 h-3 text-[#991b1b]" />
                  </div>
                  <div>
                    <p className="font-bold text-[14px] text-[#991b1b] leading-[21px]">NOT CONNECTED</p>
                    <p className={MUTED_TEXT}>YouTube Data API v3</p>
                  </div>
                </div>
              ) : (
                accounts.map((acc) => {
                  const isConnecting = connectingMap[acc.id] || acc.pending;
                  const isLoggingOut = loggingOutMap[acc.id];
                  const msg = accountMsgMap[acc.id];
                  const uploadsToday = acc.uploads_today ?? 0;
                  const maxDaily = acc.max_daily_uploads ?? 6;
                  const remaining = acc.remaining_today ?? Math.max(0, maxDaily - uploadsToday);
                  const isFull = uploadsToday >= maxDaily;

                  return (
                    <div key={acc.id} className="bg-[rgba(248,240,245,0.6)] border border-[rgba(220,180,190,0.2)] rounded-[12px] px-4 py-3 space-y-2.5">
                      <div className="flex items-center justify-between gap-2 flex-wrap">
                        <div className="flex items-center gap-2">
                          <span className="text-[13px] font-semibold text-[#1a0a10]">{acc.name}</span>
                          {acc.connected ? (
                            <span className="text-[9px] font-mono font-semibold text-emerald-700 bg-emerald-50 border border-emerald-200 px-2 py-0.5 rounded-md">
                              CONNECTED
                            </span>
                          ) : (
                            <span className="text-[9px] font-mono font-semibold text-amber-700 bg-amber-50 border border-amber-200 px-2 py-0.5 rounded-md">
                              NOT CONNECTED
                            </span>
                          )}
                          {acc.connected && acc.channel && (
                            <span className="text-[11px] font-mono text-[#9b59b6]">{acc.channel}</span>
                          )}
                        </div>

                        <div className="flex items-center gap-2">
                          {acc.connected ? (
                            <>
                              <button
                                type="button"
                                onClick={() => handleLogoutAccount(acc.id)}
                                disabled={isLoggingOut}
                                className="px-3 py-1.5 rounded-[10px] bg-[rgba(254,202,202,0.3)] hover:bg-[rgba(254,202,202,0.5)] text-[#991b1b] text-[11px] font-semibold transition-colors cursor-pointer"
                              >
                                {isLoggingOut ? "Disconnecting..." : "Disconnect"}
                              </button>
                              <button
                                type="button"
                                onClick={() => handleConnectAccount(acc.id)}
                                disabled={isConnecting}
                                className="px-3 py-1.5 rounded-[10px] bg-[rgba(220,180,190,0.2)] hover:bg-[rgba(220,180,190,0.35)] text-[#3a1020] text-[11px] font-semibold transition-colors cursor-pointer"
                              >
                                {isConnecting ? "Re-authorizing..." : "Re-authorize"}
                              </button>
                            </>
                          ) : isConnecting && (authUrlMap[acc.id] || (acc as any).auth_url) ? (
                            <a
                              href={authUrlMap[acc.id] || (acc as any).auth_url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="px-3 py-1.5 rounded-[10px] text-white text-[11px] font-semibold flex items-center gap-1.5 cursor-pointer animate-pulse"
                              style={{ background: "linear-gradient(174deg, #e4a0b8, #9b59b6)" }}
                            >
                              <ExternalLink className="w-3 h-3" /> Open Sign-In
                            </a>
                          ) : (
                            <button
                              type="button"
                              onClick={() => handleConnectAccount(acc.id)}
                              disabled={isConnecting || !acc.secrets_exists}
                              className="px-3 py-1.5 rounded-[10px] text-white text-[11px] font-semibold cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
                              style={{ background: "linear-gradient(174deg, #e4a0b8, #9b59b6)" }}
                            >
                              {isConnecting ? "Connecting..." : "Connect Channel"}
                            </button>
                          )}
                        </div>
                      </div>

                      {/* Daily Quota Progress Bar */}
                      {acc.connected && (
                        <div className="flex items-center justify-between gap-3 pt-1 border-t border-[rgba(220,180,190,0.2)] text-[11px] font-mono flex-wrap">
                          <div className="flex items-center gap-2">
                            <span className="text-[#805060] font-medium">Daily Quota:</span>
                            <span className="font-bold text-[#1a0a10]">
                              {uploadsToday} / {maxDaily} uploaded
                            </span>
                            <span className={`px-1.5 py-0.2 rounded text-[9px] font-bold ${
                              isFull
                                ? "bg-amber-100 text-amber-800 border border-amber-300"
                                : "bg-emerald-100 text-emerald-800 border border-emerald-200"
                            }`}>
                              {isFull ? "MAX REACHED" : `${remaining} SLOTS REMAINING`}
                            </span>
                          </div>

                          <div className="w-24 h-2 rounded-full bg-black/10 overflow-hidden">
                            <div
                              className="h-full rounded-full transition-all bg-gradient-to-r from-[#e4a0b8] to-[#9b59b6]"
                              style={{
                                width: `${Math.min(100, Math.round((uploadsToday / maxDaily) * 100))}%`,
                              }}
                            />
                          </div>
                        </div>
                      )}

                      {msg && <p className="text-[11px] text-[#9b59b6] font-mono">{msg}</p>}
                      {!acc.connected && acc.error && !msg && (
                        <p className="text-[11px] text-amber-600 font-mono">{acc.error}</p>
                      )}
                    </div>
                  );
                })
              )}

              {/* Connect / Add button */}
              <button
                type="button"
                onClick={() => setShowAddModal(!showAddModal)}
                className="w-full h-[49px] rounded-[12px] text-white text-[14px] font-semibold text-center cursor-pointer transition-all hover:brightness-110"
                style={{
                  background: "linear-gradient(174deg, #e4a0b8 0%, #9b59b6 100%)",
                  boxShadow: "0 4px 9px rgba(155,89,182,0.3)",
                }}
              >
                {showAddModal ? "Cancel" : accounts.length > 0 ? "+ Add Account" : "Connect Google Account"}
              </button>

              {/* Inline add form */}
              <AnimatePresence>
                {showAddModal && (
                  <motion.div
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: "auto" }}
                    exit={{ opacity: 0, height: 0 }}
                    className="overflow-hidden"
                  >
                    <div className={`${INNER_ROW} space-y-3`}>
                      <div className="flex items-center gap-2">
                        <Key className="w-3.5 h-3.5 text-[#9b59b6]" />
                        <span className="text-[13px] font-semibold text-[#1a0a10]">Register New Account</span>
                      </div>
                      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                        <div>
                          <label className="block text-[10px] font-semibold text-[#c08090] tracking-[1px] uppercase mb-1">Nickname</label>
                          <input
                            type="text"
                            placeholder="e.g. Channel 4"
                            value={newAccountName}
                            onChange={(e) => setNewAccountName(e.target.value)}
                            className="w-full bg-white/60 border border-[rgba(220,180,190,0.3)] rounded-[10px] px-3 py-2 text-[12px] text-[#3a1020] placeholder:text-[#c0a0a8] focus:outline-none focus:border-[#c084cc]"
                          />
                        </div>
                        <div>
                          <label className="block text-[10px] font-semibold text-[#c08090] tracking-[1px] uppercase mb-1">Client ID *</label>
                          <input
                            type="text"
                            placeholder="...apps.googleusercontent.com"
                            value={newClientId}
                            onChange={(e) => setNewClientId(e.target.value)}
                            required
                            className="w-full bg-white/60 border border-[rgba(220,180,190,0.3)] rounded-[10px] px-3 py-2 text-[12px] text-[#3a1020] placeholder:text-[#c0a0a8] focus:outline-none focus:border-[#c084cc]"
                          />
                        </div>
                        <div>
                          <label className="block text-[10px] font-semibold text-[#c08090] tracking-[1px] uppercase mb-1">Client Secret *</label>
                          <input
                            type="text"
                            placeholder="GOCSPX-..."
                            value={newClientSecret}
                            onChange={(e) => setNewClientSecret(e.target.value)}
                            required
                            className="w-full bg-white/60 border border-[rgba(220,180,190,0.3)] rounded-[10px] px-3 py-2 text-[12px] text-[#3a1020] placeholder:text-[#c0a0a8] focus:outline-none focus:border-[#c084cc]"
                          />
                        </div>
                      </div>
                      {addAccountError && <p className="text-[11px] text-[#991b1b] font-mono">{addAccountError}</p>}
                      <div className="flex justify-end gap-2">
                        <button type="button" onClick={() => setShowAddModal(false)} className="px-3 py-1.5 rounded-[10px] bg-[rgba(220,180,190,0.2)] text-[#3a1020] text-[11px] font-semibold cursor-pointer">Cancel</button>
                        <button
                          type="button"
                          disabled={isAddingAccount}
                          onClick={handleAddNewAccount}
                          className="px-4 py-1.5 rounded-[10px] text-white text-[11px] font-semibold flex items-center gap-1.5 cursor-pointer"
                          style={{ background: "linear-gradient(174deg, #e4a0b8, #9b59b6)" }}
                        >
                          {isAddingAccount ? <><RefreshCw className="w-3 h-3 animate-spin" /> Registering...</> : <><Plus className="w-3 h-3" /> Register & Connect</>}
                        </button>
                      </div>
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          </div>

          {/* ── Video Pipeline Controls ───────────────── */}
          <div className={CARD}>
            <div className="shimmer-active" />
            <p className={SECTION_LABEL}>VIDEO PIPELINE CONTROLS</p>

            <SliderRow
              label="Target Clip Duration (30–45s)"
              value={settings.clip_duration}
              min={30}
              max={45}
              step={1}
              display={`${settings.clip_duration}s`}
              onChange={(v) => setSettings({ ...settings, clip_duration: v })}
            />
            <SliderRow
              label="Virality Cut Threshold"
              value={settings.viral_threshold}
              min={0.1}
              max={1.0}
              step={0.05}
              display={settings.viral_threshold.toFixed(2)}
              onChange={(v) => setSettings({ ...settings, viral_threshold: v })}
            />
            <SliderRow
              label="Max Highlights / Extraction"
              value={settings.max_clips}
              min={1}
              max={20}
              step={1}
              display={String(settings.max_clips)}
              onChange={(v) => setSettings({ ...settings, max_clips: v })}
            />
            <SliderRow
              label="Parallel Render Limit"
              value={settings.parallel_renders}
              min={1}
              max={8}
              step={1}
              display={String(settings.parallel_renders)}
              onChange={(v) => setSettings({ ...settings, parallel_renders: v })}
            />
          </div>
        </div>

        {/* ═══ Row 2: Hardware & VRAM ═══ */}
        <div className={CARD}>
          <div className="shimmer-active" />
          <p className={SECTION_LABEL}>{`HARDWARE & VRAM CONFIGURATION`}</p>

          <div className="pt-5 grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div className={`${INNER_ROW} flex items-center justify-between`}>
              <div>
                <p className="text-[14px] font-semibold text-[#1a0a10] leading-[21px]">Whisper GPU FP16 Mode</p>
                <p className={`${MUTED_TEXT} pt-0.5`}>CTranslate2 CUDA kernels</p>
              </div>
              <Toggle checked={settings.use_fast_whisper} onChange={(v) => setSettings({ ...settings, use_fast_whisper: v })} />
            </div>

            <div className={`${INNER_ROW} flex items-center justify-between`}>
              <div>
                <p className="text-[14px] font-semibold text-[#1a0a10] leading-[21px]">Karaoke Caption Burn-in</p>
                <p className={`${MUTED_TEXT} pt-0.5`}>ASS subtitle burn (hardware)</p>
              </div>
              <Toggle checked={settings.burn_captions} onChange={(v) => setSettings({ ...settings, burn_captions: v })} />
            </div>
          </div>
        </div>

        {/* ═══ Row 3: AI Copywriting & Persona ═══ */}
        <div className={CARD}>
          <div className="shimmer-active" />
          <p className={SECTION_LABEL}>AI COPYWRITING &amp; PERSONA DIRECTIVES</p>

          <div className="pt-5 space-y-5">
            {/* Custom Prompt */}
            <div className="space-y-2.5">
              <div className="flex items-center justify-between gap-2 flex-wrap">
                <span className={BODY_TEXT}>Custom AI System Prompt</span>
                <span className={MUTED_TEXT}>Overrides default Gen-Z title/hook persona</span>
              </div>

              <div className="flex flex-wrap items-center gap-1.5">
                <span className="text-[10px] font-semibold text-[#c08090] tracking-[1px] uppercase">Presets:</span>
                {PROMPT_PRESETS.map((preset) => (
                  <button
                    key={preset.name}
                    type="button"
                    onClick={() => setSettings((prev) => ({ ...prev, ai_custom_prompt: preset.text }))}
                    className="text-[11px] px-2.5 py-1 rounded-[8px] bg-[rgba(248,240,245,0.6)] hover:bg-[rgba(240,220,230,0.8)] text-[#3a1020] border border-[rgba(220,180,190,0.25)] transition-colors cursor-pointer"
                  >
                    {preset.name}
                  </button>
                ))}
              </div>

              <textarea
                rows={3}
                value={settings.ai_custom_prompt || ""}
                onChange={(e) => setSettings({ ...settings, ai_custom_prompt: e.target.value })}
                placeholder="e.g. Write authentic, viral lowercase titles with emojis (💀, 😭). Reference exact spoken phrases from transcript in quotes."
                className="w-full bg-white/60 border border-[rgba(220,180,190,0.3)] rounded-[12px] p-3.5 text-[13px] text-[#3a1020] placeholder:text-[#c0a0a8] focus:outline-none focus:border-[#c084cc] transition-colors leading-relaxed"
              />
            </div>

            {/* Description Template */}
            <div className="border-t border-[rgba(220,180,190,0.2)] pt-5 space-y-2.5">
              <div className="flex items-center justify-between gap-2 flex-wrap">
                <span className={BODY_TEXT}>YouTube Shorts Description Template</span>
                <span className={MUTED_TEXT}>Click tokens to insert placeholders</span>
              </div>

              <div className="flex flex-wrap items-center gap-1.5">
                <span className="text-[10px] font-semibold text-[#c08090] tracking-[1px] uppercase">Tokens:</span>
                {DESC_TOKENS.map(({ token }) => (
                  <button
                    key={token}
                    type="button"
                    onClick={() => {
                      setSettings((prev) => ({
                        ...prev,
                        ai_description_template:
                          (prev.ai_description_template ? prev.ai_description_template + " " : "") + token,
                      }));
                    }}
                    className="text-[11px] font-mono px-2 py-0.5 rounded-[6px] bg-[rgba(192,132,204,0.12)] hover:bg-[rgba(192,132,204,0.25)] text-[#9b59b6] border border-[rgba(192,132,204,0.25)] transition-colors cursor-pointer"
                  >
                    {token}
                  </button>
                ))}
              </div>

              <textarea
                rows={4}
                value={settings.ai_description_template || ""}
                onChange={(e) => setSettings({ ...settings, ai_description_template: e.target.value })}
                placeholder={"{summary}\n\nCatch the stream live on Twitch: https://twitch.tv/{streamer}\n\n#Shorts #gaming #viral #{streamer} #fyp"}
                className="w-full bg-white/60 border border-[rgba(220,180,190,0.3)] rounded-[12px] p-3.5 text-[13px] text-[#3a1020] placeholder:text-[#c0a0a8] focus:outline-none focus:border-[#c084cc] transition-colors font-mono leading-relaxed"
              />
            </div>
          </div>
        </div>

        {/* ═══ Row 4: Upload Schedule & Timing ═══ */}
        <div className={CARD}>
          <div className="shimmer-active" />
          <p className={SECTION_LABEL}>UPLOAD SCHEDULE &amp; TIMING WINDOW</p>

          <div className="pt-5 space-y-4">
            {/* Mode cards */}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              {[
                { id: "immediate", title: "Immediate", desc: "Publish right away upon approval.", badge: "0m delay" },
                { id: "peak_hours", title: "Target Peak Hours", desc: "Schedule during peak engagement windows.", badge: "High Traffic" },
                { id: "stagger", title: "Minimum Stagger", desc: "Enforce minimum delay between uploads.", badge: "Quota Safe" },
              ].map((mode) => {
                const sel = settings.upload_schedule_mode === mode.id;
                return (
                  <div
                    key={mode.id}
                    onClick={() => setSettings({ ...settings, upload_schedule_mode: mode.id })}
                    className={`p-4 rounded-[14px] border cursor-pointer transition-all space-y-2 ${
                      sel
                        ? "bg-[rgba(192,132,204,0.1)] border-[rgba(192,132,204,0.4)] shadow-[0_0_12px_rgba(155,89,182,0.12)]"
                        : "bg-[rgba(248,240,245,0.6)] border-[rgba(220,180,190,0.2)] hover:border-[rgba(220,180,190,0.45)]"
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <span className="text-[13px] font-semibold text-[#1a0a10] flex items-center gap-1.5">
                        <input type="radio" name="upload_schedule_mode" checked={sel} onChange={() => setSettings({ ...settings, upload_schedule_mode: mode.id })} className="accent-[#9b59b6]" />
                        {mode.title}
                      </span>
                      <span className={`text-[9px] font-mono px-1.5 py-0.5 rounded-[4px] ${sel ? "bg-[rgba(192,132,204,0.2)] text-[#9b59b6]" : "bg-[rgba(220,180,190,0.2)] text-[#c08090]"}`}>
                        {mode.badge}
                      </span>
                    </div>
                    <p className="text-[11px] text-[#b07080] leading-normal">{mode.desc}</p>
                  </div>
                );
              })}
            </div>

            {/* Peak Hours config */}
            <AnimatePresence>
              {settings.upload_schedule_mode === "peak_hours" && (
                <motion.div initial={{ opacity: 0, y: -6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -6 }} className={`${INNER_ROW} space-y-3`}>
                  <div className="flex items-center justify-between gap-2 flex-wrap">
                    <span className={BODY_TEXT}>Target Peak Hour Slots (24h)</span>
                    <span className={MUTED_TEXT}>Auto-queued with collision avoidance</span>
                  </div>

                  <div className="flex flex-wrap items-center gap-2">
                    {(settings.upload_peak_hours || []).map((hour) => (
                      <span key={hour} className="inline-flex items-center gap-1 px-2.5 py-1 rounded-[8px] bg-[rgba(192,132,204,0.12)] border border-[rgba(192,132,204,0.25)] text-[#9b59b6] text-[12px] font-mono font-semibold">
                        <Clock className="w-3 h-3" />
                        {hour}
                        <button
                          type="button"
                          onClick={() => setSettings({ ...settings, upload_peak_hours: (settings.upload_peak_hours || []).filter((h) => h !== hour) })}
                          className="hover:text-[#991b1b] transition-colors ml-0.5 cursor-pointer"
                        >
                          <X className="w-3 h-3" />
                        </button>
                      </span>
                    ))}
                    {(!settings.upload_peak_hours || settings.upload_peak_hours.length === 0) && (
                      <span className="text-[12px] text-[#991b1b] font-mono">No slots selected</span>
                    )}
                  </div>

                  <div className="flex flex-wrap items-center gap-2 pt-2 border-t border-[rgba(220,180,190,0.15)]">
                    <span className="text-[10px] font-semibold text-[#c08090] tracking-[1px] uppercase">Quick Add:</span>
                    {["08:00", "12:00", "16:00", "18:00", "20:00", "22:00"].map((ph) => {
                      const has = (settings.upload_peak_hours || []).includes(ph);
                      return (
                        <button key={ph} type="button" disabled={has} onClick={() => { const cur = settings.upload_peak_hours || []; if (!cur.includes(ph)) setSettings({ ...settings, upload_peak_hours: [...cur, ph].sort() }); }}
                          className={`text-[11px] font-mono px-2 py-0.5 rounded-[6px] border transition-colors cursor-pointer ${has ? "bg-[rgba(220,180,190,0.1)] text-[#c0a0a8] border-[rgba(220,180,190,0.15)] cursor-not-allowed" : "bg-[rgba(192,132,204,0.1)] hover:bg-[rgba(192,132,204,0.22)] text-[#9b59b6] border-[rgba(192,132,204,0.2)]"}`}
                        >+{ph}</button>
                      );
                    })}
                    <div className="flex items-center gap-1.5 ml-auto">
                      <input type="time" value={customHourInput} onChange={(e) => setCustomHourInput(e.target.value)} className="bg-white/60 border border-[rgba(220,180,190,0.3)] rounded-[8px] px-2 py-1 text-[12px] text-[#3a1020] font-mono focus:outline-none focus:border-[#c084cc]" />
                      <button type="button" onClick={() => { if (!customHourInput) return; const cur = settings.upload_peak_hours || []; if (!cur.includes(customHourInput)) setSettings({ ...settings, upload_peak_hours: [...cur, customHourInput].sort() }); }}
                        className="px-2.5 py-1 rounded-[8px] text-white text-[11px] font-semibold cursor-pointer" style={{ background: "linear-gradient(174deg, #e4a0b8, #9b59b6)" }}>Add Slot</button>
                    </div>
                  </div>
                </motion.div>
              )}
            </AnimatePresence>

            {/* Stagger config */}
            <AnimatePresence>
              {settings.upload_schedule_mode === "stagger" && (
                <motion.div initial={{ opacity: 0, y: -6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -6 }} className={`${INNER_ROW} space-y-3`}>
                  <div className="flex items-center justify-between gap-2 flex-wrap">
                    <span className={BODY_TEXT}>Minimum Delay Between Uploads</span>
                    <span className={MUTED_TEXT}>Prevents quota collision by spacing jobs</span>
                  </div>
                  <div className="flex items-center gap-3 flex-wrap">
                    <input
                      type="number"
                      min="5"
                      step="5"
                      value={settings.upload_stagger_minutes || 120}
                      onChange={(e) => setSettings({ ...settings, upload_stagger_minutes: Math.max(5, Number(e.target.value)) })}
                      className="w-28 bg-white/60 border border-[rgba(220,180,190,0.3)] rounded-[10px] px-3 py-2 text-[13px] text-[#3a1020] font-mono focus:outline-none focus:border-[#c084cc]"
                    />
                    <span className={VALUE_TEXT}>≈ {((settings.upload_stagger_minutes || 120) / 60).toFixed(1)} hours</span>
                    <div className="flex items-center gap-1.5 ml-auto">
                      {[{ m: 30, l: "30m" }, { m: 60, l: "1h" }, { m: 120, l: "2h" }, { m: 180, l: "3h" }, { m: 240, l: "4h" }].map(({ m, l }) => (
                        <button key={m} type="button" onClick={() => setSettings({ ...settings, upload_stagger_minutes: m })}
                          className={`text-[11px] font-mono px-2 py-1 rounded-[6px] border transition-colors cursor-pointer ${settings.upload_stagger_minutes === m ? "bg-[rgba(192,132,204,0.2)] text-[#9b59b6] border-[rgba(192,132,204,0.4)] font-semibold" : "bg-[rgba(248,240,245,0.6)] hover:bg-[rgba(240,220,230,0.8)] text-[#b07080] border-[rgba(220,180,190,0.2)]"}`}
                        >{l}</button>
                      ))}
                    </div>
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        </div>

        {/* ═══ Submit ═══ */}
        {saveError && <p className="text-[12px] text-[#991b1b] font-mono">{saveError}</p>}
        <div className="flex justify-end pt-1">
          <button
            type="submit"
            className="px-6 py-3 rounded-[12px] text-white text-[14px] font-semibold flex items-center gap-2 cursor-pointer transition-all hover:brightness-110"
            style={{
              background: "linear-gradient(174deg, #e4a0b8 0%, #9b59b6 100%)",
              boxShadow: "0 4px 18px rgba(155,89,182,0.35)",
            }}
          >
            <Save className="w-4 h-4" /> Save System Settings
          </button>
        </div>
      </form>
    </div>
  );
}
