"use client";

import React, { useState, useRef, useEffect } from "react";
import { useRouter } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import { FileUploadZone } from "@/components/FileUploadZone";
import { api } from "@/services/api";
import { toast } from "sonner";
import {
  FilePlus2,
  KeyRound,
  ShieldCheck,
  CheckCircle2,
  Layers,
  Image as ImageIcon,
  Video,
  Music,
  FileText,
  Type,
  ChevronDown,
  Sparkles,
  ArrowRight,
  Fingerprint,
  AlignLeft,
  UploadCloud,
  X,
} from "lucide-react";

export type ContentTypeOption = "IMAGE" | "VIDEO" | "AUDIO" | "PDF" | "TEXT";

interface ContentTypeConfig {
  id: ContentTypeOption;
  label: string;
  category: string;
  description: string;
  icon: React.ElementType;
  acceptedTypes: string;
  badge: string;
}

const CONTENT_TYPES: ContentTypeConfig[] = [
  {
    id: "IMAGE",
    label: "Official Image / Infographic",
    category: "Visual Media",
    description: "Press photos, posters, circular banners, infographics",
    icon: ImageIcon,
    acceptedTypes: "image/png, image/jpeg, image/jpg, image/webp, image/gif",
    badge: "PNG, JPG, WEBP",
  },
  {
    id: "VIDEO",
    label: "Video Broadcast / Clip",
    category: "Video Media",
    description: "Official press briefings, minister speeches, video releases",
    icon: Video,
    acceptedTypes: "video/mp4, video/quicktime, video/x-msvideo, video/webm, video/mkv",
    badge: "MP4, MOV, WEBM",
  },
  {
    id: "AUDIO",
    label: "Audio Speech / Podcast",
    category: "Acoustic Media",
    description: "Radio addresses, voice statements, press audio recordings",
    icon: Music,
    acceptedTypes: "audio/mpeg, audio/wav, audio/ogg, audio/mp4, audio/x-m4a",
    badge: "MP3, WAV, M4A",
  },
  {
    id: "PDF",
    label: "Official Gazette / PDF Document",
    category: "Government Order",
    description: "Official gazette notifications, circulars, legal decrees",
    icon: FileText,
    acceptedTypes: "application/pdf",
    badge: "PDF",
  },
  {
    id: "TEXT",
    label: "Official Press Release / Text Statement",
    category: "Text Statement",
    description: "Direct press releases, executive statements, notifications",
    icon: Type,
    acceptedTypes: "text/plain, .txt, .md",
    badge: "DIRECT TEXT / TXT",
  },
];

