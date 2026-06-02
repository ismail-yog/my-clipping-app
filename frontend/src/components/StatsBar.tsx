"use client";

const Icons = {
  Activity: () => (
    <svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M22 12h-4l-3 9L9 3l-3 9H2"/></svg>
  ),
  Zap: () => (
    <svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/></svg>
  ),
  Video: () => (
    <svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="m22 8-6 4 6 4V8Z"/><rect width="14" height="12" x="2" y="6" rx="2" ry="2"/></svg>
  ),
  ClipboardList: () => (
    <svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><rect width="8" height="4" x="8" y="2" rx="1" ry="1"/><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/><path d="M12 11h4"/><path d="M12 16h4"/><path d="M8 11h.01"/><path d="M8 16h.01"/></svg>
  ),
  Cloud: () => (
    <svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M17.5 19a3.5 3.5 0 0 0 .5-6.912a5 5 0 1 0-9.398-2.076a3.502 3.502 0 0 0-1.107 6.838"/><path d="M12 12v9"/><path d="m15 18-3 3-3-3"/></svg>
  ),
  Layers: () => (
    <svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="m12.83 2.18a2 2 0 0 0-1.66 0L2.6 6.08a1 1 0 0 0 0 1.83l8.58 3.91a2 2 0 0 0 1.66 0l8.58-3.9a1 1 0 0 0 0-1.83Z"/><path d="m2.6 12.08 8.58 3.9a2 2 0 0 0 1.66 0l8.58-3.9a1 1 0 0 0 0-1.83"/><path d="m2.6 17.08 8.58 3.9a2 2 0 0 0 1.66 0l8.58-3.9a1 1 0 0 0 0-1.83"/></svg>
  )
};

type Stats = {
  active: number; pipelines: number; totalClips: number;
  pendingReview: number; uploadsToday: number; queuePending: number;
};

const items = [
  { key: "active", label: "Active Nodes", icon: Icons.Activity, color: "#22c55e" },
  { key: "pipelines", label: "Logic Matrix", icon: Icons.Zap, color: "#6d4aff" },
  { key: "totalClips", label: "Total Extracts", icon: Icons.Video, color: "#3b82f6" },
  { key: "pendingReview", label: "Review Stack", icon: Icons.ClipboardList, color: "#f59e0b" },
  { key: "uploadsToday", label: "Upload Quota", icon: Icons.Cloud, color: "#8b5cf6", format: (v: number) => `${v}/6` },
  { key: "queuePending", label: "Process Queue", icon: Icons.Layers, color: "#64748b" },
];

export default function StatsBar({ stats }: { stats: Stats }) {
  return (
    <section className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-6 gap-6 animate-elegant">
      {items.map((item) => {
        const Icon = item.icon;
        const val = stats[item.key as keyof Stats];
        return (
          <div key={item.key} className="bg-white p-8 rounded-[36px] border border-gray-50 shadow-sm flex flex-col gap-6 hover:shadow-xl hover:shadow-purple-50 transition-all duration-500 group">
            <div className="flex items-center justify-between">
              <div className="w-12 h-12 rounded-2xl flex items-center justify-center transition-all duration-500 group-hover:scale-110" style={{ backgroundColor: `${item.color}15`, color: item.color }}>
                <Icon />
              </div>
              <div className="h-1 w-8 bg-gray-100 rounded-full group-hover:bg-purple-100 transition-colors" />
            </div>
            <div className="space-y-1">
              <span className="text-[11px] font-black text-gray-400 uppercase tracking-widest leading-none">{item.label}</span>
              <div className="text-3xl font-[900] text-gray-900 leading-none tracking-tight">
                {item.format ? item.format(val) : val}
              </div>
            </div>
          </div>
        );
      })}
    </section>
  );
}
