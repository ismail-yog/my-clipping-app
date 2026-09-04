"use client";

import { useState, useEffect, useRef } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { connectWebSocket, StatusUpdate } from "@/lib/ws";
import { getStatus } from "@/lib/api";

import DashboardTab from "@/components/tabs/DashboardTab";
import EditorTab from "@/components/tabs/EditorTab";
import ClipGeneratorTab from "@/components/tabs/ClipGeneratorTab";
import StreamersTab from "@/components/tabs/StreamersTab";
import PipelineTab from "@/components/tabs/PipelineTab";
import ClipsTab from "@/components/tabs/ClipsTab";
import UploadsTab from "@/components/tabs/UploadsTab";
import SettingsTab from "@/components/tabs/SettingsTab";

// ── Blossom SVG Flower ────────────────────────────────────────────────────────
function BlossomFlower({ size = 28, color = "#f4a8c0", cx = "#fff", opacity = 1, rotate = 0 }: {
  size?: number; color?: string; cx?: string; opacity?: number; rotate?: number;
}) {
  const r = size / 2;
  const pr = r * 0.42;
  const petals = 5;
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} style={{ opacity, transform: `rotate(${rotate}deg)`, display: "block" }}>
      {Array.from({ length: petals }).map((_, i) => {
        const angle = (i / petals) * 360;
        const rad = (angle * Math.PI) / 180;
        const px = r + Math.cos(rad) * pr * 0.85;
        const py = r + Math.sin(rad) * pr * 0.85;
        return (
          <ellipse key={i} cx={px} cy={py} rx={pr * 0.7} ry={pr * 0.48}
            fill={color} transform={`rotate(${angle + 90},${px},${py})`} opacity={0.92} />
        );
      })}
      <circle cx={r} cy={r} r={r * 0.22} fill={cx} opacity={0.95} />
      <circle cx={r} cy={r} r={r * 0.12} fill="#f9d0a0" opacity={0.9} />
    </svg>
  );
}

