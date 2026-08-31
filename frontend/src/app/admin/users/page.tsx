"use client";

import React, { useEffect, useState } from "react";
import { Badge } from "@/components/Badge";
import { TableSkeleton } from "@/components/LoadingSkeleton";
import { api } from "@/services/api";
import { toast } from "sonner";
import {
  Users,
  Search,
  Shield,
  UserCheck,
  UserX,
  RefreshCw,
  Edit2,
  Check,
  X,
  KeyRound,
  Ban,
  PauseCircle,
} from "lucide-react";

export default function AdminUsersPage() {
  const [users, setUsers] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [roleFilter, setRoleFilter] = useState("");
  const [searchTerm, setSearchTerm] = useState("");
  const [editingUserId, setEditingUserId] = useState<string | null>(null);
  const [selectedRole, setSelectedRole] = useState<string>("PUBLISHER");

  // Admin Credential Management State
  const [selectedUserForCreds, setSelectedUserForCreds] = useState<any | null>(null);
  const [userCredentials, setUserCredentials] = useState<any[]>([]);
  const [loadingCreds, setLoadingCreds] = useState(false);

  const fetchUsers = async () => {
    setLoading(true);
    try {
      let url = "/admin/users?limit=100";
      if (roleFilter) url += `&role=${roleFilter}`;
      const res = await api.get(url);
      setUsers(res.data || []);
    } catch (err) {
      console.error("Failed to load users", err);
      toast.error("Could not fetch user directory.");
    } finally {
      setLoading(false);
    }
  };

  const fetchUserCredentials = async (publisherId: string) => {
    setLoadingCreds(true);
    try {
      const res = await api.get(`/credentials?publisher_id=${publisherId}`);
      setUserCredentials(res.data || []);
    } catch (err) {
      console.error("Failed to load credentials for user", err);
      toast.error("Could not load credentials.");
    } finally {
      setLoadingCreds(false);
    }
  };

  const openCredentialManager = (u: any) => {
    setSelectedUserForCreds(u);
    fetchUserCredentials(u.id);
  };

  const handleAdminRevokeCredential = async (credId: string) => {
    const reason = prompt("Enter administrative revocation reason:");
    if (!reason) return;
    try {
      await api.put(`/credentials/${credId}/revoke`, { reason });
      toast.success("Credential revoked successfully.");
      if (selectedUserForCreds) {
        fetchUserCredentials(selectedUserForCreds.id);
      }
    } catch (err: any) {
      toast.error(err.response?.data?.message || "Failed to revoke credential.");
    }
  };

  const handleAdminSuspendCredential = async (credId: string) => {
    try {
      await api.put(`/credentials/${credId}/suspend`);
      toast.success("Credential suspended.");
      if (selectedUserForCreds) {
        fetchUserCredentials(selectedUserForCreds.id);
      }
    } catch (err: any) {
      toast.error("Failed to suspend credential.");
    }
  };

  useEffect(() => {
    fetchUsers();
  }, [roleFilter]);

  const handleRoleUpdate = async (userId: string) => {
    try {
      await api.put(`/admin/users/${userId}/role`, { role: selectedRole });
      toast.success("User role updated successfully.");
      setEditingUserId(null);
      fetchUsers();
    } catch (err: any) {
      console.error(err);
      toast.error(err.response?.data?.message || "Failed to update user role.");
    }
  };

  const filteredUsers = users.filter((u) => {
    const term = searchTerm.toLowerCase();
    return (
      u.email.toLowerCase().includes(term) ||
      u.organization_name.toLowerCase().includes(term)
    );
  });

  return (
    <div className="space-y-5 sm:space-y-6 max-w-7xl mx-auto w-full">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 sm:gap-4">
        <div>
          <h2 className="text-xl sm:text-2xl font-bold text-slate-900 dark:text-white">
            User Directory & Access Control
          </h2>
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5 leading-relaxed">
            Manage authenticated publisher credentials, roles, and administrative privileges
          </p>
        </div>

        <button
          onClick={fetchUsers}
          className="p-2 sm:p-2.5 rounded-xl border border-slate-200 dark:border-slate-800 hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-600 dark:text-slate-400 text-xs font-semibold inline-flex items-center justify-center gap-2 transition-colors w-full sm:w-fit min-h-[40px]"
        >
          <RefreshCw className="h-3.5 w-3.5 flex-shrink-0" />
          <span>Refresh Directory</span>
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
            placeholder="Search by email or organization..."
            className="w-full rounded-xl pl-9 pr-3 py-2 text-xs bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-navy-500 min-h-[38px]"
          />
        </div>

        <select
          value={roleFilter}
          onChange={(e) => setRoleFilter(e.target.value)}
          className="rounded-xl px-3 py-2 text-xs bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-navy-500 min-h-[38px]"
        >
          <option value="">All Roles</option>
          <option value="ADMIN">Admin</option>
          <option value="PUBLISHER">Publisher</option>
          <option value="VIEWER">Viewer</option>
        </select>
      </div>

      {/* Users Table */}
      <div className="rounded-2xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 shadow-sm p-4 sm:p-6 space-y-4">
        {loading ? (
          <TableSkeleton rows={5} />
        ) : filteredUsers.length === 0 ? (
          <div className="p-12 text-center text-slate-400 text-xs">
            No users found matching query.
          </div>
        ) : (
          <div className="overflow-x-auto -mx-4 sm:mx-0 px-4 sm:px-0">
            <table className="w-full text-left text-xs min-w-[650px]">
              <thead className="text-[11px] uppercase font-bold text-slate-400 border-b border-slate-100 dark:border-slate-800">
                <tr>
                  <th className="py-3 px-4">User / Email</th>
                  <th className="py-3 px-4">Organization</th>
                  <th className="py-3 px-4">Domain</th>
                  <th className="py-3 px-4">Current Role</th>
                  <th className="py-3 px-4">Status</th>
                  <th className="py-3 px-4 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-800/60">
                {filteredUsers.map((u) => (
                  <tr
                    key={u.id}
                    className="hover:bg-slate-50 dark:hover:bg-slate-800/40 transition-colors"
                  >
                    <td className="py-3.5 px-4 font-semibold text-slate-900 dark:text-white max-w-[180px] truncate">
                      {u.email}
                    </td>
                    <td className="py-3.5 px-4 text-slate-600 dark:text-slate-300 max-w-[160px] truncate">
                      {u.organization_name}
                    </td>
                    <td className="py-3.5 px-4 font-mono text-slate-500 whitespace-nowrap">
                      {u.organization_domain}
                    </td>
                    <td className="py-3.5 px-4">
                      {editingUserId === u.id ? (
                        <div className="flex items-center gap-1.5 flex-wrap">
                          <select
                            value={selectedRole}
                            onChange={(e) => setSelectedRole(e.target.value)}
                            className="rounded-lg px-2 py-1 text-xs bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 min-h-[30px]"
                          >
                            <option value="ADMIN">ADMIN</option>
                            <option value="PUBLISHER">PUBLISHER</option>
                            <option value="VIEWER">VIEWER</option>
                          </select>
                          <button
                            onClick={() => handleRoleUpdate(u.id)}
                            className="p-1.5 rounded bg-emerald-600 text-white hover:bg-emerald-700 min-h-[30px] min-w-[30px] flex items-center justify-center"
                            aria-label="Confirm Role"
                          >
                            <Check className="h-3.5 w-3.5" />
                          </button>
                          <button
                            onClick={() => setEditingUserId(null)}
                            className="p-1.5 rounded bg-slate-200 dark:bg-slate-700 text-slate-600 dark:text-slate-300 min-h-[30px] min-w-[30px] flex items-center justify-center"
                            aria-label="Cancel"
                          >
                            <X className="h-3.5 w-3.5" />
                          </button>
                        </div>
                      ) : (
                        <Badge variant={u.role}>{u.role}</Badge>
                      )}
                    </td>
                    <td className="py-3.5 px-4 whitespace-nowrap">
                      <span
                        className={`inline-flex items-center gap-1 text-[11px] font-semibold ${
                          u.is_active
                            ? "text-emerald-600 dark:text-emerald-400"
                            : "text-slate-400"
                        }`}
                      >
                        <span className="w-1.5 h-1.5 rounded-full bg-current" />
                        {u.is_active ? "Active" : "Inactive"}
                      </span>
                    </td>
                    <td className="py-3.5 px-4 text-right whitespace-nowrap space-x-1.5">
                      {u.role === "PUBLISHER" && (
                        <button
                          onClick={() => openCredentialManager(u)}
                          title="Manage Publisher Credentials"
                          className="p-1.5 rounded-lg text-navy-600 dark:text-navy-300 hover:bg-navy-50 dark:hover:bg-slate-800 transition-colors"
                          aria-label="Manage Credentials"
                        >
                          <KeyRound className="h-4 w-4" />
                        </button>
                      )}
                      <button
                        onClick={() => {
                          setEditingUserId(u.id);
                          setSelectedRole(u.role);
                        }}
                        title="Change User Role"
                        className="p-1.5 rounded-lg text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
                        aria-label="Edit User"
                      >
                        <Edit2 className="h-4 w-4" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Admin Credential Management Modal */}
      {selectedUserForCreds && (
        <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-3.5 sm:p-4">
          <div className="bg-white dark:bg-slate-900 rounded-2xl sm:rounded-3xl p-4 sm:p-6 md:p-8 max-w-2xl w-full border border-slate-200 dark:border-slate-800 shadow-2xl space-y-5 max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="h-9 w-9 rounded-xl bg-navy-50 dark:bg-slate-800 text-navy-800 dark:text-navy-300 flex items-center justify-center">
                  <KeyRound className="h-5 w-5" />
                </div>
                <div>
                  <h3 className="text-sm sm:text-base font-bold text-slate-900 dark:text-white">
                    Publisher Signing Credentials
                  </h3>
                  <p className="text-xs text-slate-500 dark:text-slate-400">
                    {selectedUserForCreds.organization_name} ({selectedUserForCreds.email})
                  </p>
                </div>
              </div>
              <button
                onClick={() => setSelectedUserForCreds(null)}
                className="p-1.5 rounded-lg text-slate-400 hover:text-slate-600 dark:hover:text-white"
                aria-label="Close"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            {/* Credentials List */}
            {loadingCreds ? (
              <TableSkeleton rows={2} />
            ) : userCredentials.length === 0 ? (
              <div className="p-8 text-center text-slate-400 text-xs">
                No credentials issued for this publisher.
              </div>
            ) : (
              <div className="space-y-3">
                {userCredentials.map((cred) => (
                  <div
                    key={cred.id}
                    className="p-4 rounded-xl bg-slate-50 dark:bg-slate-800/60 border border-slate-200 dark:border-slate-700 flex flex-col sm:flex-row sm:items-center justify-between gap-3"
                  >
                    <div className="space-y-1">
                      <div className="flex items-center gap-2">
                        <span className="font-mono text-xs font-semibold text-slate-800 dark:text-slate-200">
                          {cred.id.substring(0, 8)}...{cred.id.substring(cred.id.length - 6)}
                        </span>
                        <Badge variant={cred.status}>{cred.status}</Badge>
                        <span className="text-[10px] uppercase font-bold text-slate-400">
                          {cred.credential_type}
                        </span>
                      </div>
                      <p className="text-[11px] text-slate-500">
                        Valid: {new Date(cred.valid_from).toLocaleDateString()} –{" "}
                        {new Date(cred.valid_until).toLocaleDateString()}
                      </p>
                      {cred.revocation_reason && (
                        <p className="text-[11px] text-crimson-600 dark:text-crimson-400 font-medium">
                          Reason: {cred.revocation_reason}
                        </p>
                      )}
                    </div>

                    {cred.status === "ACTIVE" && (
                      <div className="flex items-center gap-2 self-end sm:self-center">
                        <button
                          onClick={() => handleAdminSuspendCredential(cred.id)}
                          className="px-3 py-1.5 rounded-lg border border-gold-300 dark:border-gold-800 text-gold-700 dark:text-gold-300 hover:bg-gold-50 dark:hover:bg-gold-950/40 text-xs font-semibold flex items-center gap-1"
                        >
                          <PauseCircle className="h-3.5 w-3.5" />
                          <span>Suspend</span>
                        </button>
                        <button
                          onClick={() => handleAdminRevokeCredential(cred.id)}
                          className="px-3 py-1.5 rounded-lg bg-crimson-600 hover:bg-crimson-700 text-white text-xs font-semibold flex items-center gap-1"
                        >
                          <Ban className="h-3.5 w-3.5" />
                          <span>Revoke</span>
                        </button>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}

            <div className="flex justify-end pt-2">
              <button
                onClick={() => setSelectedUserForCreds(null)}
                className="px-4 py-2 rounded-xl border border-slate-200 dark:border-slate-700 text-xs font-semibold text-slate-700 dark:text-slate-300"
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
