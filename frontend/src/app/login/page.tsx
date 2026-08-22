"use client";

import React, { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuthStore } from "@/services/authStore";
import { api } from "@/services/api";
import { toast } from "sonner";
import { ShieldCheck, Mail, Lock, LogIn, Key, ArrowRight, CheckCircle2 } from "lucide-react";

export default function LoginPage() {
  const router = useRouter();
  const { setAuth } = useAuthStore();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [mfaCode, setMfaCode] = useState("");
  const [mfaRequired, setMfaRequired] = useState(false);
  const [mfaUserId, setMfaUserId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);

    try {
      if (mfaRequired && mfaUserId) {
        // MFA Verification step
        const res = await api.post("/auth/mfa/verify", {
          user_id: mfaUserId,
          code: mfaCode.trim(),
        });

        const { access_token, refresh_token, user } = res.data;
        setAuth(user, access_token, refresh_token);
        toast.success("Authentication successful!");
        router.push(user.role === "ADMIN" ? "/admin/dashboard" : "/dashboard");
      } else {
        // Primary email/password step
        const res = await api.post("/auth/login", {
          email: email.trim(),
          password,
        });

        if (res.data.mfa_required) {
          setMfaRequired(true);
          setMfaUserId(res.data.user?.id || null);
          toast.info("Please enter your 6-digit Authenticator TOTP code.");
        } else {
          const { access_token, refresh_token, user } = res.data;
          setAuth(user, access_token, refresh_token);
          toast.success("Welcome back!");
          router.push(user.role === "ADMIN" ? "/admin/dashboard" : "/dashboard");
        }
      }
    } catch (err: any) {
      console.error(err);
      toast.error(err.response?.data?.message || "Invalid login credentials.");
    } finally {
      setLoading(false);
    }
  };

  const handleGoogleAuth = async () => {
    try {
      const res = await api.get("/auth/google");
      if (res.data.url) {
        window.location.href = res.data.url;
      }
    } catch (err: any) {
      toast.error("Failed to initiate Google OAuth.");
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center p-3.5 sm:p-6 bg-slate-50 dark:bg-slate-950 w-full">
      <div className="w-full max-w-md bg-white dark:bg-slate-900 rounded-2xl sm:rounded-3xl p-5 sm:p-8 border border-slate-200 dark:border-slate-800 shadow-xl space-y-5 sm:space-y-6">
        {/* Header */}
        <div className="text-center space-y-2">
          <div className="h-11 w-11 sm:h-12 sm:w-12 rounded-2xl bg-navy-800 text-white flex items-center justify-center mx-auto shadow-md">
            <ShieldCheck className="h-6 w-6 sm:h-7 sm:w-7 text-emerald-400" />
          </div>
          <h2 className="text-lg sm:text-xl font-bold text-slate-900 dark:text-white">
            Official Publisher Access
          </h2>
          <p className="text-xs text-slate-500 dark:text-slate-400 leading-relaxed">
            Sign in to register content or manage government cryptographic keys
          </p>
        </div>

        {/* Login Form */}
        <form onSubmit={handleLogin} className="space-y-4">
          {!mfaRequired ? (
            <>
              <div>
                <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1.5">
                  Official Email Address
                </label>
                <div className="relative">
                  <Mail className="h-4 w-4 text-slate-400 absolute left-3.5 top-3.5" />
                  <input
                    type="email"
                    required
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="publisher@pib.gov.in"
                    className="w-full rounded-xl pl-10 pr-4 py-2.5 text-xs sm:text-sm bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 focus:outline-none focus:ring-2 focus:ring-navy-500 text-slate-900 dark:text-white min-h-[44px]"
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1.5">
                  Password
                </label>
                <div className="relative">
                  <Lock className="h-4 w-4 text-slate-400 absolute left-3.5 top-3.5" />
                  <input
                    type="password"
                    required
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="••••••••••••"
                    className="w-full rounded-xl pl-10 pr-4 py-2.5 text-xs sm:text-sm bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 focus:outline-none focus:ring-2 focus:ring-navy-500 text-slate-900 dark:text-white min-h-[44px]"
                  />
                </div>
              </div>
            </>
          ) : (
            <div className="space-y-2">
              <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300">
                6-Digit Multi-Factor Authentication Code
              </label>
              <div className="relative">
                <Key className="h-4 w-4 text-slate-400 absolute left-3.5 top-3.5" />
                <input
                  type="text"
                  maxLength={6}
                  required
                  autoFocus
                  value={mfaCode}
                  onChange={(e) => setMfaCode(e.target.value)}
                  placeholder="123456"
                  className="w-full rounded-xl pl-10 pr-4 py-2.5 text-xs sm:text-sm tracking-widest font-mono bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 focus:outline-none focus:ring-2 focus:ring-navy-500 text-slate-900 dark:text-white min-h-[44px]"
                />
              </div>
            </div>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full py-3 rounded-xl bg-navy-800 hover:bg-navy-700 text-white font-bold text-xs transition-all shadow-md flex items-center justify-center gap-2 disabled:opacity-50 min-h-[44px]"
          >
            {loading ? (
              <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
            ) : (
              <>
                <LogIn className="h-4 w-4 flex-shrink-0" />
                <span>{mfaRequired ? "Verify Code & Sign In" : "Sign In to Console"}</span>
              </>
            )}
          </button>
        </form>

        {/* Divider */}
        <div className="relative flex items-center justify-center">
          <div className="border-t border-slate-200 dark:border-slate-800 w-full" />
          <span className="bg-white dark:bg-slate-900 px-3 text-[11px] font-semibold text-slate-400 uppercase tracking-wider absolute">
            or
          </span>
        </div>

        {/* Google OAuth Button */}
        <button
          type="button"
          onClick={handleGoogleAuth}
          className="w-full py-2.5 px-3 sm:px-4 rounded-xl border border-slate-200 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-800 text-xs font-semibold text-slate-700 dark:text-slate-300 transition-colors flex items-center justify-center gap-2.5 min-h-[44px]"
        >
          <svg className="h-4 w-4 flex-shrink-0" viewBox="0 0 24 24">
            <path
              fill="#4285F4"
              d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
            />
            <path
              fill="#34A853"
              d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
            />
            <path
              fill="#FBBC05"
              d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l2.85-2.22.81-.63z"
            />
            <path
              fill="#EA4335"
              d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.52 6.16-4.52z"
            />
          </svg>
          <span className="truncate">Continue with Google Account</span>
        </button>

        {/* Footer Link */}
        <p className="text-center text-xs text-slate-500 dark:text-slate-400">
          Need a new publisher account?{" "}
          <Link href="/register" className="font-semibold text-navy-800 dark:text-navy-300 hover:underline">
            Register Organization
          </Link>
        </p>
      </div>
    </div>
  );
}
