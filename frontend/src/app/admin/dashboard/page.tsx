"use client";

import React, { useEffect, useState } from "react";
import { StatsCard } from "@/components/StatsCard";
import { Badge } from "@/components/Badge";
import { HashChainVisualizer } from "@/components/HashChainVisualizer";
import { TableSkeleton } from "@/components/LoadingSkeleton";
import { api } from "@/services/api";
import {
  Users,
  ShieldCheck,
  FileText,
  CheckCircle2,
  Layers,
  ScrollText,
  AlertTriangle,
  Activity,
} from "lucide-react";

export default function AdminDashboardPage() {
  const [stats, setStats] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function loadAdminStats() {
      try {
        const res = await api.get("/admin/stats");
        setStats(res.data);
      } catch (err) {
        console.error("Failed to load admin stats", err);
      } finally {
        setLoading(false);
      }
    }
    loadAdminStats();
  }, []);

  return (
    <div className="space-y-6 sm:space-y-8 max-w-7xl mx-auto w-full">
      {/* Header */}
      <div>
        <h2 className="text-xl sm:text-2xl font-bold text-slate-900 dark:text-white">
          System Administration & Governance
        </h2>
        <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5 leading-relaxed">
          National Content Provenance Registry • Global Telemetry & Security Metrics
        </p>
      </div>

      {/* Global Statistics Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3.5 sm:gap-5">
        <StatsCard
          title="Total Users"
          value={stats?.total_users ?? 0}
          description="Registered platform accounts"
          icon={Users}
        />
        <StatsCard
          title="Authorized Publishers"
          value={stats?.total_publishers ?? 0}
          description="Active government entities"
          icon={ShieldCheck}
          trend={{ value: "Verified", isPositive: true }}
        />
        <StatsCard
          title="Signed Publications"
          value={stats?.total_registered_content ?? 0}
          description="In immutable ledger"
          icon={FileText}
        />
        <StatsCard
          title="Total Inquiries"
          value={stats?.total_verifications ?? 0}
          description="Citizen verifications processed"
          icon={CheckCircle2}
        />
      </div>

      {/* Verification Breakdown & Verdict Distribution */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 sm:gap-6">
        <div className="p-4 sm:p-6 rounded-2xl sm:rounded-3xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 shadow-sm space-y-4">
          <div className="flex items-center gap-2.5">
            <Activity className="h-5 w-5 text-navy-800 dark:text-navy-300 flex-shrink-0" />
            <div>
              <h3 className="text-sm font-bold text-slate-900 dark:text-white">
                Verifications by Verdict
              </h3>
              <p className="text-xs text-slate-500 dark:text-slate-400">
                Citizen inquiry classification breakdown
              </p>
            </div>
          </div>

          <div className="space-y-2.5 sm:space-y-3 pt-1">
            {stats?.verifications_by_verdict ? (
              Object.entries(stats.verifications_by_verdict).map(([verdict, count]: any) => (
                <div
                  key={verdict}
                  className="flex items-center justify-between p-3 rounded-xl bg-slate-50 dark:bg-slate-800/60 border border-slate-200 dark:border-slate-750 text-xs"
                >
                  <div className="flex items-center gap-2">
                    <Badge variant={verdict}>{verdict}</Badge>
                  </div>
                  <span className="font-bold text-slate-900 dark:text-white font-mono text-xs sm:text-sm">
                    {count}
                  </span>
                </div>
              ))
            ) : (
              <p className="text-xs text-slate-400">Loading verifications...</p>
            )}
          </div>
        </div>

        {/* Ledger Integrity Visualizer */}
        <HashChainVisualizer />
      </div>
    </div>
  );
}
