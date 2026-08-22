import React from "react";
import { cn } from "@/utils/cn";
import { LucideIcon } from "lucide-react";

interface StatsCardProps {
  title: string;
  value: string | number;
  description?: string;
  icon: LucideIcon;
  trend?: {
    value: string;
    isPositive: boolean;
  };
  className?: string;
}

export function StatsCard({
  title,
  value,
  description,
  icon: Icon,
  trend,
  className,
}: StatsCardProps) {
  return (
    <div
      className={cn(
        "relative overflow-hidden rounded-2xl bg-white dark:bg-slate-900 p-4 sm:p-6 border border-slate-200 dark:border-slate-800 shadow-sm hover:shadow-md transition-all duration-200 w-full",
        className
      )}
    >
      <div className="flex items-center justify-between gap-2">
        <div className="min-w-0">
          <p className="text-[11px] sm:text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400 truncate">
            {title}
          </p>
          <p className="mt-1 sm:mt-2 text-2xl sm:text-3xl font-bold tracking-tight text-slate-900 dark:text-white truncate">
            {value}
          </p>
        </div>
        <div className="flex h-10 w-10 sm:h-12 sm:w-12 flex-shrink-0 items-center justify-center rounded-xl bg-navy-50 text-navy-800 dark:bg-navy-900/50 dark:text-navy-300 border border-navy-100 dark:border-navy-800">
          <Icon className="h-5 w-5 sm:h-6 sm:w-6" />
        </div>
      </div>

      {(description || trend) && (
        <div className="mt-3 sm:mt-4 flex items-center gap-2 text-xs flex-wrap">
          {trend && (
            <span
              className={cn(
                "inline-flex items-center font-semibold",
                trend.isPositive
                  ? "text-emerald-600 dark:text-emerald-400"
                  : "text-crimson-600 dark:text-crimson-400"
              )}
            >
              {trend.isPositive ? "+" : ""}
              {trend.value}
            </span>
          )}
          {description && (
            <span className="text-slate-500 dark:text-slate-400 truncate">
              {description}
            </span>
          )}
        </div>
      )}
    </div>
  );
}
