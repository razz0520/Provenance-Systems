"use client";

import React, { useState } from "react";
import { Badge } from "@/components/Badge";
import { toast } from "sonner";
import {
  ShieldCheck,
  AlertTriangle,
  XCircle,
  HelpCircle,
  CheckCircle2,
  Lock,
  Building2,
  Fingerprint,
  Layers,
  FileCheck2,
  Eye,
  X,
  Copy,
  ChevronDown,
  ChevronUp,
  FileText,
  Clock,
  Sparkles,
  ExternalLink,
  Shield,
  Check,
  MinusCircle,
} from "lucide-react";

export interface EvidenceData {
  verification_id: string;
  submitted_hash: string;
  verdict: "VERIFIED" | "SUSPICIOUS" | "UNSIGNED" | "PROVEN_INVALID" | string;
  confidence_score: number;
  verification_time_ms: number;
  evidence_bundle: {
    match_type: string;
    sha256_submitted: string;
    matched_hash?: string | null;
    sha256_match?: boolean | null;
    similarity_score: number;
    publisher_name?: string | null;
    publisher_domain?: string | null;
    publisher_public_key?: string | null;
    digital_signature?: string | null;
    signature_valid: boolean;
    signing_algorithm?: string | null;
    manifest_valid: boolean;
    manifest_data?: Record<string, any> | null;
    chain_block_id?: number | null;
    chain_integrity: boolean;
    notice?: string | null;
    content_metadata?: Record<string, any> | null;
    perceptual_hash_submitted?: Record<string, any> | null;
    perceptual_hash_matched?: Record<string, any> | null;
    perceptual_similarity_score?: number | null;
    perceptual_match_status?: "EXACT_MATCH" | "SIMILAR_MATCH" | "NO_MATCH" | "NOT_APPLICABLE" | string | null;
    superseded_by_id?: string | null;
  };
  created_at: string;
}

interface EvidenceMatrixProps {
  data: EvidenceData;
}