// ── Falling Blossom Petals Canvas ────────────────────────────────────────────
function BlossomCanvas() {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const canvas = ref.current!;
    const ctx = canvas.getContext("2d")!;
    let raf: number;
    const dpr = window.devicePixelRatio || 1;
    const resize = () => {
      canvas.width = window.innerWidth * dpr;
      canvas.height = window.innerHeight * dpr;
      canvas.style.width = window.innerWidth + "px";
      canvas.style.height = window.innerHeight + "px";
      ctx.scale(dpr, dpr);
    };
    resize();
    window.addEventListener("resize", resize);

    interface Petal { x:number;y:number;vy:number;vx:number;size:number;rotation:number;rotSpeed:number;swayAmp:number;swaySpeed:number;swayOffset:number;alpha:number;color:string;type:number;life:number;maxLife:number; }
    const petalColors = ["#f8c8d8","#f4a8c0","#e890b0","#fce4ec","#f9d0e0","#f0b8d0","#ead0e8","#fbd8e8"];
    const petals: Petal[] = [];

    const spawnPetal = () => {
      const maxLife = 260 + Math.random() * 200;
      petals.push({ x:Math.random()*window.innerWidth, y:-20, vy:0.6+Math.random()*1.0, vx:(Math.random()-0.5)*0.6, size:6+Math.random()*10, rotation:Math.random()*Math.PI*2, rotSpeed:(Math.random()-0.5)*0.06, swayAmp:25+Math.random()*45, swaySpeed:0.008+Math.random()*0.012, swayOffset:Math.random()*Math.PI*2, alpha:0, color:petalColors[Math.floor(Math.random()*petalColors.length)], type:Math.floor(Math.random()*3), life:0, maxLife });
    };
    for (let i=0; i<22; i++) {
      const maxLife = 260+Math.random()*200;
      petals.push({ x:Math.random()*window.innerWidth, y:Math.random()*window.innerHeight, vy:0.6+Math.random()*1.0, vx:(Math.random()-0.5)*0.6, size:6+Math.random()*10, rotation:Math.random()*Math.PI*2, rotSpeed:(Math.random()-0.5)*0.06, swayAmp:25+Math.random()*45, swaySpeed:0.008+Math.random()*0.012, swayOffset:Math.random()*Math.PI*2, alpha:0.6, color:petalColors[Math.floor(Math.random()*petalColors.length)], type:Math.floor(Math.random()*3), life:Math.random()*maxLife*0.5, maxLife });
    }

    const drawPetal = (p: Petal) => {
      ctx.save();
      ctx.translate(p.x, p.y);
      ctx.rotate(p.rotation);
      ctx.globalAlpha = p.alpha;
      ctx.fillStyle = p.color;
      if (p.type === 0) {
        ctx.beginPath();
        ctx.moveTo(0,-p.size*0.5);
        ctx.bezierCurveTo(p.size*0.4,-p.size*0.3,p.size*0.4,p.size*0.3,0,p.size*0.55);
        ctx.bezierCurveTo(-p.size*0.4,p.size*0.3,-p.size*0.4,-p.size*0.3,0,-p.size*0.5);
        ctx.fill();
      } else if (p.type === 1) {
        ctx.beginPath();
        ctx.ellipse(0,0,p.size*0.38,p.size*0.55,0,0,Math.PI*2);
        ctx.fill();
      } else {
        ctx.beginPath();
        ctx.moveTo(0,p.size*0.3);
        ctx.bezierCurveTo(p.size*0.45,p.size*0.1,p.size*0.5,-p.size*0.4,0,-p.size*0.5);
        ctx.bezierCurveTo(-p.size*0.5,-p.size*0.4,-p.size*0.45,p.size*0.1,0,p.size*0.3);
        ctx.fill();
      }
      ctx.globalAlpha = p.alpha * 0.22;
      ctx.strokeStyle = "#fff";
      ctx.lineWidth = 0.8;
      ctx.beginPath();
      ctx.moveTo(0,-p.size*0.4);
      ctx.lineTo(0,p.size*0.4);
      ctx.stroke();
      ctx.restore();
    };

    let frame = 0;
    const tick = () => {
      ctx.clearRect(0,0,window.innerWidth,window.innerHeight);
      frame++;
      if (petals.length < 35 && Math.random() < 0.18) spawnPetal();
      for (let i=petals.length-1; i>=0; i--) {
        const p = petals[i];
        p.life++;
        const sway = Math.sin(frame*p.swaySpeed+p.swayOffset)*p.swayAmp*0.012;
        p.x += p.vx+sway; p.y += p.vy; p.rotation += p.rotSpeed;
        const prog = p.life/p.maxLife;
        if (prog<0.15) p.alpha=(prog/0.15)*0.72;
        else if (prog>0.75) p.alpha=((1-prog)/0.25)*0.72;
        else p.alpha=0.72;
        if (p.y>window.innerHeight+40||p.life>p.maxLife){petals.splice(i,1);continue;}
        drawPetal(p);
      }
      raf = requestAnimationFrame(tick);
    };
    tick();
    return () => { cancelAnimationFrame(raf); window.removeEventListener("resize",resize); };
  }, []);
  return <canvas ref={ref} style={{ position:"fixed",inset:0,pointerEvents:"none",zIndex:2 }} />;
}

