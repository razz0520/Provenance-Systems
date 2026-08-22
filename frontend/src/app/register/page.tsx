"use client";

import React, { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { api } from "@/services/api";
import { toast } from "sonner";
import {
  ShieldCheck,
  Building2,
  Mail,
  Lock,
  Globe,
  UserPlus,
  Key,
  CheckCircle2,
} from "lucide-react";

export default function RegisterPage() {
  const router = useRouter();
  const [formData, setFormData] = useState({
    email: "",
    password: "",
    confirmPassword: "",
    organization_name: "",
    organization_domain: "",
    department: "",
    designation: "",
  });
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (formData.password !== formData.confirmPassword) {
      toast.error("Passwords do not match.");
      return;
    }

    if (formData.password.length < 8) {
      toast.error("Password must be at least 8 characters long.");
      return;
    }

    setLoading(true);

    try {
      await api.post("/auth/register", {
        email: formData.email.trim(),
        password: formData.password,
        organization_name: formData.organization_name.trim(),
        organization_domain: formData.organization_domain.trim() || formData.email.split("@")[1],
        department: formData.department.trim() || null,
        designation: formData.designation.trim() || null,
      });

      toast.success("Publisher account successfully registered! Please sign in.");
      router.push("/login");
    } catch (err: any) {
      console.error(err);
      toast.error(err.response?.data?.message || "Registration failed.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center p-3.5 sm:p-6 bg-slate-50 dark:bg-slate-950 w-full">
      <div className="w-full max-w-lg bg-white dark:bg-slate-900 rounded-2xl sm:rounded-3xl p-5 sm:p-8 border border-slate-200 dark:border-slate-800 shadow-xl space-y-5 sm:space-y-6">
        {/* Header */}
        <div className="text-center space-y-2">
          <div className="h-11 w-11 sm:h-12 sm:w-12 rounded-2xl bg-navy-800 text-white flex items-center justify-center mx-auto shadow-md">
            <ShieldCheck className="h-6 w-6 sm:h-7 sm:w-7 text-emerald-400" />
          </div>
          <h2 className="text-lg sm:text-xl font-bold text-slate-900 dark:text-white">
            Register Government Publisher
          </h2>
          <p className="text-xs text-slate-500 dark:text-slate-400 leading-relaxed">
            Provision Ed25519 signing credentials to register authentic official publications
          </p>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="space-y-3.5 sm:space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 sm:gap-4">
            <div>
              <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1.5">
                Organization Name *
              </label>
              <div className="relative">
                <Building2 className="h-4 w-4 text-slate-400 absolute left-3.5 top-3.5" />
                <input
                  type="text"
                  required
                  value={formData.organization_name}
                  onChange={(e) => setFormData({ ...formData, organization_name: e.target.value })}
                  placeholder="Press Information Bureau"
                  className="w-full rounded-xl pl-10 pr-3.5 py-2.5 text-xs bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 focus:outline-none focus:ring-2 focus:ring-navy-500 text-slate-900 dark:text-white min-h-[44px]"
                />
              </div>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1.5">
                Official Domain *
              </label>
              <div className="relative">
                <Globe className="h-4 w-4 text-slate-400 absolute left-3.5 top-3.5" />
                <input
                  type="text"
                  required
                  value={formData.organization_domain}
                  onChange={(e) => setFormData({ ...formData, organization_domain: e.target.value })}
                  placeholder="pib.gov.in"
                  className="w-full rounded-xl pl-10 pr-3.5 py-2.5 text-xs bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 focus:outline-none focus:ring-2 focus:ring-navy-500 text-slate-900 dark:text-white min-h-[44px]"
                />
              </div>
            </div>
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1.5">
              Official Email Address *
            </label>
            <div className="relative">
              <Mail className="h-4 w-4 text-slate-400 absolute left-3.5 top-3.5" />
              <input
                type="email"
                required
                value={formData.email}
                onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                placeholder="officer@pib.gov.in"
                className="w-full rounded-xl pl-10 pr-3.5 py-2.5 text-xs bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 focus:outline-none focus:ring-2 focus:ring-navy-500 text-slate-900 dark:text-white min-h-[44px]"
              />
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 sm:gap-4">
            <div>
              <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1.5">
                Department (Optional)
              </label>
              <input
                type="text"
                value={formData.department}
                onChange={(e) => setFormData({ ...formData, department: e.target.value })}
                placeholder="Media & Communications"
                className="w-full rounded-xl px-3.5 py-2.5 text-xs bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 focus:outline-none focus:ring-2 focus:ring-navy-500 text-slate-900 dark:text-white min-h-[44px]"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1.5">
                Designation (Optional)
              </label>
              <input
                type="text"
                value={formData.designation}
                onChange={(e) => setFormData({ ...formData, designation: e.target.value })}
                placeholder="Joint Director"
                className="w-full rounded-xl px-3.5 py-2.5 text-xs bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 focus:outline-none focus:ring-2 focus:ring-navy-500 text-slate-900 dark:text-white min-h-[44px]"
              />
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 sm:gap-4">
            <div>
              <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1.5">
                Password *
              </label>
              <div className="relative">
                <Lock className="h-4 w-4 text-slate-400 absolute left-3.5 top-3.5" />
                <input
                  type="password"
                  required
                  value={formData.password}
                  onChange={(e) => setFormData({ ...formData, password: e.target.value })}
                  placeholder="Min 8 characters"
                  className="w-full rounded-xl pl-10 pr-3.5 py-2.5 text-xs bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 focus:outline-none focus:ring-2 focus:ring-navy-500 text-slate-900 dark:text-white min-h-[44px]"
                />
              </div>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1.5">
                Confirm Password *
              </label>
              <div className="relative">
                <Lock className="h-4 w-4 text-slate-400 absolute left-3.5 top-3.5" />
                <input
                  type="password"
                  required
                  value={formData.confirmPassword}
                  onChange={(e) => setFormData({ ...formData, confirmPassword: e.target.value })}
                  placeholder="Re-enter password"
                  className="w-full rounded-xl pl-10 pr-3.5 py-2.5 text-xs bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 focus:outline-none focus:ring-2 focus:ring-navy-500 text-slate-900 dark:text-white min-h-[44px]"
                />
              </div>
            </div>
          </div>

          {/* Cryptographic Key Notification Box */}
          <div className="p-3.5 rounded-xl bg-navy-50 dark:bg-navy-950/40 border border-navy-100 dark:border-navy-900 text-xs text-navy-800 dark:text-navy-300 flex items-start gap-2.5">
            <Key className="h-4 w-4 text-navy-700 dark:text-navy-400 flex-shrink-0 mt-0.5" />
            <p className="leading-relaxed">
              An <strong>Ed25519 cryptographic keypair</strong> will be generated automatically upon registration to digitally sign all future content manifests.
            </p>
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full py-3 rounded-xl bg-navy-800 hover:bg-navy-700 text-white font-bold text-xs transition-all shadow-md flex items-center justify-center gap-2 disabled:opacity-50 min-h-[44px]"
          >
            {loading ? (
              <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
            ) : (
              <>
                <UserPlus className="h-4 w-4 flex-shrink-0" />
                <span>Register Publisher Organization</span>
              </>
            )}
          </button>
        </form>

        {/* Link back to login */}
        <p className="text-center text-xs text-slate-500 dark:text-slate-400">
          Already registered?{" "}
          <Link href="/login" className="font-semibold text-navy-800 dark:text-navy-300 hover:underline">
            Sign In Here
          </Link>
        </p>
      </div>
    </div>
  );
}
