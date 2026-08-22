"use client";

import React, { useEffect } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import { useAuthStore } from "@/services/authStore";
import { cn } from "@/utils/cn";
import {
  ShieldCheck,
  FilePlus2,
  FileText,
  KeyRound,
  LayoutDashboard,
  Users,
  ScrollText,
  CheckCircle2,
  LogOut,
  ExternalLink,
  X,
} from "lucide-react";

export function Sidebar() {
  const pathname = usePathname();
  const { user, logout, mobileSidebarOpen, setMobileSidebarOpen } = useAuthStore();
  const isAdmin = user?.role === "ADMIN";

  // Auto close mobile drawer on route change
  useEffect(() => {
    setMobileSidebarOpen(false);
  }, [pathname, setMobileSidebarOpen]);

  const publisherLinks = [
    { name: "Overview", href: "/dashboard", icon: LayoutDashboard },
    { name: "Register Content", href: "/dashboard/register-content", icon: FilePlus2 },
    { name: "My Publications", href: "/dashboard/content", icon: FileText },
    { name: "Credentials & Keys", href: "/dashboard/credentials", icon: KeyRound },
  ];

  const adminLinks = [
    { name: "Admin Overview", href: "/admin/dashboard", icon: LayoutDashboard },
    { name: "User Directory", href: "/admin/users", icon: Users },
    { name: "Registry Content", href: "/admin/content", icon: FileText },
    { name: "Audit Trail", href: "/admin/audit-logs", icon: ScrollText },
  ];

  const links = isAdmin ? adminLinks : publisherLinks;

  const sidebarContent = (
    <div className="flex flex-col justify-between h-full">
      <div>
        {/* Brand Header */}
        <div className="p-5 sm:p-6 border-b border-slate-200 dark:border-slate-800 flex items-center justify-between">
          <Link
            href="/"
            onClick={() => setMobileSidebarOpen(false)}
            className="flex items-center gap-3 group min-w-0"
          >
            <div className="h-10 w-10 flex-shrink-0 rounded-xl bg-navy-800 text-white flex items-center justify-center shadow-md group-hover:scale-105 transition-transform">
              <ShieldCheck className="h-6 w-6 text-emerald-400" />
            </div>
            <div className="min-w-0">
              <h1 className="text-sm font-bold text-slate-900 dark:text-white leading-tight truncate">
                PROVENANCE
              </h1>
              <p className="text-[10px] uppercase font-semibold text-slate-400 tracking-wider truncate">
                Gov Verification System
              </p>
            </div>
          </Link>

          {/* Close button on mobile */}
          <button
            onClick={() => setMobileSidebarOpen(false)}
            className="md:hidden p-2 rounded-xl text-slate-400 hover:text-slate-600 dark:hover:text-white hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
            aria-label="Close Navigation"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Navigation Items */}
        <nav className="p-3 sm:p-4 space-y-1.5 overflow-y-auto">
          <div className="px-3 py-1.5 text-[11px] font-bold uppercase tracking-wider text-slate-400">
            {isAdmin ? "Admin Controls" : "Publisher Workspace"}
          </div>

          {links.map((item) => {
            const Icon = item.icon;
            const isActive = pathname === item.href;
            return (
              <Link
                key={item.href}
                href={item.href}
                onClick={() => setMobileSidebarOpen(false)}
                className={cn(
                  "flex items-center gap-3 px-3.5 py-2.5 rounded-xl text-sm font-medium transition-all duration-150 min-h-[44px]",
                  isActive
                    ? "bg-navy-800 text-white dark:bg-navy-700 shadow-sm"
                    : "text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800/60 hover:text-slate-900 dark:hover:text-white"
                )}
              >
                <Icon className={cn("h-4 w-4 flex-shrink-0", isActive ? "text-emerald-400" : "text-slate-400")} />
                <span className="truncate">{item.name}</span>
              </Link>
            );
          })}

          <div className="pt-4 px-3 py-1.5 text-[11px] font-bold uppercase tracking-wider text-slate-400">
            Citizen Tools
          </div>
          <Link
            href="/"
            onClick={() => setMobileSidebarOpen(false)}
            className="flex items-center justify-between px-3.5 py-2.5 rounded-xl text-sm font-medium text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800/60 hover:text-slate-900 dark:hover:text-white transition-all min-h-[44px]"
          >
            <div className="flex items-center gap-3 min-w-0">
              <CheckCircle2 className="h-4 w-4 text-emerald-500 flex-shrink-0" />
              <span className="truncate">Public Verifier</span>
            </div>
            <ExternalLink className="h-3.5 w-3.5 opacity-60 flex-shrink-0" />
          </Link>
        </nav>
      </div>

      {/* User Info & Logout Footer */}
      <div className="p-3 sm:p-4 border-t border-slate-200 dark:border-slate-800">
        <div className="flex items-center justify-between p-2.5 rounded-xl bg-slate-50 dark:bg-slate-800/50 border border-slate-200 dark:border-slate-750">
          <div className="truncate pr-2 min-w-0">
            <p className="text-xs font-semibold text-slate-900 dark:text-white truncate">
              {user?.organization_name || user?.email || "Authenticated User"}
            </p>
            <p className="text-[10px] text-slate-500 dark:text-slate-400 uppercase tracking-wider font-semibold truncate">
              {user?.role || "PUBLISHER"}
            </p>
          </div>
          <button
            onClick={() => {
              setMobileSidebarOpen(false);
              logout();
            }}
            title="Logout"
            className="p-2 rounded-lg text-slate-400 hover:text-crimson-600 hover:bg-white dark:hover:bg-slate-700 transition-colors flex-shrink-0"
            aria-label="Log Out"
          >
            <LogOut className="h-4 w-4" />
          </button>
        </div>
      </div>
    </div>
  );

  return (
    <>
      {/* Desktop Sidebar (Fixed on Desktop, Hidden on Mobile/Tablet < md) */}
      <aside className="hidden md:flex w-64 flex-shrink-0 border-r border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 flex-col justify-between h-screen sticky top-0 z-20">
        {sidebarContent}
      </aside>

      {/* Mobile & Tablet Drawer (< md) */}
      <AnimatePresence>
        {mobileSidebarOpen && (
          <>
            {/* Backdrop Overlay */}
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.2 }}
              onClick={() => setMobileSidebarOpen(false)}
              className="md:hidden fixed inset-0 bg-black/60 backdrop-blur-sm z-50"
            />

            {/* Slide-over Panel */}
            <motion.aside
              initial={{ x: "-100%" }}
              animate={{ x: 0 }}
              exit={{ x: "-100%" }}
              transition={{ type: "spring", damping: 25, stiffness: 300 }}
              className="md:hidden fixed inset-y-0 left-0 w-72 max-w-[85vw] bg-white dark:bg-slate-900 border-r border-slate-200 dark:border-slate-800 z-50 shadow-2xl flex flex-col justify-between"
            >
              {sidebarContent}
            </motion.aside>
          </>
        )}
      </AnimatePresence>
    </>
  );
}
