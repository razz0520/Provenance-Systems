"use client";

import React, { useEffect, useState } from "react";
import { Badge } from "@/components/Badge";
import { TableSkeleton } from "@/components/LoadingSkeleton";
import { api } from "@/services/api";
import { toast } from "sonner";
import {
  FileText,
  Search,
  Filter,
  Eye,
  RefreshCw,
  Ban,
  ShieldCheck,
  CheckCircle2,
  X,
  ExternalLink,
} from "lucide-react";

export default function ContentListPage() {
  const [contentList, setContentList] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState("");
  const [typeFilter, setTypeFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [selectedItem, setSelectedItem] = useState<any | null>(null);
  const [revokeModalItem, setRevokeModalItem] = useState<any | null>(null);
  const [revokeReason, setRevokeReason] = useState("");
  const [revoking, setRevoking] = useState(false);

  const fetchContent = async () => {
    setLoading(true);
    try {
      let url = "/content?limit=50";
      if (typeFilter) url += `&content_type=${typeFilter}`;
      if (statusFilter) url += `&status=${statusFilter}`;
      const res = await api.get(url);
      setContentList(res.data.items || []);
    } catch (err) {
      console.error(err);
      toast.error("Failed to load publications.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchContent();
  }, [typeFilter, statusFilter]);

  const handleRevoke = async () => {
    if (!revokeModalItem || !revokeReason.trim()) {
      toast.error("Please specify a revocation reason.");
      return;
    }

    setRevoking(true);
    try {
      await api.put(`/content/${revokeModalItem.id}/revoke`, {
        reason: revokeReason.trim(),
      });
      toast.success("Publication successfully revoked.");
      setRevokeModalItem(null);
      setRevokeReason("");
      fetchContent();
    } catch (err: any) {
      console.error(err);
      toast.error(err.response?.data?.message || "Revocation failed.");
    } finally {
      setRevoking(false);
    }
  };

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
            Publications Registry
          </h2>
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
            Browse, inspect cryptographic signatures, and manage content lifecycle
          </p>
        </div>

        <button
          onClick={fetchContent}
          className="p-2 sm:p-2.5 rounded-xl border border-slate-200 dark:border-slate-800 hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-600 dark:text-slate-400 text-xs font-semibold inline-flex items-center justify-center gap-2 transition-colors w-full sm:w-fit min-h-[40px]"
        >
          <RefreshCw className="h-3.5 w-3.5 flex-shrink-0" />
          <span>Refresh List</span>
        </button>
      </div>

      {/* Filters & Search Toolbar */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-2.5 sm:gap-3 p-3 sm:p-4 rounded-2xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 shadow-sm">
        {/* Search */}
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

        {/* Type Filter */}
        <select
          value={typeFilter}
          onChange={(e) => setTypeFilter(e.target.value)}
          className="rounded-xl px-3 py-2 text-xs bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-navy-500 min-h-[38px]"
        >
          <option value="">All Content Types</option>
          <option value="IMAGE">Image</option>
          <option value="VIDEO">Video</option>
          <option value="AUDIO">Audio</option>
          <option value="PDF">PDF</option>
          <option value="TEXT">Text</option>
        </select>

        {/* Status Filter */}
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

      {/* Publications Table */}
      <div className="rounded-2xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 shadow-sm p-4 sm:p-6 space-y-4">
        {loading ? (
          <TableSkeleton rows={6} />
        ) : filteredItems.length === 0 ? (
          <div className="p-12 text-center text-slate-400 text-xs">
            No publications found matching current filters.
          </div>
        ) : (
          <div className="overflow-x-auto -mx-4 sm:mx-0 px-4 sm:px-0">
            <table className="w-full text-left text-xs min-w-[650px]">
              <thead className="text-[11px] uppercase font-bold text-slate-400 border-b border-slate-100 dark:border-slate-800">
                <tr>
                  <th className="py-3 px-4">Filename</th>
                  <th className="py-3 px-4">Type</th>
                  <th className="py-3 px-4">Size</th>
                  <th className="py-3 px-4">SHA-256 Hash</th>
                  <th className="py-3 px-4">Status</th>
                  <th className="py-3 px-4">Created</th>
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
                    <td className="py-3.5 px-4 font-mono uppercase text-slate-500">
                      {item.content_type}
                    </td>
                    <td className="py-3.5 px-4 text-slate-500 whitespace-nowrap">
                      {(item.file_size / (1024 * 1024)).toFixed(2)} MB
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
                    <td className="py-3.5 px-4 text-right space-x-1 sm:space-x-2 whitespace-nowrap">
                      <button
                        onClick={() => setSelectedItem(item)}
                        title="View Metadata & Hashes"
                        className="p-1.5 rounded-lg text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800 hover:text-slate-900 dark:hover:text-white transition-colors"
                        aria-label="View Details"
                      >
                        <Eye className="h-4 w-4" />
                      </button>
                      {item.status === "ACTIVE" && (
                        <button
                          onClick={() => setRevokeModalItem(item)}
                          title="Revoke Content"
                          className="p-1.5 rounded-lg text-crimson-500 hover:bg-crimson-50 dark:hover:bg-crimson-950/50 transition-colors"
                          aria-label="Revoke Content"
                        >
                          <Ban className="h-4 w-4" />
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Detail Inspection Modal */}
      {selectedItem && (
        <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-3.5 sm:p-4">
          <div className="bg-white dark:bg-slate-900 rounded-2xl sm:rounded-3xl p-4 sm:p-6 md:p-8 max-w-xl w-full border border-slate-200 dark:border-slate-800 shadow-2xl space-y-4 sm:space-y-6 max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between">
              <h3 className="text-sm sm:text-base font-bold text-slate-900 dark:text-white">
                Content Provenance Details
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
                <div className="flex justify-between items-center">
                  <span className="text-slate-400 font-semibold text-[10px] uppercase">1. Content & Filename</span>
                  <Badge variant={selectedItem.status}>{selectedItem.status}</Badge>
                </div>
                <p className="font-semibold text-slate-900 dark:text-white mt-0.5 break-all">{selectedItem.original_filename}</p>
                <p className="text-[11px] text-slate-400 mt-0.5 font-mono">ID: {selectedItem.id}</p>
              </div>

              <div className="p-3 rounded-xl bg-slate-50 dark:bg-slate-800/60 border border-slate-200 dark:border-slate-700">
                <span className="text-slate-400 font-semibold text-[10px] uppercase">2. SHA-256 Cryptographic Hash</span>
                <p className="hash-font text-slate-900 dark:text-slate-200 break-all mt-0.5 select-all">{selectedItem.sha256_hash}</p>
              </div>

              <div className="p-3 rounded-xl bg-slate-50 dark:bg-slate-800/60 border border-slate-200 dark:border-slate-700">
                <span className="text-slate-400 font-semibold text-[10px] uppercase">3. Perceptual Fingerprint (pHash / MFCC)</span>
                <pre className="hash-font text-[11px] text-slate-900 dark:text-slate-200 break-all mt-0.5 bg-white dark:bg-slate-900 p-2 rounded-lg border border-slate-200 dark:border-slate-750 overflow-x-auto">
                  {JSON.stringify(selectedItem.perceptual_hash, null, 2)}
                </pre>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                <div className="p-2.5 rounded-xl bg-slate-50 dark:bg-slate-800/60 border border-slate-200 dark:border-slate-700">
                  <span className="text-slate-400 font-semibold text-[10px] uppercase">4. Content Type & Size</span>
                  <p className="font-semibold text-slate-900 dark:text-white mt-0.5 uppercase">{selectedItem.content_type} ({(selectedItem.file_size / (1024 * 1024)).toFixed(2)} MB)</p>
                </div>
                <div className="p-2.5 rounded-xl bg-slate-50 dark:bg-slate-800/60 border border-slate-200 dark:border-slate-700">
                  <span className="text-slate-400 font-semibold text-[10px] uppercase">5. Registered Timestamp</span>
                  <p className="font-semibold text-slate-900 dark:text-white mt-0.5">{selectedItem.created_at ? new Date(selectedItem.created_at).toLocaleString() : "-"}</p>
                </div>
              </div>
            </div>

            <div className="flex justify-end pt-2">
              <button
                onClick={() => setSelectedItem(null)}
                className="w-full sm:w-auto px-5 py-2.5 rounded-xl bg-navy-800 text-white text-xs font-semibold hover:bg-navy-700 min-h-[40px]"
              >
                Close Details
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Revocation Confirmation Modal */}
      {revokeModalItem && (
        <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-3.5 sm:p-4">
          <div className="bg-white dark:bg-slate-900 rounded-2xl sm:rounded-3xl p-4 sm:p-6 md:p-8 max-w-md w-full border border-crimson-200 dark:border-crimson-800 shadow-2xl space-y-4 max-h-[90vh] overflow-y-auto">
            <div className="flex items-center gap-3 text-crimson-600">
              <Ban className="h-5 w-5 sm:h-6 sm:w-6 flex-shrink-0" />
              <h3 className="text-sm sm:text-base font-bold text-slate-900 dark:text-white">
                Confirm Content Revocation
              </h3>
            </div>
            <p className="text-xs text-slate-500 dark:text-slate-400 leading-relaxed">
              Are you sure you want to revoke official authenticity for <strong>{revokeModalItem.original_filename}</strong>? Future citizen verifications will return <strong>PROVEN_INVALID</strong>.
            </p>

            <div className="space-y-1.5">
              <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300">
                Revocation Reason *
              </label>
              <textarea
                rows={3}
                value={revokeReason}
                onChange={(e) => setRevokeReason(e.target.value)}
                placeholder="e.g., Publication retracted due to revised statistics"
                className="w-full rounded-xl p-3 text-xs bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 focus:outline-none focus:ring-2 focus:ring-crimson-500 text-slate-900 dark:text-white"
              />
            </div>

            <div className="flex flex-col-reverse sm:flex-row items-stretch sm:items-center justify-end gap-2.5 sm:gap-3 pt-2">
              <button
                onClick={() => {
                  setRevokeModalItem(null);
                  setRevokeReason("");
                }}
                className="px-4 py-2.5 rounded-xl border border-slate-200 dark:border-slate-700 text-xs font-semibold text-slate-700 dark:text-slate-300 hover:bg-slate-100 text-center min-h-[40px]"
              >
                Cancel
              </button>
              <button
                onClick={handleRevoke}
                disabled={revoking}
                className="px-4 py-2.5 rounded-xl bg-crimson-600 hover:bg-crimson-700 text-white text-xs font-semibold transition-colors disabled:opacity-50 text-center min-h-[40px]"
              >
                {revoking ? "Revoking..." : "Confirm Revoke"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