export function EvidenceMatrix({ data }: EvidenceMatrixProps) {
  const [showModal, setShowModal] = useState(false);
  const [expandedSections, setExpandedSections] = useState<Record<string, boolean>>({});

  const { verdict, confidence_score, evidence_bundle, verification_time_ms } = data;
  const isVerified = verdict === "VERIFIED";
  const isSuspicious = verdict === "SUSPICIOUS";
  const isInvalid = verdict === "PROVEN_INVALID";
  const isUnsigned = verdict === "UNSIGNED";

  const getVerdictIcon = () => {
    if (isVerified) return <CheckCircle2 className="h-6 w-6 sm:h-8 sm:w-8 text-emerald-500 flex-shrink-0" />;
    if (isSuspicious) return <AlertTriangle className="h-6 w-6 sm:h-8 sm:w-8 text-gold-500 flex-shrink-0" />;
    if (isInvalid) return <XCircle className="h-6 w-6 sm:h-8 sm:w-8 text-crimson-500 flex-shrink-0" />;
    return <HelpCircle className="h-6 w-6 sm:h-8 sm:w-8 text-slate-400 flex-shrink-0" />;
  };

  const getVerdictTitle = () => {
    if (isVerified) return "Authentic Government Content Verified";
    if (isSuspicious) return "Potential Deepfake / Modified Content";
    if (isInvalid) return "Invalid / Revoked Official Content";
    return "No Official Provenance Record Found";
  };

  const getVerdictDescription = () => {
    if (isVerified)
      return "This content matches an official government publication. Cryptographic signature, provenance manifest, and hash chain integrity have been validated.";
    if (isSuspicious)
      return (
        evidence_bundle.notice ||
        "This media exhibits high visual/acoustic similarity to registered government content, but exhibits structural alterations or compression anomalies."
      );
    if (isInvalid)
      return evidence_bundle.notice || "This publication has been officially retracted or failed digital signature verification.";
    return "No matching cryptographic provenance record exists in the national ledger for this submitted file or statement.";
  };

  const copyToClipboard = (text: string, label: string) => {
    navigator.clipboard.writeText(text);
    toast.success(`${label} copied to clipboard!`);
  };

  const toggleSection = (section: string) => {
    setExpandedSections((prev) => ({ ...prev, [section]: !prev[section] }));
  };

  // 1. SHA-256 status
  const isSha256Verified = Boolean(evidence_bundle.sha256_match);
  
  // 2. Perceptual Fingerprint status
  const isPerceptualNA =
    evidence_bundle.perceptual_match_status === "NOT_APPLICABLE" ||
    evidence_bundle.perceptual_hash_submitted?.status === "NOT_APPLICABLE";
  const isPerceptualVerified =
    !isPerceptualNA &&
    (evidence_bundle.perceptual_match_status === "EXACT_MATCH" ||
      (evidence_bundle.perceptual_similarity_score ?? 0) >= 95);
  const isPerceptualSuspicious =
    !isPerceptualNA &&
    !isPerceptualVerified &&
    (evidence_bundle.perceptual_similarity_score ?? 0) >= 70;

  // 3. Ed25519 Signature status
  const isSignatureVerified = Boolean(evidence_bundle.signature_valid);
  const isSignatureFailed = !isSignatureVerified && Boolean(evidence_bundle.digital_signature);

  // 4. Provenance Manifest status
  const isManifestVerified = Boolean(evidence_bundle.manifest_valid);
  const isManifestFailed = !isManifestVerified && Boolean(evidence_bundle.manifest_data);

  // 5. Hash Chain Ledger status
  const isChainVerified = Boolean(evidence_bundle.chain_integrity && evidence_bundle.chain_block_id);

  const renderStatusBadge = (status: "VERIFIED" | "FAILED" | "NOT_AVAILABLE" | "SUSPICIOUS" | "NOT_APPLICABLE") => {
    if (status === "VERIFIED") {
      return (
        <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-emerald-50 text-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-300 border border-emerald-300 dark:border-emerald-800 shadow-sm">
          <Check className="h-3 w-3 stroke-[3]" />
          <span>Verified</span>
        </span>
      );
    }
    if (status === "SUSPICIOUS") {
      return (
        <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-gold-50 text-gold-700 dark:bg-gold-950/50 dark:text-gold-300 border border-gold-300 dark:border-gold-800 shadow-sm">
          <AlertTriangle className="h-3 w-3" />
          <span>Suspicious</span>
        </span>
      );
    }
    if (status === "FAILED") {
      return (
        <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-crimson-50 text-crimson-700 dark:bg-crimson-950/50 dark:text-crimson-300 border border-crimson-300 dark:border-crimson-800 shadow-sm">
          <X className="h-3 w-3 stroke-[3]" />
          <span>Failed</span>
        </span>
      );
    }
    return (
      <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-semibold bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400 border border-slate-200 dark:border-slate-700">
        <MinusCircle className="h-3 w-3" />
        <span>{status === "NOT_APPLICABLE" ? "Not Applicable" : "Not Available"}</span>
      </span>
    );
  };

  return (
    <div className="space-y-4 sm:space-y-6 w-full">
      {/* Citizen-Friendly Main Verdict Banner */}
      <div
        className={`rounded-2xl p-4 sm:p-6 border shadow-sm transition-all ${
          isVerified
            ? "bg-emerald-50/80 border-emerald-200 dark:bg-emerald-950/20 dark:border-emerald-800"
            : isSuspicious
            ? "bg-gold-50/80 border-gold-200 dark:bg-gold-950/20 dark:border-gold-800"
            : isInvalid
            ? "bg-crimson-50/80 border-crimson-200 dark:bg-crimson-950/20 dark:border-crimson-800"
            : "bg-slate-50 border-slate-200 dark:bg-slate-800/40 dark:border-slate-700"
        }`}
      >
        <div className="flex flex-col xs:flex-row items-start gap-3 sm:gap-4">
          <div className="p-2 sm:p-2.5 rounded-2xl bg-white dark:bg-slate-900 shadow-sm border border-slate-200/60 dark:border-slate-800 flex-shrink-0">
            {getVerdictIcon()}
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 sm:gap-3 flex-wrap">
              <h3 className="text-base sm:text-lg font-bold text-slate-900 dark:text-white leading-tight">
                {getVerdictTitle()}
              </h3>
              <Badge variant={verdict}>{verdict}</Badge>
            </div>
            <p className="mt-1.5 text-xs sm:text-sm text-slate-600 dark:text-slate-300 leading-relaxed">
              {getVerdictDescription()}
            </p>

            <div className="mt-3 sm:mt-4 flex items-center justify-between flex-wrap gap-2 pt-2 border-t border-slate-200/40 dark:border-slate-700/40">
              <div className="flex items-center gap-2 text-[11px] sm:text-xs font-medium text-slate-500 dark:text-slate-400 flex-wrap">
                <span className="bg-white/70 dark:bg-slate-900/70 px-2 py-0.5 rounded-md border border-slate-200/60 dark:border-slate-700">
                  Confidence: {(confidence_score * 100).toFixed(1)}%
                </span>
                <span className="bg-white/70 dark:bg-slate-900/70 px-2 py-0.5 rounded-md border border-slate-200/60 dark:border-slate-700">
                  Latency: {verification_time_ms}ms
                </span>
              </div>

              {/* View Provenance Details Trigger */}
              <button
                onClick={() => setShowModal(true)}
                className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-xl bg-navy-800 hover:bg-navy-700 text-white text-xs font-bold transition-all shadow-sm min-h-[36px]"
              >
                <Eye className="h-3.5 w-3.5 text-emerald-400 flex-shrink-0" />
                <span>View Provenance Details</span>
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Simplified 4-Pillar Summary Cards for Quick Citizen Overview */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-3.5">
        <div className="p-3.5 rounded-2xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 shadow-sm space-y-1.5">
          <div className="flex items-center justify-between">
            <span className="text-slate-700 dark:text-slate-200 font-bold text-xs">SHA-256 Hash</span>
            {renderStatusBadge(isSha256Verified ? "VERIFIED" : "FAILED")}
          </div>
          <p className="text-[11px] text-slate-500 truncate">
            {isSha256Verified ? "Exact cryptographic match" : "No bit-level hash match"}
          </p>
        </div>

        <div className="p-3.5 rounded-2xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 shadow-sm space-y-1.5">
          <div className="flex items-center justify-between">
            <span className="text-slate-700 dark:text-slate-200 font-bold text-xs">Perceptual Match</span>
            {renderStatusBadge(isPerceptualNA ? "NOT_APPLICABLE" : isPerceptualVerified ? "VERIFIED" : isPerceptualSuspicious ? "SUSPICIOUS" : "FAILED")}
          </div>
          <p className="text-[11px] text-slate-500 truncate">
            {isPerceptualNA
              ? "Not applicable to text"
              : `${(evidence_bundle.similarity_score ?? 0).toFixed(0)}% visual similarity`}
          </p>
        </div>

        <div className="p-3.5 rounded-2xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 shadow-sm space-y-1.5">
          <div className="flex items-center justify-between">
            <span className="text-slate-700 dark:text-slate-200 font-bold text-xs">Ed25519 Signature</span>
            {renderStatusBadge(isSignatureVerified ? "VERIFIED" : isSignatureFailed ? "FAILED" : "NOT_AVAILABLE")}
          </div>
          <p className="text-[11px] text-slate-500 truncate">
            {evidence_bundle.publisher_name || "Unsigned media"}
          </p>
        </div>

        <div className="p-3.5 rounded-2xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 shadow-sm space-y-1.5">
          <div className="flex items-center justify-between">
            <span className="text-slate-700 dark:text-slate-200 font-bold text-xs">Ledger Anchor</span>
            {renderStatusBadge(isChainVerified ? "VERIFIED" : "NOT_AVAILABLE")}
          </div>
          <p className="text-[11px] text-slate-500 truncate">
            {isChainVerified ? `Block #${evidence_bundle.chain_block_id}` : "Not anchored"}
          </p>
        </div>
      </div>

      {/* COMPLETE PROVENANCE DETAILS MODAL (5 EVIDENCE MECHANISMS) */}
      {showModal && (
        <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-md flex items-center justify-center p-3 sm:p-4 md:p-6 animate-fadeIn">
          <div className="bg-white dark:bg-slate-900 rounded-2xl sm:rounded-3xl border border-slate-200 dark:border-slate-800 shadow-2xl w-full max-w-3xl max-h-[90vh] flex flex-col overflow-hidden">
            {/* Modal Header */}
            <div className="p-4 sm:p-6 border-b border-slate-100 dark:border-slate-800 flex items-center justify-between gap-3 flex-shrink-0 bg-slate-50/50 dark:bg-slate-900">
              <div className="flex items-center gap-3">
                <div className="h-9 w-9 sm:h-10 sm:w-10 rounded-xl bg-navy-800 text-white flex items-center justify-center shadow-sm flex-shrink-0">
                  <ShieldCheck className="h-5 w-5 text-emerald-400" />
                </div>
                <div>
                  <h3 className="text-sm sm:text-base font-bold text-slate-900 dark:text-white">
                    Official Provenance Verification Details
                  </h3>
                  <p className="text-[11px] text-slate-500 dark:text-slate-400">
                    Verification ID: <span className="font-mono">{data.verification_id}</span>
                  </p>
                </div>
              </div>

              <button
                onClick={() => setShowModal(false)}
                className="p-2 rounded-xl text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
                aria-label="Close Provenance Modal"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            {/* Modal Body: 5 Security Mechanisms */}
            <div className="p-4 sm:p-6 space-y-4 sm:space-y-5 overflow-y-auto flex-1 text-xs">
              {/* Evidence 1: SHA-256 Cryptographic Hash */}
              <div className="rounded-2xl border border-slate-200 dark:border-slate-800 p-4 space-y-3 bg-slate-50/50 dark:bg-slate-800/30">
                <div className="flex items-center justify-between flex-wrap gap-2">
                  <div className="flex items-center gap-2 font-bold text-slate-900 dark:text-white text-xs sm:text-sm">
                    <Fingerprint className="h-4 w-4 text-navy-700 dark:text-navy-300" />
                    <span>1. SHA-256 Cryptographic Hash</span>
                  </div>
                  {renderStatusBadge(isSha256Verified ? "VERIFIED" : "FAILED")}
                </div>
                <p className="text-slate-600 dark:text-slate-300 text-xs leading-relaxed">
                  Bit-level cryptographic fingerprint ensuring exact byte-for-byte authenticity against the registry.
                </p>

                <div className="space-y-2">
                  <div>
                    <span className="text-[10px] font-bold text-slate-400 uppercase">Submitted SHA-256 Hash</span>
                    <div className="flex items-center justify-between gap-2 p-2 rounded-lg bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 mt-0.5">
                      <span className="hash-font text-[11px] text-slate-800 dark:text-slate-200 break-all">
                        {evidence_bundle.sha256_submitted}
                      </span>
                      <button
                        onClick={() => copyToClipboard(evidence_bundle.sha256_submitted, "Submitted SHA-256 Hash")}
                        className="p-1 text-slate-400 hover:text-slate-600 flex-shrink-0"
                        title="Copy Hash"
                      >
                        <Copy className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  </div>

                  {evidence_bundle.matched_hash ? (
                    <div>
                      <span className="text-[10px] font-bold text-slate-400 uppercase">Registry Anchored Hash</span>
                      <div className="flex items-center justify-between gap-2 p-2 rounded-lg bg-emerald-50 dark:bg-emerald-950/40 border border-emerald-200 dark:border-emerald-800 mt-0.5">
                        <span className="hash-font text-[11px] text-emerald-700 dark:text-emerald-300 break-all font-semibold">
                          {evidence_bundle.matched_hash}
                        </span>
                        <button
                          onClick={() => copyToClipboard(evidence_bundle.matched_hash!, "Registry Hash")}
                          className="p-1 text-emerald-600 hover:text-emerald-800 flex-shrink-0"
                          title="Copy Registry Hash"
                        >
                          <Copy className="h-3.5 w-3.5" />
                        </button>
                      </div>
                    </div>
                  ) : (
                    <div className="p-2 rounded-lg bg-slate-100 dark:bg-slate-800 text-slate-500 text-[11px]">
                      No exact bit-level SHA-256 match found in active government publications.
                    </div>
                  )}
                </div>

                <button
                  onClick={() => toggleSection("sha256")}
                  className="inline-flex items-center gap-1 text-[11px] font-semibold text-navy-700 dark:text-navy-300 hover:underline pt-1"
                >
                  <span>Technical details</span>
                  {expandedSections["sha256"] ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
                </button>
                {expandedSections["sha256"] && (
                  <div className="p-3 rounded-xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 space-y-1 text-[11px]">
                    <p><strong className="text-slate-700 dark:text-slate-300">Standard:</strong> FIPS 180-4 SHA-256 (256-bit digest)</p>
                    <p><strong className="text-slate-700 dark:text-slate-300">Streaming Buffer:</strong> 64 KB memory-safe chunk digest</p>
                  </div>
                )}
              </div>

              {/* Evidence 2: Perceptual Fingerprint */}
              <div className="rounded-2xl border border-slate-200 dark:border-slate-800 p-4 space-y-3 bg-slate-50/50 dark:bg-slate-800/30">
                <div className="flex items-center justify-between flex-wrap gap-2">
                  <div className="flex items-center gap-2 font-bold text-slate-900 dark:text-white text-xs sm:text-sm">
                    <Lock className="h-4 w-4 text-navy-700 dark:text-navy-300" />
                    <span>2. Perceptual Fingerprint (pHash / Audio MFCC)</span>
                  </div>
                  {renderStatusBadge(
                    isPerceptualNA
                      ? "NOT_APPLICABLE"
                      : isPerceptualVerified
                      ? "VERIFIED"
                      : isPerceptualSuspicious
                      ? "SUSPICIOUS"
                      : "FAILED"
                  )}
                </div>
                <p className="text-slate-600 dark:text-slate-300 text-xs leading-relaxed">
                  Acoustic and visual structural fingerprinting tolerant of format conversion, compression, and resizing.
                </p>

                {isPerceptualNA ? (
                  <div className="p-3 rounded-lg bg-slate-100 dark:bg-slate-800 text-slate-500 text-[11px] leading-relaxed">
                    <strong>Not Applicable:</strong> Perceptual hashing algorithms (pHash/dHash/MFCC) are formulated for visual and acoustic waveforms (images, video, audio). Text statements and document byte streams are verified via cryptographic SHA-256 hashing.
                  </div>
                ) : (
                  <div className="space-y-2">
                    <div className="p-3 rounded-xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 space-y-2 text-[11px]">
                      <div className="flex justify-between items-center">
                        <span className="text-slate-500">Perceptual Similarity Score:</span>
                        <span className="font-bold text-slate-900 dark:text-white text-xs sm:text-sm">
                          {(evidence_bundle.similarity_score ?? 0).toFixed(1)}%
                        </span>
                      </div>
                      <div className="w-full bg-slate-100 dark:bg-slate-800 h-2 rounded-full overflow-hidden">
                        <div
                          className={`h-full rounded-full transition-all duration-500 ${
                            (evidence_bundle.similarity_score ?? 0) >= 95
                              ? "bg-emerald-500"
                              : (evidence_bundle.similarity_score ?? 0) >= 70
                              ? "bg-gold-500"
                              : "bg-slate-400"
                          }`}
                          style={{ width: `${evidence_bundle.similarity_score ?? 0}%` }}
                        />
                      </div>
                    </div>

                    {evidence_bundle.perceptual_hash_submitted && (
                      <div>
                        <span className="text-[10px] font-bold text-slate-400 uppercase">Calculated Perceptual Hashes</span>
                        <pre className="hash-font text-[10px] text-slate-800 dark:text-slate-200 bg-white dark:bg-slate-900 p-2 rounded-lg border border-slate-200 dark:border-slate-700 overflow-x-auto mt-0.5">
                          {JSON.stringify(evidence_bundle.perceptual_hash_submitted, null, 2)}
                        </pre>
                      </div>
                    )}
                  </div>
                )}

                <button
                  onClick={() => toggleSection("perceptual")}
                  className="inline-flex items-center gap-1 text-[11px] font-semibold text-navy-700 dark:text-navy-300 hover:underline pt-1"
                >
                  <span>Technical details</span>
                  {expandedSections["perceptual"] ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
                </button>
                {expandedSections["perceptual"] && (
                  <div className="p-3 rounded-xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 space-y-1 text-[11px]">
                    <p><strong className="text-slate-700 dark:text-slate-300">Image Methods:</strong> 64-bit DCT pHash + gradient dHash (weighted 60/40)</p>
                    <p><strong className="text-slate-700 dark:text-slate-300">Video Methods:</strong> 1.0 FPS multi-threaded frame extraction with composite hash</p>
                    <p><strong className="text-slate-700 dark:text-slate-300">Audio Methods:</strong> 12-chroma + 13-MFCC acoustic feature vector fingerprinting</p>
                  </div>
                )}
              </div>

              {/* Evidence 3: Ed25519 Digital Signature */}
              <div className="rounded-2xl border border-slate-200 dark:border-slate-800 p-4 space-y-3 bg-slate-50/50 dark:bg-slate-800/30">
                <div className="flex items-center justify-between flex-wrap gap-2">
                  <div className="flex items-center gap-2 font-bold text-slate-900 dark:text-white text-xs sm:text-sm">
                    <Building2 className="h-4 w-4 text-navy-700 dark:text-navy-300" />
                    <span>3. Digital Signature (Ed25519)</span>
                  </div>
                  {renderStatusBadge(isSignatureVerified ? "VERIFIED" : isSignatureFailed ? "FAILED" : "NOT_AVAILABLE")}
                </div>
                <p className="text-slate-600 dark:text-slate-300 text-xs leading-relaxed">
                  Asymmetric Edwards-curve digital signature guaranteeing publisher non-repudiation and origin authenticity.
                </p>

                {isSignatureVerified ? (
                  <div className="space-y-2">
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                      <div className="p-2.5 rounded-lg bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700">
                        <span className="text-[10px] font-bold text-slate-400 uppercase">Signing Publisher</span>
                        <p className="font-semibold text-slate-900 dark:text-white mt-0.5 truncate">
                          {evidence_bundle.publisher_name}
                        </p>
                      </div>
                      <div className="p-2.5 rounded-lg bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700">
                        <span className="text-[10px] font-bold text-slate-400 uppercase">Verified Domain</span>
                        <p className="font-semibold text-slate-900 dark:text-white font-mono mt-0.5 truncate">
                          {evidence_bundle.publisher_domain}
                        </p>
                      </div>
                    </div>

                    <div>
                      <span className="text-[10px] font-bold text-slate-400 uppercase">Base64 Signature</span>
                      <div className="flex items-center justify-between gap-2 p-2 rounded-lg bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 mt-0.5">
                        <span className="hash-font text-[11px] text-slate-800 dark:text-slate-200 break-all">
                          {evidence_bundle.digital_signature}
                        </span>
                        {evidence_bundle.digital_signature && (
                          <button
                            onClick={() => copyToClipboard(evidence_bundle.digital_signature!, "Digital Signature")}
                            className="p-1 text-slate-400 hover:text-slate-600 flex-shrink-0"
                            title="Copy Signature"
                          >
                            <Copy className="h-3.5 w-3.5" />
                          </button>
                        )}
                      </div>
                    </div>
                  </div>
                ) : (
                  <div className="p-3 rounded-lg bg-slate-100 dark:bg-slate-800 text-slate-500 text-[11px]">
                    {isSignatureFailed
                      ? "Digital signature verification failed against the publisher's public key."
                      : "Not available: This submission was not signed by an authorized publisher key."}
                  </div>
                )}

                <button
                  onClick={() => toggleSection("signature")}
                  className="inline-flex items-center gap-1 text-[11px] font-semibold text-navy-700 dark:text-navy-300 hover:underline pt-1"
                >
                  <span>Technical details & Public Key</span>
                  {expandedSections["signature"] ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
                </button>
                {expandedSections["signature"] && (
                  <div className="p-3 rounded-xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 space-y-2 text-[11px]">
                    <p><strong className="text-slate-700 dark:text-slate-300">Algorithm:</strong> {evidence_bundle.signing_algorithm || "Ed25519 (RFC 8032)"}</p>
                    {evidence_bundle.publisher_public_key && (
                      <div>
                        <strong className="text-slate-700 dark:text-slate-300 block mb-1">Publisher Public Key (PEM):</strong>
                        <pre className="hash-font text-[10px] text-slate-800 dark:text-slate-200 bg-slate-50 dark:bg-slate-800 p-2 rounded-lg whitespace-pre-wrap break-all max-h-[100px] overflow-y-auto">
                          {evidence_bundle.publisher_public_key}
                        </pre>
                      </div>
                    )}
                  </div>
                )}
              </div>

              {/* Evidence 4: Provenance Manifest */}
              <div className="rounded-2xl border border-slate-200 dark:border-slate-800 p-4 space-y-3 bg-slate-50/50 dark:bg-slate-800/30">
                <div className="flex items-center justify-between flex-wrap gap-2">
                  <div className="flex items-center gap-2 font-bold text-slate-900 dark:text-white text-xs sm:text-sm">
                    <FileCheck2 className="h-4 w-4 text-navy-700 dark:text-navy-300" />
                    <span>4. Provenance Manifest</span>
                  </div>
                  {renderStatusBadge(isManifestVerified ? "VERIFIED" : isManifestFailed ? "FAILED" : "NOT_AVAILABLE")}
                </div>
                <p className="text-slate-600 dark:text-slate-300 text-xs leading-relaxed">
                  Canonical metadata manifest recording timestamp, publisher ID, content type, and cryptographic assertions.
                </p>

                {isManifestVerified ? (
                  <div className="p-3 rounded-xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 space-y-1.5 text-[11px]">
                    <div className="flex justify-between">
                      <span className="text-slate-500">Manifest Version:</span>
                      <span className="font-semibold text-slate-900 dark:text-white">
                        {evidence_bundle.manifest_data?.manifest_version || "1.0"}
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-slate-500">Certified Timestamp:</span>
                      <span className="font-semibold text-slate-900 dark:text-white">
                        {evidence_bundle.manifest_data?.timestamp ? new Date(evidence_bundle.manifest_data.timestamp).toUTCString() : "Verified"}
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-slate-500">Content Type:</span>
                      <span className="font-semibold uppercase text-slate-900 dark:text-white">
                        {evidence_bundle.manifest_data?.content_type || "MEDIA"}
                      </span>
                    </div>
                  </div>
                ) : (
                  <div className="p-3 rounded-lg bg-slate-100 dark:bg-slate-800 text-slate-500 text-[11px]">
                    Not available: No official provenance manifest exists for this submission.
                  </div>
                )}

                <button
                  onClick={() => toggleSection("manifest")}
                  className="inline-flex items-center gap-1 text-[11px] font-semibold text-navy-700 dark:text-navy-300 hover:underline pt-1"
                >
                  <span>Technical details & Raw Manifest JSON</span>
                  {expandedSections["manifest"] ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
                </button>
                {expandedSections["manifest"] && (
                  <div className="p-3 rounded-xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 space-y-2 text-[11px]">
                    <strong className="text-slate-700 dark:text-slate-300 block">Canonical Manifest JSON:</strong>
                    <pre className="hash-font text-[10px] text-slate-800 dark:text-slate-200 bg-slate-50 dark:bg-slate-800 p-2 rounded-lg overflow-x-auto max-h-[140px]">
                      {evidence_bundle.manifest_data
                        ? JSON.stringify(evidence_bundle.manifest_data, null, 2)
                        : "No manifest payload"}
                    </pre>
                  </div>
                )}
              </div>

              {/* Evidence 5: Hash Chain Ledger Anchor */}
              <div className="rounded-2xl border border-slate-200 dark:border-slate-800 p-4 space-y-3 bg-slate-50/50 dark:bg-slate-800/30">
                <div className="flex items-center justify-between flex-wrap gap-2">
                  <div className="flex items-center gap-2 font-bold text-slate-900 dark:text-white text-xs sm:text-sm">
                    <Layers className="h-4 w-4 text-navy-700 dark:text-navy-300" />
                    <span>5. Hash Chain Ledger Anchor</span>
                  </div>
                  {renderStatusBadge(isChainVerified ? "VERIFIED" : "NOT_AVAILABLE")}
                </div>
                <p className="text-slate-600 dark:text-slate-300 text-xs leading-relaxed">
                  Immutable append-only cryptographic hash chain linking this publication to the genesis block.
                </p>

                {isChainVerified ? (
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-[11px]">
                    <div className="p-2.5 rounded-lg bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700">
                      <span className="text-slate-400 font-semibold text-[10px] uppercase">Chain Block Height</span>
                      <p className="font-mono font-bold text-slate-900 dark:text-white mt-0.5">
                        #{evidence_bundle.chain_block_id}
                      </p>
                    </div>
                    <div className="p-2.5 rounded-lg bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700">
                      <span className="text-slate-400 font-semibold text-[10px] uppercase">Ledger Integrity</span>
                      <p className="font-semibold text-emerald-600 dark:text-emerald-400 mt-0.5">
                        Tamper-Proof Block Verified
                      </p>
                    </div>
                  </div>
                ) : (
                  <div className="p-3 rounded-lg bg-slate-100 dark:bg-slate-800 text-slate-500 text-[11px]">
                    Not anchored: This submission has no block entry in the national hash chain.
                  </div>
                )}
              </div>
            </div>

            {/* Modal Footer */}
            <div className="p-4 sm:p-6 border-t border-slate-100 dark:border-slate-800 flex justify-end bg-slate-50/50 dark:bg-slate-900 flex-shrink-0">
              <button
                onClick={() => setShowModal(false)}
                className="w-full sm:w-auto px-5 py-2.5 rounded-xl bg-navy-800 text-white font-semibold text-xs hover:bg-navy-700 transition-colors min-h-[40px]"
              >
                Close Audit Details
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
