"use client";

import React, { useState, useEffect, useRef } from "react";
import { loginUser, registerUser, loginGoogle, getSettings } from "@/lib/api";

interface LandingPageProps {
  onAuthenticated: (user: any) => void;
}

const DEFAULT_GOOGLE_CLIENT_ID = "781306653779-euaoqhmellgoq5dl4v3h4b355rieu3qv.apps.googleusercontent.com";

export default function LandingPage({ onAuthenticated }: LandingPageProps) {
  const [showAuthModal, setShowAuthModal] = useState(false);
  const [authMode, setAuthMode] = useState<"login" | "register">("register");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [googleClientId, setGoogleClientId] = useState<string>(DEFAULT_GOOGLE_CLIENT_ID);
  const [gsiLoaded, setGsiLoaded] = useState(false);
  const googleBtnRef = useRef<HTMLDivElement>(null);

  // Fetch configured Google Client ID from backend settings
  useEffect(() => {
    getSettings()
      .then((d) => {
        if (d?.google_client_id?.trim()) {
          setGoogleClientId(d.google_client_id.trim());
        }
      })
      .catch(() => {});
  }, []);

  // Dynamically load Google Identity Services script
  useEffect(() => {
    if (typeof window === "undefined") return;

    if ((window as any).google?.accounts?.id) {
      setGsiLoaded(true);
      return;
    }

    const existingScript = document.getElementById("google-gsi-script");
    if (!existingScript) {
      const script = document.createElement("script");
      script.id = "google-gsi-script";
      script.src = "https://accounts.google.com/gsi/client";
      script.async = true;
      script.defer = true;
      script.onload = () => setGsiLoaded(true);
      script.onerror = () => {
        console.warn("Failed to load Google Identity Services script.");
      };
      document.head.appendChild(script);
    } else {
      existingScript.addEventListener("load", () => setGsiLoaded(true));
    }
  }, []);

  // Initialize Google Identity Services when modal opens and GSI is ready
  useEffect(() => {
    if (!showAuthModal || !gsiLoaded || typeof window === "undefined") return;
    const google = (window as any).google;
    if (!google?.accounts?.id) return;

    try {
      google.accounts.id.initialize({
        client_id: googleClientId,
        callback: async (response: any) => {
          if (response?.credential) {
            setLoading(true);
            setError(null);
            try {
              const res = await loginGoogle(response.credential);
              if (res?.token) {
                localStorage.setItem("synclip_jwt", res.token);
              }
              onAuthenticated(res.user);
            } catch (err: any) {
              setError(err.message || "Google authentication failed.");
            } finally {
              setLoading(false);
            }
          }
        },
        auto_select: false,
        cancel_on_tap_outside: true,
      });

      if (googleBtnRef.current) {
        googleBtnRef.current.innerHTML = "";
        google.accounts.id.renderButton(googleBtnRef.current, {
          type: "standard",
          shape: "pill",
          theme: "outline",
          text: "continue_with",
          size: "large",
          logo_alignment: "left",
          width: 360,
        });
      }
    } catch (e: any) {
      console.warn("Error initializing Google Identity:", e);
    }
  }, [showAuthModal, gsiLoaded, googleClientId]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      if (authMode === "register") {
        const res = await registerUser({ email, password, display_name: displayName });
        if (res.token) localStorage.setItem("synclip_jwt", res.token);
        onAuthenticated(res.user);
      } else {
        const res = await loginUser({ email, password });
        if (res.token) localStorage.setItem("synclip_jwt", res.token);
        onAuthenticated(res.user);
      }
    } catch (err: any) {
      setError(err.message || "Authentication failed. Please check your credentials.");
    } finally {
      setLoading(false);
    }
  };

  const handleManualGoogleClick = () => {
    setError(null);
    const google = typeof window !== "undefined" ? (window as any).google : null;
    if (google?.accounts?.id) {
      try {
        google.accounts.id.prompt((notification: any) => {
          if (notification?.isNotDisplayed?.() || notification?.isSkippedMoment?.()) {
            // Prompt was suppressed or blocked; fallback to informing user to use the rendered button
            setError("Please click the 'Continue with Google' button directly above.");
          }
        });
      } catch (e: any) {
        setError(e.message || "Google authentication failed. Please configure Client ID in settings.");
      }
    } else {
      setError("Google Sign-In is initializing. Please verify accounts.google.com is accessible.");
    }
  };

  return (
    <div className="min-h-screen bg-[#fdf6f4] text-[#1a0a10] flex flex-col justify-between selection:bg-[#f8c8d8] selection:text-[#8b2252] relative overflow-hidden">
      {/* ── Ambient Background Glows ────────────────────────────────────────── */}
      <div className="absolute top-[-10%] left-[-10%] w-[500px] h-[500px] rounded-full bg-gradient-to-br from-[#f8d7e1] to-[#f4a8c0] opacity-40 filter blur-3xl pointer-events-none" />
      <div className="absolute bottom-[-10%] right-[-10%] w-[600px] h-[600px] rounded-full bg-gradient-to-tl from-[#ead0e8] to-[#f9d0e0] opacity-45 filter blur-3xl pointer-events-none" />

      {/* ── Top Navigation Bar ─────────────────────────────────────────────── */}
      <nav className="w-full max-w-7xl mx-auto px-6 py-6 flex items-center justify-between z-20 relative">
        <div className="flex items-center gap-3">
          <div className="size-9 rounded-2xl bg-gradient-to-br from-[#f4a8c0] to-[#8b2252] flex items-center justify-center shadow-md">
            <span className="text-white text-lg font-bold">🌸</span>
          </div>
          <div>
            <span className="font-extrabold text-lg tracking-tight text-[#1a0a10] block leading-none">SYNCLIP</span>
            <span className="text-[9px] font-mono tracking-widest text-[#c08090] font-semibold">AUTONOMOUS CLIPPING ENGINE</span>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={() => { setAuthMode("login"); setShowAuthModal(true); setError(null); }}
            className="px-5 py-2 text-xs font-bold text-[#8b2252] hover:bg-[#f4a8c0]/20 rounded-full transition-all cursor-pointer"
          >
            Sign In
          </button>
          <button
            onClick={() => { setAuthMode("register"); setShowAuthModal(true); setError(null); }}
            className="px-6 py-2.5 text-xs font-bold text-white bg-gradient-to-r from-[#e87a90] via-[#c08090] to-[#8b2252] rounded-full shadow-md hover:brightness-105 transition-all cursor-pointer"
          >
            Start Free Studio
          </button>
        </div>
      </nav>

      {/* ── Hero Section ───────────────────────────────────────────────────── */}
      <main className="w-full max-w-6xl mx-auto px-6 py-12 flex flex-col items-center text-center z-10 relative">
        {/* Release Pill */}
        <div className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full bg-white/80 border border-[#f4a8c0]/40 shadow-xs mb-8">
          <span className="size-2 rounded-full bg-emerald-500 animate-pulse" />
          <span className="text-[11px] font-mono font-bold text-[#8b2252]">AI CLIPPING STUDIO 2.0 LIVE</span>
        </div>

        {/* Main Headline */}
        <h1 className="text-4xl sm:text-6xl lg:text-7xl font-extrabold tracking-tight text-[#1a0a10] max-w-4xl leading-[1.1] mb-6">
          Turn Multi-Hour Streams Into <span className="bg-clip-text text-transparent bg-gradient-to-r from-[#d946ef] via-[#ec4899] to-[#f43f5e]">Viral Shorts</span> Autonomously.
        </h1>

        {/* Subtitle */}
        <p className="text-base sm:text-lg text-[#805060] max-w-2xl font-medium leading-relaxed mb-10">
          Capture Twitch, Kick, and YouTube streams 24/7. AI detects instant rage, clutch wins, and plot twists with 9:16 smart cropping, Hormozi karaoke captions, and multi-account publishing.
        </p>

        {/* Call to Action Button */}
        <div className="flex flex-col sm:flex-row items-center gap-4 mb-16">
          <button
            onClick={() => { setAuthMode("register"); setShowAuthModal(true); setError(null); }}
            className="px-8 py-4 rounded-2xl text-sm font-extrabold text-white bg-gradient-to-r from-[#f43f5e] via-[#ec4899] to-[#8b2252] shadow-lg hover:shadow-xl hover:scale-[1.02] transition-all cursor-pointer flex items-center gap-2"
          >
            <span>Launch Your Studio</span>
            <span>⚡</span>
          </button>
          <button
            onClick={() => { setAuthMode("login"); setShowAuthModal(true); setError(null); }}
            className="px-8 py-4 rounded-2xl text-sm font-bold text-[#1a0a10] bg-white/80 border border-[#dcb4be]/40 hover:bg-white shadow-xs transition-all cursor-pointer"
          >
            Open Existing Account
          </button>
        </div>

        {/* ── Feature Highlights Grid ──────────────────────────────────────── */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 w-full text-left">
          <div className="p-6 rounded-3xl bg-white/70 backdrop-blur-md border border-[rgba(220,180,190,0.3)] shadow-sm flex flex-col justify-between">
            <div className="size-10 rounded-2xl bg-[#ffe4e6] flex items-center justify-center text-lg mb-4">🎯</div>
            <h3 className="font-extrabold text-base text-[#1a0a10] mb-2">Lead Editorial Director</h3>
            <p className="text-xs text-[#805060] leading-relaxed">
              Trained on viral archetypes (Meltdowns, Plot Twists, Absurdity) with strict 8/10 retention gating to kill false triggers.
            </p>
          </div>

          <div className="p-6 rounded-3xl bg-white/70 backdrop-blur-md border border-[rgba(220,180,190,0.3)] shadow-sm flex flex-col justify-between">
            <div className="size-10 rounded-2xl bg-[#ede9fe] flex items-center justify-center text-lg mb-4">🔥</div>
            <h3 className="font-extrabold text-base text-[#1a0a10] mb-2">Hormozi Karaoke Captions</h3>
            <p className="text-xs text-[#805060] leading-relaxed">
              Word-level synchronized animations, ultra-bold native display typography, and zero desync on variable live streams.
            </p>
          </div>

          <div className="p-6 rounded-3xl bg-white/70 backdrop-blur-md border border-[rgba(220,180,190,0.3)] shadow-sm flex flex-col justify-between">
            <div className="size-10 rounded-2xl bg-[#e0f2fe] flex items-center justify-center text-lg mb-4">🚀</div>
            <h3 className="font-extrabold text-base text-[#1a0a10] mb-2">Multi-Account Distribution</h3>
            <p className="text-xs text-[#805060] leading-relaxed">
              Automated upload schedule cycling across primary and secondary YouTube accounts to bypass daily quota caps.
            </p>
          </div>
        </div>
      </main>

      {/* ── Footer ─────────────────────────────────────────────────────────── */}
      <footer className="w-full max-w-7xl mx-auto px-6 py-8 border-t border-[rgba(220,180,190,0.25)] flex flex-col sm:flex-row items-center justify-between text-xs text-[#a06070] z-10 relative gap-4">
        <span>© 2026 SYNCLIP Autonomous Studio. All rights reserved.</span>
        <div className="flex items-center gap-6 font-medium">
          <span>FastAPI + Next.js</span>
          <span>CUDA Hardware Accelerated</span>
          <span>Isolated User Vaults</span>
        </div>
      </footer>

      {/* ── Auth Modal (Sign In / Register) ─────────────────────────────────── */}
      {showAuthModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4 animate-fadeIn">
          <div className="w-full max-w-md bg-white/95 backdrop-blur-xl border border-[rgba(220,180,190,0.4)] rounded-3xl p-8 shadow-2xl relative">
            {/* Close Button */}
            <button
              onClick={() => setShowAuthModal(false)}
              className="absolute top-5 right-5 text-gray-400 hover:text-gray-700 font-bold text-lg cursor-pointer"
            >
              ✕
            </button>

            {/* Modal Header */}
            <div className="text-center mb-6">
              <span className="text-3xl block mb-2">🌸</span>
              <h2 className="text-2xl font-extrabold text-[#1a0a10]">
                {authMode === "register" ? "Create Your Studio Account" : "Welcome Back"}
              </h2>
              <p className="text-xs text-[#805060] mt-1">
                {authMode === "register" ? "Private clip vault, monitored streamers, and automated uploads" : "Sign in to access your personal dashboard"}
              </p>
            </div>

            {/* Switch Tabs */}
            <div className="flex rounded-xl bg-[#fdf6f4] p-1 border border-[rgba(220,180,190,0.3)] mb-6">
              <button
                type="button"
                onClick={() => { setAuthMode("register"); setError(null); }}
                className={`flex-1 py-2 text-xs font-bold rounded-lg transition-all cursor-pointer ${authMode === "register" ? "bg-white text-[#8b2252] shadow-xs" : "text-[#805060]"}`}
              >
                Register
              </button>
              <button
                type="button"
                onClick={() => { setAuthMode("login"); setError(null); }}
                className={`flex-1 py-2 text-xs font-bold rounded-lg transition-all cursor-pointer ${authMode === "login" ? "bg-white text-[#8b2252] shadow-xs" : "text-[#805060]"}`}
              >
                Sign In
              </button>
            </div>

            {/* Error Banner */}
            {error && (
              <div className="mb-4 p-3 rounded-xl bg-rose-50 border border-rose-200 text-rose-700 text-xs font-semibold">
                {error}
              </div>
            )}

            {/* Form */}
            <form onSubmit={handleSubmit} className="flex flex-col gap-3">
              {authMode === "register" && (
                <div>
                  <label className="block text-[11px] font-bold text-[#805060] mb-1">Display Name</label>
                  <input
                    type="text"
                    required
                    placeholder="e.g. Alex"
                    value={displayName}
                    onChange={(e) => setDisplayName(e.target.value)}
                    className="w-full px-4 py-2.5 rounded-xl border border-[rgba(220,180,190,0.5)] bg-white text-xs text-[#1a0a10] focus:outline-none focus:ring-2 focus:ring-[#f4a8c0]"
                  />
                </div>
              )}

              <div>
                <label className="block text-[11px] font-bold text-[#805060] mb-1">Email Address</label>
                <input
                  type="email"
                  required
                  placeholder="creator@domain.com"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="w-full px-4 py-2.5 rounded-xl border border-[rgba(220,180,190,0.5)] bg-white text-xs text-[#1a0a10] focus:outline-none focus:ring-2 focus:ring-[#f4a8c0]"
                />
              </div>

              <div>
                <label className="block text-[11px] font-bold text-[#805060] mb-1">Password</label>
                <input
                  type="password"
                  required
                  placeholder="••••••••"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="w-full px-4 py-2.5 rounded-xl border border-[rgba(220,180,190,0.5)] bg-white text-xs text-[#1a0a10] focus:outline-none focus:ring-2 focus:ring-[#f4a8c0]"
                />
              </div>

              <button
                type="submit"
                disabled={loading}
                className="w-full mt-2 py-3 rounded-xl text-xs font-extrabold text-white bg-gradient-to-r from-[#f43f5e] to-[#8b2252] shadow-md hover:brightness-105 transition-all cursor-pointer flex items-center justify-center gap-2"
              >
                {loading ? "Authenticating..." : authMode === "register" ? "Create Studio Account" : "Sign In to Studio"}
              </button>
            </form>

            {/* Divider */}
            <div className="flex items-center my-4">
              <div className="flex-1 border-t border-[rgba(220,180,190,0.3)]" />
              <span className="px-3 text-[10px] font-mono text-[#a06070] font-semibold">OR</span>
              <div className="flex-1 border-t border-[rgba(220,180,190,0.3)]" />
            </div>

            {/* Google Identity Services Container */}
            <div className="flex flex-col items-center gap-2">
              <div ref={googleBtnRef} className="w-full flex justify-center min-h-[44px]" />

              {/* Fallback button if Google GSI iframe is still initializing or blocked */}
              <button
                type="button"
                onClick={handleManualGoogleClick}
                className="w-full py-2.5 rounded-xl border border-[rgba(220,180,190,0.4)] bg-white hover:bg-gray-50 text-xs font-bold text-[#1a0a10] flex items-center justify-center gap-2 transition-all cursor-pointer shadow-2xs"
              >
                <svg className="size-4" viewBox="0 0 24 24">
                  <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
                  <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
                  <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l2.85-2.22.81-.63z"/>
                  <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.52 6.16-4.52z"/>
                </svg>
                <span>Continue with Google</span>
              </button>

              <div className="mt-2 text-center">
                <p className="text-[10px] text-[#a06070] leading-tight">
                  Requires OAuth Client ID (type <b>Web Application</b>) with origin <code className="bg-black/5 px-1 py-0.2 rounded font-mono text-[9px]">http://localhost:3000</code>.
                </p>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
