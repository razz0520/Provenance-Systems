"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { useAuthStore } from "@/services/authStore";
import { api } from "@/services/api";
import {
  Sun,
  Moon,
  ShieldCheck,
  Activity,
  User as UserIcon,
  CheckCircle,
  AlertTriangle,
  Menu,
} from "lucide-react";

export function Header() {
  const { user, theme, toggleTheme, toggleMobileSidebar } = useAuthStore();
  const [systemStatus, setSystemStatus] = useState<string>("checking");

  useEffect(() => {
    async function checkHealth() {
      try {
        const res = await api.get("/health");
        setSystemStatus(res.data.status === "ok" ? "operational" : "degraded");
      } catch {
        setSystemStatus("offline");
      }
    }
    checkHealth();
  }, []);

  return (
    <header className="h-16 border-b border-slate-200 dark:border-slate-800 bg-white/90 dark:bg-slate-900/90 backdrop-blur-md sticky top-0 z-30 flex items-center justify-between px-3.5 sm:px-6 md:px-8">
      {/* Left: Mobile Menu Toggle & Registry Health Badge */}
      <div className="flex items-center gap-2 sm:gap-3 min-w-0">
        {/* Mobile Hamburger Trigger (visible on < md) */}
        <button
          onClick={toggleMobileSidebar}
          className="md:hidden p-2 rounded-xl border border-slate-200 dark:border-slate-800 text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors flex-shrink-0"
          aria-label="Open Navigation Menu"
        >
          <Menu className="h-5 w-5" />
        </button>

        {/* Health status indicator */}
        <div className="flex items-center gap-1.5 sm:gap-2 px-2.5 sm:px-3 py-1 rounded-full bg-slate-100 dark:bg-slate-800 text-[11px] sm:text-xs font-medium border border-slate-200 dark:border-slate-700 truncate">
          <span
            className={`w-2 h-2 rounded-full flex-shrink-0 ${
              systemStatus === "operational"
                ? "bg-emerald-500 animate-pulse"
                : systemStatus === "degraded"
                ? "bg-gold-500"
                : "bg-crimson-500"
            }`}
          />
          <span className="text-slate-600 dark:text-slate-300 capitalize truncate">
            Ledger: {systemStatus}
          </span>
        </div>
      </div>

      {/* Right: Theme Mode & User Badge */}
      <div className="flex items-center gap-2 sm:gap-4 flex-shrink-0">
        {/* Dark Mode Toggle */}
        <button
          onClick={toggleTheme}
          className="p-2 rounded-xl border border-slate-200 dark:border-slate-800 text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
          title={`Switch to ${theme === "light" ? "Dark" : "Light"} mode`}
          aria-label="Toggle Dark Mode"
        >
          {theme === "light" ? (
            <Moon className="h-4 w-4" />
          ) : (
            <Sun className="h-4 w-4" />
          )}
        </button>

        {/* User Badge */}
        {user && (
          <div className="flex items-center gap-2 sm:gap-3 pl-2 sm:pl-3 border-l border-slate-200 dark:border-slate-800">
            <div className="h-8 w-8 rounded-full bg-navy-800 text-white flex items-center justify-center text-xs font-bold shadow-sm flex-shrink-0">
              {user.organization_name ? user.organization_name.charAt(0) : "U"}
            </div>
            <div className="hidden lg:block text-left max-w-[140px] truncate">
              <p className="text-xs font-semibold text-slate-900 dark:text-white leading-tight truncate">
                {user.email}
              </p>
              <p className="text-[10px] text-slate-500 dark:text-slate-400 font-mono truncate">
                {user.role}
              </p>
            </div>
          </div>
        )}
      </div>
    </header>
  );
}
