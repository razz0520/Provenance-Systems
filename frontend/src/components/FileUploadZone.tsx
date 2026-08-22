"use client";

import React, { useState, useRef, useEffect } from "react";
import { cn } from "@/utils/cn";
import {
  UploadCloud,
  File,
  Image as ImageIcon,
  Video,
  Music,
  FileText,
  X,
  CheckCircle2,
} from "lucide-react";

interface FileUploadZoneProps {
  onFileSelect: (file: File | null) => void;
  acceptedTypes?: string;
  maxSizeMB?: number;
  className?: string;
  contentTypeLabel?: string;
  selectedFile?: File | null;
}

export function FileUploadZone({
  onFileSelect,
  acceptedTypes = "image/*,video/*,audio/*,.pdf,.txt",
  maxSizeMB = 50,
  className,
  contentTypeLabel = "Media Asset",
  selectedFile: externalSelectedFile,
}: FileUploadZoneProps) {
  const [dragActive, setDragActive] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(externalSelectedFile || null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (externalSelectedFile !== undefined) {
      setSelectedFile(externalSelectedFile);
      if (externalSelectedFile && externalSelectedFile.type.startsWith("image/")) {
        const url = URL.createObjectURL(externalSelectedFile);
        setPreviewUrl(url);
      } else {
        setPreviewUrl(null);
      }
    }
  }, [externalSelectedFile]);

  const handleFiles = (files: FileList | null) => {
    if (!files || files.length === 0) return;
    const file = files[0];

    if (file.size > maxSizeMB * 1024 * 1024) {
      alert(`File size exceeds maximum allowed limit of ${maxSizeMB}MB`);
      return;
    }

    setSelectedFile(file);
    onFileSelect(file);

    if (file.type.startsWith("image/")) {
      const url = URL.createObjectURL(file);
      setPreviewUrl(url);
    } else {
      setPreviewUrl(null);
    }
  };

  const removeFile = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    setSelectedFile(null);
    setPreviewUrl(null);
    onFileSelect(null);
    if (inputRef.current) inputRef.current.value = "";
  };

  const getFileIcon = () => {
    if (!selectedFile) return UploadCloud;
    if (selectedFile.type.startsWith("image/")) return ImageIcon;
    if (selectedFile.type.startsWith("video/")) return Video;
    if (selectedFile.type.startsWith("audio/")) return Music;
    if (selectedFile.type.includes("pdf")) return FileText;
    return File;
  };

  const Icon = getFileIcon();

  return (
    <div className={cn("w-full", className)}>
      <div
        onDragEnter={(e) => {
          e.preventDefault();
          setDragActive(true);
        }}
        onDragLeave={(e) => {
          e.preventDefault();
          setDragActive(false);
        }}
        onDragOver={(e) => e.preventDefault()}
        onDrop={(e) => {
          e.preventDefault();
          setDragActive(false);
          handleFiles(e.dataTransfer.files);
        }}
        onClick={() => inputRef.current?.click()}
        className={cn(
          "relative border-2 border-dashed rounded-2xl p-4 sm:p-6 md:p-8 flex flex-col items-center justify-center text-center cursor-pointer transition-all duration-200 min-h-[160px] sm:min-h-[190px]",
          dragActive
            ? "border-emerald-500 bg-emerald-50/50 dark:bg-emerald-950/20 scale-[0.99]"
            : "border-slate-300 dark:border-slate-700 bg-slate-50/50 dark:bg-slate-900/50 hover:border-navy-500 hover:bg-slate-100/50 dark:hover:bg-slate-800/50 active:scale-[0.99]"
        )}
      >
        <input
          ref={inputRef}
          type="file"
          accept={acceptedTypes}
          onChange={(e) => handleFiles(e.target.files)}
          className="hidden"
        />

        {selectedFile ? (
          <div className="flex flex-col items-center gap-3 sm:gap-4 w-full">
            {previewUrl ? (
              <div className="relative w-28 h-28 sm:w-36 sm:h-36 rounded-xl overflow-hidden border border-slate-200 dark:border-slate-700 shadow-sm bg-black/5 flex-shrink-0">
                <img
                  src={previewUrl}
                  alt="Preview"
                  className="w-full h-full object-cover"
                />
              </div>
            ) : (
              <div className="h-12 w-12 sm:h-16 sm:w-16 rounded-2xl bg-navy-800 text-emerald-400 flex items-center justify-center shadow-md flex-shrink-0">
                <Icon className="h-6 w-6 sm:h-8 sm:w-8" />
              </div>
            )}

            <div className="text-center max-w-xs sm:max-w-sm px-2">
              <p className="text-xs sm:text-sm font-semibold text-slate-900 dark:text-white truncate">
                {selectedFile.name}
              </p>
              <p className="text-[11px] sm:text-xs text-slate-500 dark:text-slate-400 mt-0.5">
                {(selectedFile.size / (1024 * 1024)).toFixed(2)} MB • {selectedFile.type || "binary"}
              </p>
            </div>

            <button
              type="button"
              onClick={removeFile}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-semibold bg-crimson-50 text-crimson-700 dark:bg-crimson-950/50 dark:text-crimson-300 border border-crimson-200 dark:border-crimson-800 hover:bg-crimson-100 transition-colors min-h-[36px]"
            >
              <X className="h-3.5 w-3.5" />
              Remove & Choose Another
            </button>
          </div>
        ) : (
          <div className="flex flex-col items-center gap-2.5 sm:gap-3 px-2">
            <div className="h-12 w-12 sm:h-14 sm:w-14 rounded-2xl bg-navy-50 dark:bg-slate-800 text-navy-800 dark:text-navy-300 flex items-center justify-center border border-navy-100 dark:border-slate-700 flex-shrink-0">
              <UploadCloud className="h-6 w-6 sm:h-7 sm:w-7" />
            </div>
            <div>
              <p className="text-xs sm:text-sm font-semibold text-slate-900 dark:text-white">
                Tap to upload or drag & drop official {contentTypeLabel}
              </p>
              <p className="text-[11px] sm:text-xs text-slate-500 dark:text-slate-400 mt-1 max-w-xs sm:max-w-md mx-auto leading-relaxed">
                Accepted: {acceptedTypes} (Max {maxSizeMB}MB)
              </p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
