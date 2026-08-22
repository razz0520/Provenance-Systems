"use client";

import React, { useEffect, useState } from "react";
import { Badge } from "@/components/Badge";
import { TableSkeleton } from "@/components/LoadingSkeleton";
import { api } from "@/services/api";
import { toast } from "sonner";
import {
  FileText,
  Search,
  RefreshCw,
  Eye,
  ShieldCheck,
  Ban,
  X,
  Layers,
} from "lucide-react";

export default function AdminContentPage() {
  const [contentList, setContentList] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [selectedItem, setSelectedItem] = useState<any | null>(null);

  const fetchContent = async () => {
    setLoading(true);
    try {
      let url = "/content?limit=100";
      if (statusFilter) url += `&status=${statusFilter}`;
      const res = await api.get(url);
      setContentList(res.data.items || []);
    } catch (err) {
      console.error(err);
      toast.error("Failed to load registry content.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchContent();
  }, [statusFilter]);

  const filteredItems = contentList.filter((item) => {
    const term = searchTerm.toLowerCase();
    return (
      item.original_filename.toLowerCase().includes(term) ||
      item.sha256_hash.toLowerCase().includes(term)
    );
  });

  return (
    <div className="space-y-5 sm:space-y-6 max-w-7xl mx-auto w-full">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 sm:gap-4">
        <div>
          <h2 className="text-xl sm:text-2xl font-bold text-slate-900 dark:text-white">
            Registry Master Content Ledger
          </h2>
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5 leading-relaxed">
            Global repository of signed official publications across all government publishers
          </p>
        </div>

        <button
          onClick={fetchContent}
          className="p-2 sm:p-2.5 rounded-xl border border-slate-200 dark:border-slate-800 hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-600 dark:text-slate-400 text-xs font-semibold inline-flex items-center justify-center gap-2 transition-colors w-full sm:w-fit min-h-[40px]"
        >
          <RefreshCw className="h-3.5 w-3.5 flex-shrink-0" />
          <span>Refresh Ledger</span>
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
            placeholder="Search by filename or hash..."
            className="w-full rounded-xl pl-9 pr-3 py-2 text-xs bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-navy-500 min-h-[38px]"
          />
        </div>

        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="rounded-xl px-3 py-2 text-xs bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-navy-500 min-h-[38px]"
        >
          <option value="">All Statuses</option>
          <option value="ACTIVE">Active</option>
          <option value="SUPERSEDED">Superseded</option>
          <option value="REVOKED">Revoked</option>
        </select>
      </div>

      {/* Table */}
      <div className="rounded-2xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 shadow-sm p-4 sm:p-6 space-y-4">
        {loading ? (
          <TableSkeleton rows={6} />
        ) : filteredItems.length === 0 ? (
          <div className="p-12 text-center text-slate-400 text-xs">
            No registered content records in ledger.
          </div>
        ) : (
          <div className="overflow-x-auto -mx-4 sm:mx-0 px-4 sm:px-0">
            <table className="w-full text-left text-xs min-w-[650px]">
              <thead className="text-[11px] uppercase font-bold text-slate-400 border-b border-slate-100 dark:border-slate-800">
                <tr>
                  <th className="py-3 px-4">Filename</th>
                  <th className="py-3 px-4">Publisher ID</th>
                  <th className="py-3 px-4">Type</th>
                  <th className="py-3 px-4">SHA-256 Hash</th>
                  <th className="py-3 px-4">Status</th>
                  <th className="py-3 px-4">Date</th>
                  <th className="py-3 px-4 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-800/60">
                {filteredItems.map((item) => (
                  <tr
                    key={item.id}
                    className="hover:bg-slate-50 dark:hover:bg-slate-800/40 transition-colors"
                  >
                    <td className="py-3.5 px-4 font-semibold text-slate-900 dark:text-white max-w-[180px] truncate">
                      {item.original_filename}
                    </td>
                    <td className="py-3.5 px-4 font-mono text-slate-500 whitespace-nowrap">
                      {item.publisher_id ? `${item.publisher_id.substring(0, 8)}...` : "-"}
                    </td>
                    <td className="py-3.5 px-4 font-mono uppercase text-slate-500">
                      {item.content_type}
                    </td>
                    <td className="py-3.5 px-4 hash-font text-slate-600 dark:text-slate-300">
                      {item.sha256_hash.substring(0, 16)}...
                    </td>
                    <td className="py-3.5 px-4">
                      <Badge variant={item.status}>{item.status}</Badge>
                    </td>
                    <td className="py-3.5 px-4 text-slate-400 whitespace-nowrap">
                      {item.created_at ? new Date(item.created_at).toLocaleDateString() : "-"}
                    </td>
                    <td className="py-3.5 px-4 text-right whitespace-nowrap">
                      <button
                        onClick={() => setSelectedItem(item)}
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

      {/* Modal */}
      {selectedItem && (
        <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-3.5 sm:p-4">
          <div className="bg-white dark:bg-slate-900 rounded-2xl sm:rounded-3xl p-4 sm:p-6 md:p-8 max-w-xl w-full border border-slate-200 dark:border-slate-800 shadow-2xl space-y-4 sm:space-y-6 max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between">
              <h3 className="text-sm sm:text-base font-bold text-slate-900 dark:text-white">
                Ledger Manifest Inspector
              </h3>
              <button
                onClick={() => setSelectedItem(null)}
                className="p-1.5 rounded-lg text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800"
                aria-label="Close Modal"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <div className="space-y-3 text-xs">
              <div className="p-3 rounded-xl bg-slate-50 dark:bg-slate-800/60 border border-slate-200 dark:border-slate-700">
                <span className="text-slate-400 font-semibold text-[10px] uppercase">Content ID</span>
                <p className="font-mono text-slate-900 dark:text-white mt-0.5 break-all">{selectedItem.id}</p>
              </div>

              <div className="p-3 rounded-xl bg-slate-50 dark:bg-slate-800/60 border border-slate-200 dark:border-slate-700">
                <span className="text-slate-400 font-semibold text-[10px] uppercase">SHA-256 Hash</span>
                <p className="hash-font text-slate-900 dark:text-slate-200 break-all mt-0.5">{selectedItem.sha256_hash}</p>
              </div>

              <div className="p-3 rounded-xl bg-slate-50 dark:bg-slate-800/60 border border-slate-200 dark:border-slate-700">
                <span className="text-slate-400 font-semibold text-[10px] uppercase">Perceptual Hashes</span>
                <p className="hash-font text-slate-900 dark:text-slate-200 break-all mt-0.5">
                  {JSON.stringify(selectedItem.perceptual_hash)}
                </p>
              </div>
            </div>

            <div className="flex justify-end pt-2">
              <button
                onClick={() => setSelectedItem(null)}
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
