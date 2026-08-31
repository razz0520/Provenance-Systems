"use client";

import React, { useEffect, useState } from "react";
import { Badge } from "@/components/Badge";
import { TableSkeleton } from "@/components/LoadingSkeleton";
import { useAuthStore } from "@/services/authStore";
import { api } from "@/services/api";
import { toast } from "sonner";
import {
  KeyRound,
  Plus,
  ShieldCheck,
  Ban,
  PauseCircle,
  Copy,
  CheckCircle2,
  Lock,
  Calendar,
} from "lucide-react";

export default function CredentialsPage() {
  const { user } = useAuthStore();
  const [credentials, setCredentials] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [showIssueModal, setShowIssueModal] = useState(false);
  const [validDays, setValidDays] = useState(365);
  const [issuing, setIssuing] = useState(false);

  const fetchCredentials = async () => {
    setLoading(true);
    try {
      const res = await api.get("/credentials");
      setCredentials(res.data || []);
    } catch (err) {
      console.error(err);
      toast.error("Failed to load credentials.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchCredentials();
  }, []);

  const handleIssueCredential = async (e: React.FormEvent) => {
    e.preventDefault();
    setIssuing(true);
    try {
      await api.post("/credentials", {
        credential_type: "SECONDARY",
        valid_days: Number(validDays),
      });
      toast.success("Secondary credential issued successfully!");
      setShowIssueModal(false);
      fetchCredentials();
    } catch (err: any) {
      console.error(err);
      toast.error(err.response?.data?.message || "Failed to issue credential.");
    } finally {
      setIssuing(false);
    }
  };

  const copyPublicKey = () => {
    if (user?.public_key) {
      navigator.clipboard.writeText(user.public_key);
      toast.success("Public Key copied to clipboard!");
    }
  };

  return (
    <div className="space-y-6 sm:space-y-8 max-w-7xl mx-auto w-full">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 sm:gap-4">
        <div>
          <h2 className="text-xl sm:text-2xl font-bold text-slate-900 dark:text-white">
            Cryptographic Credentials & Keys
          </h2>
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
            View Ed25519 asymmetric keypairs and active publisher certificates
          </p>
        </div>

        <button
          onClick={() => setShowIssueModal(true)}
          className="inline-flex items-center justify-center gap-2 px-4 sm:px-5 py-2.5 rounded-xl bg-navy-800 hover:bg-navy-700 text-white font-bold text-xs transition-all shadow-md w-full sm:w-fit min-h-[40px]"
        >
          <Plus className="h-4 w-4 flex-shrink-0" />
          <span>Issue Secondary Credential</span>
        </button>
      </div>

      {/* Primary Ed25519 Public Key Card */}
      <div className="rounded-2xl sm:rounded-3xl p-4 sm:p-6 md:p-8 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 shadow-sm space-y-4">
        <div className="flex flex-col xs:flex-row xs:items-center justify-between gap-3">
          <div className="flex items-center gap-3 min-w-0">
            <div className="h-9 w-9 sm:h-10 sm:w-10 rounded-xl bg-navy-50 dark:bg-slate-800 text-navy-800 dark:text-navy-300 flex items-center justify-center flex-shrink-0">
              <KeyRound className="h-4 w-4 sm:h-5 sm:w-5" />
            </div>
            <div className="min-w-0">
              <h3 className="text-xs sm:text-sm font-bold text-slate-900 dark:text-white truncate">
                Ed25519 Public Certificate Key
              </h3>
              <p className="text-[11px] sm:text-xs text-slate-500 dark:text-slate-400 truncate">
                Bound to {user?.organization_name} ({user?.organization_domain})
              </p>
            </div>
          </div>

          <button
            onClick={copyPublicKey}
            className="inline-flex items-center justify-center gap-1.5 px-3 py-1.5 rounded-xl border border-slate-200 dark:border-slate-700 text-xs font-semibold text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors w-fit min-h-[36px]"
          >
            <Copy className="h-3.5 w-3.5 flex-shrink-0" />
            <span>Copy PEM</span>
          </button>
        </div>

        <div className="p-3.5 sm:p-4 rounded-2xl bg-slate-50 dark:bg-slate-800/60 border border-slate-200 dark:border-slate-700 overflow-hidden">
          <pre className="hash-font text-[11px] sm:text-xs text-slate-800 dark:text-slate-200 whitespace-pre-wrap break-all leading-relaxed max-h-[140px] overflow-y-auto">
            {user?.public_key || "Generating Ed25519 Public Key..."}
          </pre>
        </div>
      </div>

      {/* Credentials Table */}
      <div className="rounded-2xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 shadow-sm p-4 sm:p-6 space-y-4">
        <h3 className="text-sm sm:text-base font-bold text-slate-900 dark:text-white">
          Active & Historical Credentials
        </h3>

        {loading ? (
          <TableSkeleton rows={3} />
        ) : credentials.length === 0 ? (
          <div className="p-8 text-center text-slate-400 text-xs">
            No credentials found.
          </div>
        ) : (
          <div className="overflow-x-auto -mx-4 sm:mx-0 px-4 sm:px-0">
            <table className="w-full text-left text-xs min-w-[550px]">
              <thead className="text-[11px] uppercase font-bold text-slate-400 border-b border-slate-100 dark:border-slate-800">
                <tr>
                  <th className="py-3 px-4">Credential ID</th>
                  <th className="py-3 px-4">Type</th>
                  <th className="py-3 px-4">Valid From</th>
                  <th className="py-3 px-4">Valid Until</th>
                  <th className="py-3 px-4">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-800/60">
                {credentials.map((cred) => (
                  <tr
                    key={cred.id}
                    className="hover:bg-slate-50 dark:hover:bg-slate-800/40 transition-colors"
                  >
                    <td className="py-3.5 px-4 font-mono text-slate-600 dark:text-slate-300">
                      {cred.id.substring(0, 8)}...
                    </td>
                    <td className="py-3.5 px-4 font-semibold uppercase text-slate-900 dark:text-white">
                      {cred.credential_type}
                    </td>
                    <td className="py-3.5 px-4 text-slate-500 whitespace-nowrap">
                      {new Date(cred.valid_from).toLocaleDateString()}
                    </td>
                    <td className="py-3.5 px-4 text-slate-500 whitespace-nowrap">
                      {new Date(cred.valid_until).toLocaleDateString()}
                    </td>
                    <td className="py-3.5 px-4">
                      <Badge variant={cred.status}>{cred.status}</Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Issue Modal */}
      {showIssueModal && (
        <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-3.5 sm:p-4">
          <form
            onSubmit={handleIssueCredential}
            className="bg-white dark:bg-slate-900 rounded-2xl sm:rounded-3xl p-4 sm:p-6 md:p-8 max-w-md w-full border border-slate-200 dark:border-slate-800 shadow-2xl space-y-4 max-h-[90vh] overflow-y-auto"
          >
            <h3 className="text-sm sm:text-base font-bold text-slate-900 dark:text-white">
              Issue Secondary Credential
            </h3>
            <p className="text-xs text-slate-500 dark:text-slate-400 leading-relaxed">
              Provision a secondary signing certificate for departmental operations.
            </p>

            <div>
              <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1.5">
                Validity Duration (Days)
              </label>
              <input
                type="number"
                min={30}
                max={1825}
                value={validDays}
                onChange={(e) => setValidDays(Number(e.target.value))}
                className="w-full rounded-xl px-3.5 py-2.5 text-xs bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 focus:outline-none focus:ring-2 focus:ring-navy-500 text-slate-900 dark:text-white min-h-[40px]"
              />
            </div>

            <div className="flex flex-col-reverse sm:flex-row items-stretch sm:items-center justify-end gap-2.5 sm:gap-3 pt-2">
              <button
                type="button"
                onClick={() => setShowIssueModal(false)}
                className="px-4 py-2.5 rounded-xl border border-slate-200 dark:border-slate-700 text-xs font-semibold text-slate-700 dark:text-slate-300 text-center min-h-[40px]"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={issuing}
                className="px-5 py-2.5 rounded-xl bg-navy-800 hover:bg-navy-700 text-white text-xs font-semibold shadow-sm disabled:opacity-50 text-center min-h-[40px]"
              >
                {issuing ? "Issuing..." : "Issue Certificate"}
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}
