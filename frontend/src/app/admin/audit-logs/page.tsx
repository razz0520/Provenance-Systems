"use client";

import React, { useEffect, useState } from "react";
import { TableSkeleton } from "@/components/LoadingSkeleton";
import { api } from "@/services/api";
import { toast } from "sonner";
import {
  ScrollText,
  Search,
  RefreshCw,
  Eye,
  ShieldAlert,
  Calendar,
  X,
} from "lucide-react";

export default function AdminAuditLogsPage() {
  const [logs, setLogs] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState("");
  const [actionFilter, setActionFilter] = useState("");
  const [selectedLog, setSelectedLog] = useState<any | null>(null);

  const fetchLogs = async () => {
    setLoading(true);
    try {
      let url = "/admin/audit-logs?limit=100";
      if (actionFilter) url += `&action=${actionFilter}`;
      const res = await api.get(url);
      setLogs(res.data || []);
    } catch (err) {
      console.error(err);
      toast.error("Failed to load audit logs.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchLogs();
  }, [actionFilter]);

  const filteredLogs = logs.filter((log) => {
    const term = searchTerm.toLowerCase();
    return (
      log.action.toLowerCase().includes(term) ||
      (log.actor_id && log.actor_id.toLowerCase().includes(term))
    );
  });

  return (
    <div className="space-y-5 sm:space-y-6 max-w-7xl mx-auto w-full">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 sm:gap-4">
        <div>
          <h2 className="text-xl sm:text-2xl font-bold text-slate-900 dark:text-white">
            Immutable Audit Trail
          </h2>
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5 leading-relaxed">
            Tamper-evident log of all publisher registrations, signings, revocations, and system actions
          </p>
        </div>

        <button
          onClick={fetchLogs}
          className="p-2 sm:p-2.5 rounded-xl border border-slate-200 dark:border-slate-800 hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-600 dark:text-slate-400 text-xs font-semibold inline-flex items-center justify-center gap-2 transition-colors w-full sm:w-fit min-h-[40px]"
        >
          <RefreshCw className="h-3.5 w-3.5 flex-shrink-0" />
          <span>Refresh Trail</span>
        </button>
      </div>

      {/* Filters */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5 sm:gap-3 p-3 sm:p-4 rounded-2xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 shadow-sm">
        <div className="relative">
          <Search className="h-4 w-4 text-slate-400 absolute left-3 top-3" />
          <input
            type="text"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            placeholder="Search by action or actor ID..."
            className="w-full rounded-xl pl-9 pr-3 py-2 text-xs bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-navy-500 min-h-[38px]"
          />
        </div>

        <select
          value={actionFilter}
          onChange={(e) => setActionFilter(e.target.value)}
          className="rounded-xl px-3 py-2 text-xs bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-navy-500 min-h-[38px]"
        >
          <option value="">All Audit Actions</option>
          <option value="CONTENT_REGISTER">CONTENT_REGISTER</option>
          <option value="CONTENT_SUPERSEDED">CONTENT_SUPERSEDED</option>
          <option value="CONTENT_REVOKED">CONTENT_REVOKED</option>
          <option value="LOGIN_SUCCESS">LOGIN_SUCCESS</option>
          <option value="CREDENTIAL_CREATED">CREDENTIAL_CREATED</option>
          <option value="CREDENTIAL_REVOKED">CREDENTIAL_REVOKED</option>
          <option value="ROLE_ASSIGNED">ROLE_ASSIGNED</option>
        </select>
      </div>

      {/* Audit Logs Table */}
      <div className="rounded-2xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 shadow-sm p-4 sm:p-6 space-y-4">
        {loading ? (
          <TableSkeleton rows={6} />
        ) : filteredLogs.length === 0 ? (
          <div className="p-12 text-center text-slate-400 text-xs">
            No audit events found.
          </div>
        ) : (
          <div className="overflow-x-auto -mx-4 sm:mx-0 px-4 sm:px-0">
            <table className="w-full text-left text-xs min-w-[650px]">
              <thead className="text-[11px] uppercase font-bold text-slate-400 border-b border-slate-100 dark:border-slate-800">
                <tr>
                  <th className="py-3 px-4">Action</th>
                  <th className="py-3 px-4">Actor ID</th>
                  <th className="py-3 px-4">IP Address</th>
                  <th className="py-3 px-4">Timestamp</th>
                  <th className="py-3 px-4 text-right">Details</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-800/60">
                {filteredLogs.map((log) => (
                  <tr
                    key={log.id}
                    className="hover:bg-slate-50 dark:hover:bg-slate-800/40 transition-colors"
                  >
                    <td className="py-3.5 px-4 font-mono font-semibold text-slate-900 dark:text-white">
                      <span className="px-2 py-0.5 rounded-md bg-slate-100 dark:bg-slate-800 text-slate-800 dark:text-slate-200 border border-slate-200 dark:border-slate-700 text-[11px]">
                        {log.action}
                      </span>
                    </td>
                    <td className="py-3.5 px-4 font-mono text-slate-500 whitespace-nowrap">
                      {log.actor_id ? `${log.actor_id.substring(0, 8)}...` : "System / Anon"}
                    </td>
                    <td className="py-3.5 px-4 font-mono text-slate-500 whitespace-nowrap">
                      {log.ip_address || "Internal"}
                    </td>
                    <td className="py-3.5 px-4 text-slate-400 whitespace-nowrap">
                      {new Date(log.created_at).toLocaleString()}
                    </td>
                    <td className="py-3.5 px-4 text-right whitespace-nowrap">
                      <button
                        onClick={() => setSelectedLog(log)}
                        className="p-1.5 rounded-lg text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
                        aria-label="View Details"
                      >
                        <Eye className="h-4 w-4" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Detail Modal */}
      {selectedLog && (
        <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-3.5 sm:p-4">
          <div className="bg-white dark:bg-slate-900 rounded-2xl sm:rounded-3xl p-4 sm:p-6 md:p-8 max-w-xl w-full border border-slate-200 dark:border-slate-800 shadow-2xl space-y-4 sm:space-y-6 max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between">
              <h3 className="text-sm sm:text-base font-bold text-slate-900 dark:text-white">
                Audit Event JSON Inspector
              </h3>
              <button
                onClick={() => setSelectedLog(null)}
                className="p-1.5 rounded-lg text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800"
                aria-label="Close Modal"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <div className="space-y-3 text-xs">
              <div className="flex flex-col xs:flex-row xs:justify-between py-1 border-b border-slate-100 dark:border-slate-800 gap-1">
                <span className="text-slate-400">Event ID:</span>
                <span className="font-mono text-slate-800 dark:text-slate-200 break-all">{selectedLog.id}</span>
              </div>
              <div className="flex flex-col xs:flex-row xs:justify-between py-1 border-b border-slate-100 dark:border-slate-800 gap-1">
                <span className="text-slate-400">Action:</span>
                <span className="font-semibold text-slate-800 dark:text-slate-200">{selectedLog.action}</span>
              </div>

              <div>
                <span className="text-slate-400 font-semibold text-[10px] uppercase">Payload Details</span>
                <pre className="hash-font text-[11px] sm:text-xs text-slate-900 dark:text-slate-200 bg-slate-50 dark:bg-slate-800/80 p-3 rounded-xl border border-slate-200 dark:border-slate-700 overflow-x-auto mt-1 max-h-[220px]">
                  {JSON.stringify(selectedLog.details, null, 2)}
                </pre>
              </div>
            </div>

            <div className="flex justify-end pt-2">
              <button
                onClick={() => setSelectedLog(null)}
                className="w-full sm:w-auto px-5 py-2.5 rounded-xl bg-navy-800 text-white text-xs font-semibold hover:bg-navy-700 min-h-[40px]"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
