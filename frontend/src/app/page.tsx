"use client";

import React, { useState } from "react";
import Link from "next/link";
import { FileUploadZone } from "@/components/FileUploadZone";
import { EvidenceMatrix, EvidenceData } from "@/components/EvidenceMatrix";
import { HashChainVisualizer } from "@/components/HashChainVisualizer";
import { useAuthStore } from "@/services/authStore";
import { api } from "@/services/api";
import { toast } from "sonner";
import {
  ShieldCheck,
  Search,
  FileText,
  Lock,
  ArrowRight,
  MessageSquare,
  Sparkles,
  CheckCircle,
  HelpCircle,
  QrCode,
  LogIn,
  LayoutDashboard,
} from "lucide-react";

export default function HomePage() {
  const { user, isAuthenticated } = useAuthStore();
  const [activeTab, setActiveTab] = useState<"file" | "text">("file");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [textContent, setTextContent] = useState("");
  const [verifying, setVerifying] = useState(false);
  const [result, setResult] = useState<EvidenceData | null>(null);

  const handleVerify = async () => {
    setVerifying(true);
    setResult(null);

    try {
      if (activeTab === "file") {
        if (!selectedFile) {
          toast.error("Please select a media file to verify.");
          setVerifying(false);
          return;
        }

        const formData = new FormData();
        formData.append("file", selectedFile);

        const res = await api.post("/verify", formData, {
          headers: { "Content-Type": "multipart/form-data" },
        });

        setResult(res.data);
        toast.success(`Verification complete: ${res.data.verdict}`);
      } else {
        if (!textContent.trim()) {
          toast.error("Please enter statement text to verify.");
          setVerifying(false);
          return;
        }

        const res = await api.post("/verify/text", { text: textContent.trim() });
        setResult(res.data);
        toast.success(`Verification complete: ${res.data.verdict}`);
      }
    } catch (err: any) {
      console.error(err);
      toast.error(err.response?.data?.message || "Verification request failed.");
    } finally {
      setVerifying(false);
    }
  };

  return (
    <div className="min-h-screen flex flex-col bg-slate-50 dark:bg-slate-950 w-full overflow-x-hidden">
      {/* Top Public Header */}
      <header className="border-b border-slate-200 dark:border-slate-800 bg-white/90 dark:bg-slate-900/90 backdrop-blur-md sticky top-0 z-40">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 h-16 flex items-center justify-between gap-3">
          <div className="flex items-center gap-2.5 sm:gap-3 min-w-0">
            <div className="h-9 w-9 sm:h-10 sm:w-10 rounded-xl bg-navy-800 text-white flex items-center justify-center shadow-md flex-shrink-0">
              <ShieldCheck className="h-5 w-5 sm:h-6 sm:w-6 text-emerald-400" />
            </div>
            <div className="min-w-0">
              <h1 className="text-xs sm:text-sm font-bold text-slate-900 dark:text-white leading-tight truncate">
                NATIONAL PROVENANCE REGISTRY
              </h1>
              <p className="text-[9px] sm:text-[10px] uppercase font-semibold text-slate-500 dark:text-slate-400 tracking-wider truncate hidden xs:block">
                Deepfake-Resistant Government Verification
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2 sm:gap-3 flex-shrink-0">
            {isAuthenticated ? (
              <Link
                href={user?.role === "ADMIN" ? "/admin/dashboard" : "/dashboard"}
                className="inline-flex items-center gap-1.5 sm:gap-2 px-3 sm:px-4 py-2 rounded-xl bg-navy-800 text-white text-xs font-semibold hover:bg-navy-700 transition-all shadow-sm min-h-[38px]"
              >
                <LayoutDashboard className="h-3.5 w-3.5 flex-shrink-0" />
                <span className="hidden sm:inline">Go to Workspace</span>
                <span className="sm:hidden">Workspace</span>
              </Link>
            ) : (
              <Link
                href="/login"
                className="inline-flex items-center gap-1.5 sm:gap-2 px-3 sm:px-4 py-2 rounded-xl bg-navy-800 text-white text-xs font-semibold hover:bg-navy-700 transition-all shadow-sm min-h-[38px]"
              >
                <LogIn className="h-3.5 w-3.5 flex-shrink-0" />
                <span>Publisher Login</span>
              </Link>
            )}
          </div>
        </div>
      </header>

      {/* Hero & Verification Section */}
      <main className="flex-1 max-w-5xl w-full mx-auto px-3.5 sm:px-6 py-6 sm:py-10 space-y-6 sm:space-y-8">
        {/* Title Banner */}
        <div className="text-center space-y-2.5 sm:space-y-3 max-w-3xl mx-auto px-2">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-emerald-50 dark:bg-emerald-950/40 text-emerald-700 dark:text-emerald-300 text-[11px] sm:text-xs font-semibold border border-emerald-200 dark:border-emerald-800">
            <Sparkles className="h-3.5 w-3.5 flex-shrink-0" />
            <span>Official Government Authenticity Checker</span>
          </div>
          <h2 className="text-2xl sm:text-3xl md:text-4xl font-extrabold text-slate-900 dark:text-white tracking-tight leading-tight">
            Verify Authentic Government Media & Detect Deepfakes
          </h2>
          <p className="text-xs sm:text-sm text-slate-600 dark:text-slate-300 max-w-2xl mx-auto leading-relaxed">
            Upload any official image, video, audio clip, or press release statement to cross-examine
            our immutable cryptographic hash chain and digital signature registry.
          </p>
        </div>

        {/* Verification Card */}
        <div className="bg-white dark:bg-slate-900 rounded-2xl sm:rounded-3xl p-4 sm:p-6 md:p-8 border border-slate-200 dark:border-slate-800 shadow-sm space-y-5 sm:space-y-6">
          {/* Responsive Tab Selector */}
          <div className="grid grid-cols-1 xs:grid-cols-2 gap-1 p-1 rounded-xl bg-slate-100 dark:bg-slate-800/80 max-w-md mx-auto border border-slate-200 dark:border-slate-700 w-full">
            <button
              onClick={() => {
                setActiveTab("file");
                setResult(null);
              }}
              className={`flex items-center justify-center gap-2 px-3 sm:px-4 py-2 rounded-lg text-xs font-semibold transition-all min-h-[38px] ${
                activeTab === "file"
                  ? "bg-white dark:bg-slate-900 text-navy-800 dark:text-white shadow-sm"
                  : "text-slate-500 hover:text-slate-900 dark:text-slate-400"
              }`}
            >
              <Search className="h-3.5 w-3.5 flex-shrink-0" />
              <span className="truncate">Media File</span>
            </button>
            <button
              onClick={() => {
                setActiveTab("text");
                setResult(null);
              }}
              className={`flex items-center justify-center gap-2 px-3 sm:px-4 py-2 rounded-lg text-xs font-semibold transition-all min-h-[38px] ${
                activeTab === "text"
                  ? "bg-white dark:bg-slate-900 text-navy-800 dark:text-white shadow-sm"
                  : "text-slate-500 hover:text-slate-900 dark:text-slate-400"
              }`}
            >
              <FileText className="h-3.5 w-3.5 flex-shrink-0" />
              <span className="truncate">Statement Text</span>
            </button>
          </div>

          {/* Form Content */}
          {activeTab === "file" ? (
            <FileUploadZone onFileSelect={(f) => setSelectedFile(f)} />
          ) : (
            <div className="space-y-2">
              <textarea
                rows={5}
                value={textContent}
                onChange={(e) => setTextContent(e.target.value)}
                placeholder="Paste the official statement or press release text here to check against the government registry..."
                className="w-full rounded-2xl p-3.5 sm:p-4 text-xs sm:text-sm bg-slate-50 dark:bg-slate-800/60 border border-slate-200 dark:border-slate-700 focus:outline-none focus:ring-2 focus:ring-navy-500 text-slate-900 dark:text-white leading-relaxed"
              />
            </div>
          )}

          {/* Verify Action Button */}
          <div className="flex justify-center">
            <button
              onClick={handleVerify}
              disabled={verifying}
              className="w-full sm:w-auto inline-flex items-center justify-center gap-2 px-6 sm:px-8 py-3.5 rounded-2xl bg-navy-800 hover:bg-navy-700 text-white font-bold text-xs sm:text-sm transition-all duration-150 shadow-md hover:shadow-lg disabled:opacity-50 min-h-[48px]"
            >
              {verifying ? (
                <>
                  <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                  Verifying Cryptographic Ledger...
                </>
              ) : (
                <>
                  <ShieldCheck className="h-4 w-4 text-emerald-400 flex-shrink-0" />
                  Verify Authenticity Now
                </>
              )}
            </button>
          </div>
        </div>

        {/* Results Matrix */}
        {result && <EvidenceMatrix data={result} />}

        {/* Hash Chain State Visualizer */}
        <HashChainVisualizer />

        {/* WhatsApp Tipline Banner */}
        <div className="rounded-2xl sm:rounded-3xl p-5 sm:p-8 bg-emerald-900 text-white flex flex-col md:flex-row items-stretch md:items-center justify-between gap-5 sm:gap-6 shadow-md">
          <div className="space-y-2 max-w-xl text-center md:text-left">
            <div className="inline-flex items-center gap-1.5 px-3 py-0.5 rounded-full bg-emerald-800/80 text-emerald-300 text-xs font-semibold border border-emerald-700">
              <MessageSquare className="h-3.5 w-3.5 flex-shrink-0" />
              <span>Citizen WhatsApp Tipline</span>
            </div>
            <h3 className="text-lg sm:text-xl font-bold">Verify Suspicious Media Directly on WhatsApp</h3>
            <p className="text-xs text-emerald-100 leading-relaxed">
              Forward any viral video, audio statement, or circular to the Official Government Verification Bot to receive instant cryptographic proof in seconds.
            </p>
          </div>

          <a
            href="https://wa.me/919999999999?text=Verify"
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center justify-center gap-2 px-6 py-3 rounded-2xl bg-white text-emerald-900 font-bold text-xs hover:bg-emerald-50 transition-all shadow-md flex-shrink-0 text-center min-h-[44px]"
          >
            <MessageSquare className="h-4 w-4 text-emerald-600 flex-shrink-0" />
            <span>Launch WhatsApp Bot</span>
          </a>
        </div>
      </main>

      {/* Public Footer */}
      <footer className="border-t border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 py-6 text-center text-xs text-slate-500 dark:text-slate-400 px-4">
        <p>© 2026 National Content Provenance & Verification Authority. All rights reserved.</p>
      </footer>
    </div>
  );
}