// ── Blossom Branch Decoration ─────────────────────────────────────────────────
function BlossomBranch({ style = {} }: { style?: React.CSSProperties }) {
  const blossoms: [number,number,number,string,number][] = [
    [110,102,14,"#f4a8c0",0],[80,143,12,"#f8c8d8",20],[145,112,13,"#e890b0",-15],
    [178,78,15,"#f4a8c0",35],[220,27,16,"#fce4ec",10],[155,94,10,"#f9d0e0",-30],
    [196,54,11,"#ead0e8",50],[95,130,9,"#f8c8d8",70],
  ];
  return (
    <svg className="blossom-branch" viewBox="0 0 260 200" fill="none"
      style={{ position:"absolute",pointerEvents:"none",...style }}>
      <path d="M10 190 Q60 140 120 110 Q170 80 220 30" stroke="#c8a0b0" strokeWidth="3" strokeLinecap="round" opacity="0.5"/>
      <path d="M80 145 Q95 120 115 105" stroke="#c8a0b0" strokeWidth="2" strokeLinecap="round" opacity="0.4"/>
      <path d="M140 115 Q155 95 175 80" stroke="#c8a0b0" strokeWidth="2" strokeLinecap="round" opacity="0.4"/>
      <path d="M170 90 Q180 68 195 55" stroke="#c8a0b0" strokeWidth="1.5" strokeLinecap="round" opacity="0.35"/>
      {blossoms.map(([x,y,s,color,rot],idx) => (
        <g key={idx} transform={`translate(${Number(x)-Number(s)/2},${Number(y)-Number(s)/2})`}>
          <BlossomFlower size={Number(s)} color={String(color)} cx="#fff8fa" rotate={Number(rot)} opacity={0.85}/>
        </g>
      ))}
      {([[130,108],[165,86],[100,125]] as [number,number][]).map(([x,y],i) => (
        <ellipse key={i} cx={x} cy={y} rx="4" ry="5.5" fill="#f4a8c0" opacity="0.6"/>
      ))}
    </svg>
  );
}

// ── Nav items ─────────────────────────────────────────────────────────────────
const NAV_ITEMS = [
  { id:"dashboard",  label:"Dashboard",     icon:"🏠" },
  { id:"generator",  label:"Clip Studio",   icon:"✂️" },
  { id:"streamers",  label:"Auto Monitor",  icon:"📺" },
  { id:"clips",      label:"Clip Vault",    icon:"🗂️" },
  { id:"uploads",    label:"Distribution",  icon:"⬆️" },
  { id:"pipeline",   label:"Pipeline",      icon:"⚙️" },
  { id:"editor",     label:"Editor",        icon:"🎬" },
  { id:"settings",   label:"Settings",      icon:"⚙️" },
];

