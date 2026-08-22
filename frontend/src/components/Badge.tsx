import React from "react";
import { cn } from "@/utils/cn";

export type BadgeVariant =
  | "VERIFIED"
  | "SUSPICIOUS"
  | "UNSIGNED"
  | "PROVEN_INVALID"
  | "ACTIVE"
  | "SUPERSEDED"
  | "REVOKED"
  | "SUSPENDED"
  | "ADMIN"
  | "PUBLISHER"
  | "VIEWER"
  | "PRIMARY"
  | "SECONDARY";

interface BadgeProps {
  variant: BadgeVariant | string;
  className?: string;
  children?: React.ReactNode;
}

export function Badge({ variant, className, children }: BadgeProps) {
  const v = variant.toUpperCase();

  let styles = "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300 border-slate-200 dark:border-slate-700";

  if (v === "VERIFIED" || v === "ACTIVE" || v === "PRIMARY") {
    styles = "bg-emerald-50 text-emerald-700 border-emerald-300 dark:bg-emerald-950/50 dark:text-emerald-300 dark:border-emerald-800";
  } else if (v === "SUSPICIOUS" || v === "SUPERSEDED" || v === "SECONDARY" || v === "PUBLISHER") {
    styles = "bg-gold-50 text-gold-700 border-gold-300 dark:bg-gold-950/50 dark:text-gold-300 dark:border-gold-800";
  } else if (v === "PROVEN_INVALID" || v === "REVOKED" || v === "SUSPENDED" || v === "ADMIN") {
    styles = "bg-crimson-50 text-crimson-700 border-crimson-300 dark:bg-crimson-950/50 dark:text-crimson-300 dark:border-crimson-800";
  } else if (v === "UNSIGNED" || v === "VIEWER") {
    styles = "bg-slate-100 text-slate-700 border-slate-300 dark:bg-slate-800 dark:text-slate-300 dark:border-slate-700";
  }

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold tracking-wide border shadow-sm",
        styles,
        className
      )}
    >
      <span className="w-1.5 h-1.5 rounded-full bg-current" />
      {children || variant}
    </span>
  );
}
