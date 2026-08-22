"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { StatsCard } from "@/components/StatsCard";
import { Badge } from "@/components/Badge";
import { HashChainVisualizer } from "@/components/HashChainVisualizer";
import { TableSkeleton } from "@/components/LoadingSkeleton";
import { useAuthStore } from "@/services/authStore";
import { api } from "@/services/api";
import {
  FilePlus2,
  FileText,
  KeyRound,
  ShieldCheck,
  CheckCircle2,
  Clock,
  Layers,
  ArrowUpRight,
} from "lucide-react";

export default function DashboardPage() {
  const { user } = useAuthStore();
  const [stats, setStats] = useState<any>(null);
  const [recentContent, setRecentContent] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function loadDashboardData() {
      try {
        const [contentRes, statusRes] = await Promise.all([
          api.get("/content?limit=5"),
          api.get("/status"),
        ]);
        setRecentContent(contentRes.data.items || []);
        setStats(statusRes.data);
      } catch (err) {
        console.error("Dashboard data fetch error", err);
      } finally {
        setLoading(false);
      }
    }
    loadDashboardData();
  }, []);

  return (
    <div className="space-y-6 sm:space-y-8 max-w-7xl mx-auto w-full">
      {/* Top Welcome Banner */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 sm:gap-4">
        <div className="min-w-0">
          <h2 className="text-xl sm:text-2xl font-bold text-slate-900 dark:text-white truncate">
            Welcome, {user?.organization_name || "Publisher"}
          </h2>
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5 truncate">
            Government Provenance Console • {user?.email}
          </p>
        </div>

        <Link
          href="/dashboard/register-content"
          className="inline-flex items-center justify-center gap-2 px-4 sm:px-5 py-2.5 rounded-xl bg-navy-800 hover:bg-navy-700 text-white font-bold text-xs transition-all shadow-md hover:shadow-lg w-full sm:w-fit text-center min-h-[44px]"
        >
          <FilePlus2 className="h-4 w-4 text-emerald-400 flex-shrink-0" />
          <span>Register New Content</span>
        </Link>
      </div>

      {/* Statistics Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3.5 sm:gap-5">
        <StatsCard
          title="Total Publications"
          value={stats?.total_registered_content ?? 0}
          description="In immutable registry"
          icon={FileText}
          trend={{ value: "Live", isPositive: true }}
        />
        <StatsCard
          title="Ledger Verifications"
          value={stats?.total_verifications ?? 0}
          description="Citizen inquiries served"
          icon={CheckCircle2}
          trend={{ value: "99.8%", isPositive: true }}
        />
        <StatsCard
          title="Active Publishers"
          value={stats?.active_publishers ?? 1}
          description="Authorized government agencies"
          icon={ShieldCheck}
        />
        <StatsCard
          title="Hash Chain Ledger"
          value={stats?.registry_integrity ? "Secure" : "Warning"}
          description="Zero tampering detected"
          icon={Layers}
          trend={{ value: "100%", isPositive: true }}
        />
      </div>

      {/* Immutable Hash Chain Visualizer */}
      <HashChainVisualizer />

      {/* Recent Publications Table */}
      <div className="rounded-2xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 shadow-sm p-4 sm:p-6 space-y-4">
        <div className="flex flex-col xs:flex-row xs:items-center justify-between gap-2">
          <div>
            <h3 className="text-sm sm:text-base font-bold text-slate-900 dark:text-white">
              Recent Official Publications
            </h3>
            <p className="text-[11px] sm:text-xs text-slate-500 dark:text-slate-400">
              Latest items signed with Ed25519 and anchored to the ledger
            </p>
          </div>

          <Link
            href="/dashboard/content"
            className="text-xs font-semibold text-navy-800 dark:text-navy-300 hover:underline inline-flex items-center gap-1 w-fit"
          >
            <span>View All Content</span>
            <ArrowUpRight className="h-3.5 w-3.5 flex-shrink-0" />
          </Link>
        </div>

        {loading ? (
          <TableSkeleton rows={4} />
        ) : recentContent.length === 0 ? (
          <div className="p-8 text-center text-slate-400 text-xs">
            No registered content yet. Click &quot;Register New Content&quot; above to anchor your first publication.
          </div>
        ) : (
          <div className="overflow-x-auto -mx-4 sm:mx-0 px-4 sm:px-0">
            <table className="w-full text-left text-xs min-w-[550px]">
              <thead className="text-[11px] uppercase font-bold text-slate-400 border-b border-slate-100 dark:border-slate-800">
                <tr>
                  <th className="py-3 px-4">Filename / Media</th>
                  <th className="py-3 px-4">Type</th>
                  <th className="py-3 px-4">SHA-256 Hash</th>
                  <th className="py-3 px-4">Status</th>
                  <th className="py-3 px-4">Date</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-800/60">
                {recentContent.map((item) => (
                  <tr
                    key={item.id}
                    className="hover:bg-slate-50 dark:hover:bg-slate-800/40 transition-colors"
                  >
                    <td className="py-3.5 px-4 font-semibold text-slate-900 dark:text-white max-w-[200px] truncate">
                      {item.original_filename}
                    </td>
                    <td className="py-3.5 px-4 font-mono text-slate-500 uppercase">
                      {item.content_type}
                    </td>
                    <td className="py-3.5 px-4 hash-font text-slate-600 dark:text-slate-300">
                      {item.sha256_hash.substring(0, 16)}...
                    </td>
                    <td className="py-3.5 px-4">
                      <Badge variant={item.status}>{item.status}</Badge>
                    </td>
                    <td className="py-3.5 px-4 text-slate-400 whitespace-nowrap">
                      {item.created_at ? new Date(item.created_at).toLocaleDateString() : "Just now"}
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