export default function SynclipDashboard() {
  const [activeTab, setActiveTab] = useState("dashboard");
  const [navKey, setNavKey] = useState(0);
  const [connected, setConnected] = useState(false);
  const [pendingCount, setPendingCount] = useState(0);
  const [vodProgress, setVodProgress] = useState<Record<string, unknown>>({});

  useEffect(() => {
    const ws = connectWebSocket((data: StatusUpdate) => {
      setConnected(true);
      setPendingCount(data.pending_review);
      if (data.vod_progress) setVodProgress(data.vod_progress);
    });
    return () => { if (ws) ws.close(); };
  }, []);

  useEffect(() => {
    getStatus()
      .then((data: Record<string, unknown>) => {
        setConnected(true);
        const stats = data.stats as Record<string, unknown> | undefined;
        setPendingCount((stats?.pending_review as number) ?? 0);
      })
      .catch(() => setConnected(false));
  }, []);

  const navigate = (id: string) => { setActiveTab(id); setNavKey(k => k+1); };

  return (
    <div style={{ height:"100vh", overflow:"hidden", display:"flex", flexDirection:"column", position:"relative", background:"#fdf6f4" }}>
      {/* Background layers */}
      <div className="ambient-bg">
        <div className="ambient-orb ambient-orb-1"/>
        <div className="ambient-orb ambient-orb-2"/>
        <div className="ambient-orb ambient-orb-3"/>
      </div>
      <div className="cyber-grid"/>
      <BlossomCanvas/>
      <div className="wind-shimmer"/>
      <div className="wind-shimmer" style={{ animationDelay:"-4.5s", top:"30%" }}/>
      <BlossomBranch style={{ width:260, height:200, top:-20, right:-10, opacity:0.55, zIndex:3, transform:"scaleX(-1)" }}/>
      <BlossomBranch style={{ width:200, height:160, bottom:30, left:-20, opacity:0.38, zIndex:3, transform:"rotate(180deg)" }}/>

      {/* ── Top Nav ─────────────────────────────────── */}
      <nav style={{ background:"rgba(255,255,255,0.72)", backdropFilter:"blur(18px)", borderBottom:"1px solid rgba(220,180,190,0.25)", position:"relative", zIndex:10, display:"flex", alignItems:"center", padding:"10px 24px", gap:4, flexShrink:0 }}>
        {/* Logo */}
        <div style={{ marginRight:28, display:"flex", alignItems:"center", gap:8 }}>
          <div className="blossom-bloom" style={{ transformOrigin:"center" }}>
            <BlossomFlower size={20} color="#f4a8c0" cx="#fff8fa"/>
          </div>
          <div>
            <div style={{ fontWeight:700, fontSize:14, letterSpacing:"0.05em", color:"#1a0a10" }}>SYNCLIP</div>
            <div style={{ fontSize:8, letterSpacing:"0.18em", color:"#c08090", fontWeight:500 }}>AUTONOMOUS STUDIO</div>
          </div>
        </div>

        {/* Nav links */}
        <div style={{ display:"flex", alignItems:"center", gap:2, flex:1, flexWrap:"wrap" }}>
          {NAV_ITEMS.map(item => {
            const isActive = activeTab === item.id;
            return (
              <button key={item.id} onClick={() => navigate(item.id)} style={{ display:"flex", alignItems:"center", gap:6, padding:"6px 14px", borderRadius:20, fontSize:13, fontWeight:500, color:isActive?"#8b2252":"#b07080", background:isActive?"rgba(240,180,195,0.35)":"transparent", border:"none", cursor:"pointer", transition:"all 0.2s" }}>
                <span style={{ fontSize:11 }}>{item.icon}</span>
                {item.label}
                {item.id==="clips" && pendingCount>0 && (
                  <span style={{ background:"#f43f5e", color:"white", fontSize:10, fontWeight:700, padding:"1px 6px", borderRadius:999, marginLeft:2 }}>{pendingCount}</span>
                )}
              </button>
            );
          })}
        </div>

        {/* Live + connection indicator */}
        <div className="live-pulse" style={{ display:"flex", alignItems:"center", gap:6, background:"rgba(240,200,210,0.5)", borderRadius:20, padding:"6px 14px", fontSize:12, fontWeight:600, letterSpacing:"0.06em", color:"#8b2252" }}>
          <div style={{ width:8, height:8, borderRadius:"50%", background:connected?"#22c55e":"#ef4444" }}/>
          {connected ? "LIVE" : "OFFLINE"}
        </div>
      </nav>

      {/* ── Main content ─────────────────────────────── */}
      <div style={{ flex:1, overflow:"auto", position:"relative", zIndex:5 }} key={navKey}>
        <AnimatePresence mode="wait">
          <motion.div
            key={activeTab}
            initial={{ opacity:0, y:10 }}
            animate={{ opacity:1, y:0 }}
            exit={{ opacity:0, y:-10 }}
            transition={{ duration:0.25, ease:"easeOut" }}
            style={{ padding:"24px 32px", maxWidth:1400, margin:"0 auto" }}
          >
            {activeTab==="dashboard"  && <DashboardTab/>}
            {activeTab==="editor"     && <EditorTab/>}
            {activeTab==="generator"  && <ClipGeneratorTab/>}
            {activeTab==="streamers"  && <StreamersTab/>}
            {activeTab==="pipeline"   && <PipelineTab/>}
            {activeTab==="clips"      && <ClipsTab/>}
            {activeTab==="uploads"    && <UploadsTab/>}
            {activeTab==="settings"   && <SettingsTab/>}
          </motion.div>
        </AnimatePresence>
      </div>

      {/* ── Footer ───────────────────────────────────── */}
      <div style={{ textAlign:"center", padding:"8px 0", borderTop:"1px dashed rgba(210,150,170,0.3)", position:"relative", zIndex:10, display:"flex", alignItems:"center", justifyContent:"center", gap:12, background:"rgba(255,255,255,0.5)", backdropFilter:"blur(10px)" }}>
        <BlossomFlower size={12} color="#f4a8c0" cx="#fff" opacity={0.6}/>
        <span style={{ fontSize:10, letterSpacing:"0.2em", color:"#d4a0b0", fontWeight:500 }}>AUTONOMOUS CLIPPING STUDIO</span>
        <BlossomFlower size={12} color="#c084cc" cx="#fff" opacity={0.6}/>
      </div>
    </div>
  );
}