export default function RegisterContentPage() {
  const router = useRouter();
  const [selectedType, setSelectedType] = useState<ContentTypeOption>("IMAGE");
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  // Text specific mode
  const [textInputMode, setTextInputMode] = useState<"direct" | "file">("direct");
  const [statementText, setStatementText] = useState("");

  // File state
  const [selectedFile, setSelectedFile] = useState<File | null>(null);

  // Metadata
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [department, setDepartment] = useState("");
  const [tags, setTags] = useState("");
  const [privateKey, setPrivateKey] = useState("");

  // Submission & Result
  const [submitting, setSubmitting] = useState(false);
  const [registeredResult, setRegisteredResult] = useState<any>(null);

  // Close dropdown on outside click
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setDropdownOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const currentConfig = CONTENT_TYPES.find((t) => t.id === selectedType) || CONTENT_TYPES[0];

  const handleSelectType = (type: ContentTypeOption) => {
    setSelectedType(type);
    setDropdownOpen(false);
    setSelectedFile(null);
    if (type !== "TEXT") {
      setStatementText("");
    }
  };

  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault();

    let fileToUpload: File | null = selectedFile;

    // If TEXT mode with direct statement input
    if (selectedType === "TEXT" && textInputMode === "direct") {
      if (!statementText.trim()) {
        toast.error("Please enter the official press release or statement text.");
        return;
      }

      // Convert raw text into a File object with .txt extension
      const safeTitle = (title.trim() || "statement").replace(/[^a-zA-Z0-9_-]/g, "_").toLowerCase();
      const textBlob = new Blob([statementText.trim()], { type: "text/plain;charset=utf-8" });
      fileToUpload = new File([textBlob], `${safeTitle}.txt`, { type: "text/plain" });
    } else {
      if (!fileToUpload) {
        toast.error(`Please select or upload the official ${currentConfig.category}.`);
        return;
      }
    }

    setSubmitting(true);

    try {
      const formData = new FormData();
      formData.append("file", fileToUpload);

      const metadataPayload = {
        title: title.trim() || fileToUpload.name,
        content_type: selectedType,
        description: description.trim() || null,
        department: department.trim() || null,
        tags: tags.split(",").map((t) => t.trim()).filter(Boolean),
        timestamp: new Date().toISOString(),
      };

      formData.append("metadata", JSON.stringify(metadataPayload));

      if (privateKey.trim()) {
        formData.append("private_key", privateKey.trim());
      }

      const res = await api.post("/content/register", formData, {
        headers: { "Content-Type": "multipart/form-data" },
      });

      setRegisteredResult(res.data);
      toast.success("Official content cryptographically registered and anchored!");
    } catch (err: any) {
      console.error(err);
      toast.error(err.response?.data?.message || "Content registration failed.");
    } finally {
      setSubmitting(false);
    }
  };

  const ActiveIcon = currentConfig.icon;

  return (
    <div className="max-w-4xl mx-auto space-y-6 sm:space-y-8 w-full">
      {/* Page Header */}
      <div>
        <div className="inline-flex items-center gap-1.5 sm:gap-2 px-3 py-1 rounded-full bg-navy-50 dark:bg-slate-800 text-navy-800 dark:text-navy-300 text-[11px] sm:text-xs font-semibold border border-navy-100 dark:border-slate-700 mb-2">
          <ShieldCheck className="h-3.5 w-3.5 text-emerald-500 flex-shrink-0" />
          <span>Official Provenance Anchor Console</span>
        </div>
        <h2 className="text-xl sm:text-2xl font-bold text-slate-900 dark:text-white tracking-tight">
          Register Official Content
        </h2>
        <p className="text-xs text-slate-500 dark:text-slate-400 mt-1 leading-relaxed">
          Select media category, upload assets or paste official statements, sign with Ed25519, and anchor to the national hash chain.
        </p>
      </div>

      {registeredResult ? (
        /* Success Receipt Card */
        <motion.div
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.3 }}
          className="rounded-2xl sm:rounded-3xl p-5 sm:p-8 bg-white dark:bg-slate-900 border border-emerald-200 dark:border-emerald-800 shadow-sm space-y-5 sm:space-y-6"
        >
          <div className="flex items-start sm:items-center gap-3">
            <div className="h-10 w-10 sm:h-12 sm:w-12 rounded-2xl bg-emerald-50 dark:bg-emerald-950/50 text-emerald-600 dark:text-emerald-400 flex items-center justify-center border border-emerald-200 dark:border-emerald-800 shadow-sm flex-shrink-0">
              <CheckCircle2 className="h-6 w-6 sm:h-7 sm:w-7" />
            </div>
            <div className="min-w-0">
              <h3 className="text-base sm:text-lg font-bold text-slate-900 dark:text-white truncate">
                Content Cryptographically Anchored
              </h3>
              <p className="text-[11px] sm:text-xs text-slate-500 dark:text-slate-400 truncate">
                Ledger Block #{registeredResult.hash_chain_block_id} • ID: {registeredResult.content_id?.substring(0, 16)}...
              </p>
            </div>
          </div>

          <div className="space-y-3 text-xs">
            <div className="p-3.5 sm:p-4 rounded-xl bg-slate-50 dark:bg-slate-800/60 border border-slate-200 dark:border-slate-700 space-y-1">
              <p className="font-semibold text-slate-400 uppercase tracking-wider text-[10px]">
                Cryptographic SHA-256 Hash
              </p>
              <p className="hash-font font-mono text-[11px] sm:text-xs text-slate-900 dark:text-slate-200 break-all">
                {registeredResult.sha256_hash}
              </p>
            </div>

            <div className="p-3.5 sm:p-4 rounded-xl bg-slate-50 dark:bg-slate-800/60 border border-slate-200 dark:border-slate-700 space-y-1">
              <p className="font-semibold text-slate-400 uppercase tracking-wider text-[10px]">
                Ed25519 Digital Manifest Signature
              </p>
              <p className="hash-font font-mono text-[11px] sm:text-xs text-slate-900 dark:text-slate-200 break-all">
                {registeredResult.manifest_signature}
              </p>
            </div>
          </div>

          <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-3 pt-2">
            <button
              onClick={() => {
                setRegisteredResult(null);
                setSelectedFile(null);
                setStatementText("");
                setTitle("");
                setDescription("");
              }}
              className="px-5 py-3 rounded-xl bg-navy-800 text-white text-xs font-semibold hover:bg-navy-700 transition-colors shadow-sm text-center min-h-[44px]"
            >
              Register Another Item
            </button>
            <button
              onClick={() => router.push("/dashboard/content")}
              className="px-5 py-3 rounded-xl border border-slate-200 dark:border-slate-700 text-xs font-semibold text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors text-center min-h-[44px]"
            >
              View My Publications
            </button>
          </div>
        </motion.div>
      ) : (
        /* Registration Form */
        <form onSubmit={handleRegister} className="space-y-6">
          <div className="p-4 sm:p-6 md:p-8 rounded-2xl sm:rounded-3xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 shadow-sm space-y-6">
            
            {/* STEP 1: Content Type Dropdown Selector */}
            <div className="space-y-3" ref={dropdownRef}>
              <div className="flex flex-col xs:flex-row xs:items-center justify-between gap-1">
                <label className="block text-xs font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400">
                  1. Select Content Type *
                </label>
                <span className="text-[11px] text-emerald-600 dark:text-emerald-400 font-semibold">
                  Required before upload
                </span>
              </div>

              {/* Animated Custom Dropdown Trigger */}
              <div className="relative">
                <button
                  type="button"
                  onClick={() => setDropdownOpen((prev) => !prev)}
                  className={`w-full flex items-center justify-between p-3 sm:p-4 rounded-2xl border transition-all duration-200 text-left min-h-[56px] ${
                    dropdownOpen
                      ? "border-navy-600 ring-2 ring-navy-500/20 bg-slate-50/80 dark:bg-slate-800/80 shadow-md"
                      : "border-slate-200 dark:border-slate-700 bg-slate-50/50 dark:bg-slate-800/50 hover:border-slate-300 dark:hover:border-slate-600 hover:bg-slate-100/50 dark:hover:bg-slate-800/80"
                  }`}
                >
                  <div className="flex items-center gap-2.5 sm:gap-3.5 min-w-0 pr-2">
                    <div className="h-9 w-9 sm:h-11 sm:w-11 rounded-xl bg-navy-800 text-emerald-400 flex items-center justify-center shadow-sm flex-shrink-0">
                      <ActiveIcon className="h-4 w-4 sm:h-5 sm:w-5" />
                    </div>
                    <div className="min-w-0">
                      <div className="flex items-center gap-1.5 sm:gap-2 flex-wrap">
                        <span className="text-xs sm:text-sm font-bold text-slate-900 dark:text-white truncate">
                          {currentConfig.label}
                        </span>
                        <span className="px-1.5 py-0.5 rounded-full text-[9px] sm:text-[10px] font-bold bg-navy-100 dark:bg-navy-950 text-navy-800 dark:text-navy-300 border border-navy-200 dark:border-navy-800">
                          {currentConfig.badge}
                        </span>
                      </div>
                      <p className="text-[11px] sm:text-xs text-slate-500 dark:text-slate-400 mt-0.5 truncate hidden xs:block">
                        {currentConfig.description}
                      </p>
                    </div>
                  </div>

                  <motion.div
                    animate={{ rotate: dropdownOpen ? 180 : 0 }}
                    transition={{ duration: 0.2 }}
                    className="p-1 rounded-lg text-slate-400 flex-shrink-0"
                  >
                    <ChevronDown className="h-5 w-5" />
                  </motion.div>
                </button>

                {/* Animated Dropdown Menu */}
                <AnimatePresence>
                  {dropdownOpen && (
                    <motion.div
                      initial={{ opacity: 0, y: -8, scale: 0.98 }}
                      animate={{ opacity: 1, y: 0, scale: 1 }}
                      exit={{ opacity: 0, y: -8, scale: 0.98 }}
                      transition={{ duration: 0.18, ease: "easeOut" }}
                      className="absolute left-0 right-0 top-full mt-2 z-40 rounded-2xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 shadow-2xl overflow-hidden p-1.5 sm:p-2 space-y-1 max-h-[70vh] overflow-y-auto"
                    >
                      {CONTENT_TYPES.map((type) => {
                        const Icon = type.icon;
                        const isSelected = type.id === selectedType;

                        return (
                          <button
                            key={type.id}
                            type="button"
                            onClick={() => handleSelectType(type.id)}
                            className={`w-full flex items-center justify-between p-2.5 sm:p-3 rounded-xl text-left transition-all min-h-[48px] ${
                              isSelected
                                ? "bg-navy-50 dark:bg-slate-800/90 text-navy-900 dark:text-white border border-navy-200/80 dark:border-slate-700"
                                : "hover:bg-slate-50 dark:hover:bg-slate-800/50 text-slate-700 dark:text-slate-300"
                            }`}
                          >
                            <div className="flex items-center gap-2.5 sm:gap-3 min-w-0 pr-2">
                              <div
                                className={`h-8 w-8 sm:h-9 sm:w-9 rounded-lg flex items-center justify-center flex-shrink-0 ${
                                  isSelected
                                    ? "bg-navy-800 text-emerald-400 shadow-sm"
                                    : "bg-slate-100 dark:bg-slate-800 text-slate-500 dark:text-slate-400"
                                }`}
                              >
                                <Icon className="h-4 w-4" />
                              </div>
                              <div className="min-w-0">
                                <div className="flex items-center gap-1.5 flex-wrap">
                                  <span className="text-xs font-bold truncate">{type.label}</span>
                                  <span className="text-[10px] font-semibold text-slate-400">
                                    • {type.badge}
                                  </span>
                                </div>
                                <p className="text-[10px] sm:text-[11px] text-slate-500 dark:text-slate-400 mt-0.5 truncate hidden xs:block">
                                  {type.description}
                                </p>
                              </div>
                            </div>

                            {isSelected && (
                              <CheckCircle2 className="h-4 w-4 text-emerald-500 flex-shrink-0" />
                            )}
                          </button>
                        );
                      })}
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>
            </div>

            {/* STEP 2: Tailored Upload or Text Statement Area */}
            <div className="border-t border-slate-100 dark:border-slate-800 pt-5 sm:pt-6 space-y-4">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                <label className="block text-xs font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400">
                  2. {selectedType === "TEXT" ? "Provide Official Statement" : `Upload ${currentConfig.label}`} *
                </label>

                {selectedType === "TEXT" && (
                  <div className="flex items-center gap-1 p-1 rounded-xl bg-slate-100 dark:bg-slate-800 text-xs border border-slate-200 dark:border-slate-700 w-fit">
                    <button
                      type="button"
                      onClick={() => setTextInputMode("direct")}
                      className={`px-2.5 sm:px-3 py-1 rounded-lg font-semibold transition-all min-h-[32px] ${
                        textInputMode === "direct"
                          ? "bg-white dark:bg-slate-900 text-navy-800 dark:text-white shadow-sm"
                          : "text-slate-500 hover:text-slate-900 dark:text-slate-400"
                      }`}
                    >
                      Type Statement
                    </button>
                    <button
                      type="button"
                      onClick={() => setTextInputMode("file")}
                      className={`px-2.5 sm:px-3 py-1 rounded-lg font-semibold transition-all min-h-[32px] ${
                        textInputMode === "file"
                          ? "bg-white dark:bg-slate-900 text-navy-800 dark:text-white shadow-sm"
                          : "text-slate-500 hover:text-slate-900 dark:text-slate-400"
                      }`}
                    >
                      Upload Text File
                    </button>
                  </div>
                )}
              </div>

              {/* Dynamic Content Body based on selected type */}
              <AnimatePresence mode="wait">
                {selectedType === "TEXT" && textInputMode === "direct" ? (
                  <motion.div
                    key="text-direct"
                    initial={{ opacity: 0, y: 6 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -6 }}
                    transition={{ duration: 0.2 }}
                    className="space-y-2"
                  >
                    <div className="relative">
                      <textarea
                        rows={6}
                        value={statementText}
                        onChange={(e) => setStatementText(e.target.value)}
                        placeholder="Paste or compose the full text of the official government press release, gazette announcement, or public notification here..."
                        className="w-full rounded-2xl p-3.5 sm:p-4 text-xs font-mono leading-relaxed bg-slate-50 dark:bg-slate-800/70 border border-slate-200 dark:border-slate-700 focus:outline-none focus:ring-2 focus:ring-navy-500 text-slate-900 dark:text-white shadow-inner"
                      />
                    </div>

                    <div className="flex flex-col sm:flex-row sm:items-center justify-between text-[11px] text-slate-400 px-1 font-medium gap-1">
                      <span>
                        Characters: {statementText.length} • Words:{" "}
                        {statementText.trim() ? statementText.trim().split(/\s+/).length : 0}
                      </span>
                      <span className="text-emerald-600 dark:text-emerald-400">
                        Packaged and anchored as UTF-8 statement
                      </span>
                    </div>
                  </motion.div>
                ) : (
                  <motion.div
                    key={`upload-${selectedType}-${textInputMode}`}
                    initial={{ opacity: 0, y: 6 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -6 }}
                    transition={{ duration: 0.2 }}
                  >
                    <FileUploadZone
                      onFileSelect={(f) => setSelectedFile(f)}
                      acceptedTypes={currentConfig.acceptedTypes}
                      contentTypeLabel={currentConfig.label}
                      selectedFile={selectedFile}
                    />
                  </motion.div>
                )}
              </AnimatePresence>
            </div>

            {/* STEP 3: Publication Metadata */}
            <div className="border-t border-slate-100 dark:border-slate-800 pt-5 sm:pt-6 space-y-4">
              <label className="block text-xs font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400">
                3. Publication Metadata
              </label>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 sm:gap-4">
                <div>
                  <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                    Publication Title *
                  </label>
                  <input
                    type="text"
                    required
                    value={title}
                    onChange={(e) => setTitle(e.target.value)}
                    placeholder="e.g. Official Gazette Circular on Digital Media 2026"
                    className="w-full rounded-xl px-3.5 py-2.5 text-xs bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 focus:outline-none focus:ring-2 focus:ring-navy-500 text-slate-900 dark:text-white"
                  />
                </div>

                <div>
                  <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                    Department / Division
                  </label>
                  <input
                    type="text"
                    value={department}
                    onChange={(e) => setDepartment(e.target.value)}
                    placeholder="e.g. Press Information Bureau / Ministry of I&B"
                    className="w-full rounded-xl px-3.5 py-2.5 text-xs bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 focus:outline-none focus:ring-2 focus:ring-navy-500 text-slate-900 dark:text-white"
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                  Description / Context
                </label>
                <textarea
                  rows={2}
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder="Official context and purpose of this publication..."
                  className="w-full rounded-xl p-3 text-xs bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 focus:outline-none focus:ring-2 focus:ring-navy-500 text-slate-900 dark:text-white"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                  Tags (Comma separated)
                </label>
                <input
                  type="text"
                  value={tags}
                  onChange={(e) => setTags(e.target.value)}
                  placeholder="press-release, gazette, announcement, national-security"
                  className="w-full rounded-xl px-3.5 py-2.5 text-xs bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 focus:outline-none focus:ring-2 focus:ring-navy-500 text-slate-900 dark:text-white"
                />
              </div>
            </div>

            {/* STEP 4: Signing Key Option */}
            <div className="border-t border-slate-100 dark:border-slate-800 pt-5 sm:pt-6 space-y-3">
              <label className="block text-xs font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400">
                4. Cryptographic Manifest Signature
              </label>
              <div className="p-3 sm:p-3.5 rounded-xl bg-slate-50 dark:bg-slate-800/60 border border-slate-200 dark:border-slate-700 text-xs text-slate-600 dark:text-slate-300 flex items-start gap-2.5">
                <ShieldCheck className="h-4 w-4 text-emerald-500 flex-shrink-0 mt-0.5" />
                <p className="leading-relaxed">
                  Your official <strong>Ed25519 digital keypair</strong> will automatically sign this canonical manifest and append a block to the immutable ledger.
                </p>
              </div>

              <input
                type="password"
                value={privateKey}
                onChange={(e) => setPrivateKey(e.target.value)}
                placeholder="Optional external Ed25519 Private Key PEM (leave empty to use registered system key)"
                className="w-full rounded-xl px-3.5 py-2.5 text-xs font-mono bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 focus:outline-none focus:ring-2 focus:ring-navy-500 text-slate-900 dark:text-white"
              />
            </div>
          </div>

          {/* Submit Action Button */}
          <button
            type="submit"
            disabled={submitting}
            className="w-full py-3.5 sm:py-4 rounded-2xl bg-navy-800 hover:bg-navy-700 text-white font-bold text-xs sm:text-sm transition-all shadow-md hover:shadow-lg flex items-center justify-center gap-2.5 disabled:opacity-50 min-h-[48px]"
          >
            {submitting ? (
              <>
                <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                Computing Hashes, Signing Manifest & Anchoring Ledger...
              </>
            ) : (
              <>
                <FilePlus2 className="h-4 w-4 text-emerald-400 flex-shrink-0" />
                Sign & Register {currentConfig.category} in Ledger
              </>
            )}
          </button>
        </form>
      )}
    </div>
  );
}
