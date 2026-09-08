"use client";

import React from "react";

interface SynClipNavProps {
  activeTab: string;
  onTabChange: (tab: string) => void;
  isLive?: boolean;
}

export default function SynClipNav({
  activeTab,
  onTabChange,
  isLive = true,
}: SynClipNavProps) {
  const navItems = [
    { id: "dashboard", label: "Dashboard", icon: "/figma/home.svg" },
    { id: "studio", label: "Clip Studio", icon: "/figma/scissors.svg" },
    { id: "auto_monitor", label: "Auto Monitor", icon: "/figma/monitor.svg" },
    { id: "clips", label: "Clip Vault", icon: "/figma/archive.svg" },
    { id: "uploads", label: "Distribution", icon: "/figma/upload.svg" },
    { id: "settings", label: "Settings", icon: "/figma/settings.svg" },
  ];

  return (
    <div
      className="backdrop-blur-[18px] bg-[rgba(255,255,255,0.72)] border-[rgba(220,180,190,0.25)] border-b-[0.8px] border-solid content-stretch flex gap-[4px] items-center px-[24px] py-[12px] relative shrink-0 w-full select-none"
      data-name="Nav"
    >
      {/* Brand */}
      <div
        className="content-stretch flex flex-col h-[33px] items-start pr-[32px] relative shrink-0 w-[146.087px] cursor-pointer"
        onClick={() => onTabChange("studio")}
        data-name="Container"
      >
        <div className="content-stretch flex flex-col items-start relative shrink-0 w-full">
          <p className="font-bold leading-[21px] relative shrink-0 text-[#1a0a10] text-[14px] tracking-[0.7px] whitespace-nowrap">
            SYNCLIP
          </p>
        </div>
        <div className="content-stretch flex flex-col items-start relative shrink-0 w-full">
          <p className="font-medium leading-[12px] relative shrink-0 text-[#c08090] text-[8px] tracking-[1.44px] whitespace-nowrap">
            AUTONOMOUS STUDIO
          </p>
        </div>
      </div>

      {/* Nav Tabs */}
      <div
        className="content-stretch flex flex-[894.625_0_0] gap-[4px] items-center min-w-px relative"
        data-name="Container"
      >
        {navItems.map((item) => {
          const isActive = activeTab === item.id;
          return (
            <button
              key={item.id}
              onClick={() => onTabChange(item.id)}
              className={`content-stretch flex gap-[6px] items-center px-[14px] py-[6px] relative rounded-[20px] shrink-0 transition-all ${
                isActive
                  ? "bg-[rgba(240,180,195,0.35)]"
                  : "hover:bg-[rgba(240,180,195,0.15)]"
              }`}
              data-name="Button"
            >
              <div className="relative shrink-0 size-[14px]">
                <img
                  alt=""
                  className="absolute block inset-0 max-w-none size-full"
                  src={item.icon}
                />
              </div>
              <p
                className={`font-medium leading-[19.5px] relative shrink-0 text-[13px] text-center whitespace-nowrap ${
                  isActive ? "text-[#8b2252]" : "text-[#b07080]"
                }`}
              >
                {item.label}
              </p>
            </button>
          );
        })}
      </div>

      {/* Live Badge */}
      <div
        className="bg-[rgba(240,200,210,0.5)] content-stretch flex gap-[6px] items-center overflow-clip px-[14px] py-[6px] relative rounded-[20px] shadow-[0px_0px_0px_6.472px_rgba(34,197,94,0.11)] shrink-0"
        data-name="Container"
      >
        <div className="bg-[#22c55e] relative rounded-[4px] shrink-0 size-[8px] animate-pulse" />
        <p className="font-semibold leading-[18px] relative shrink-0 text-[#8b2252] text-[12px] tracking-[0.72px] whitespace-nowrap">
          LIVE
        </p>
      </div>
    </div>
  );
}
