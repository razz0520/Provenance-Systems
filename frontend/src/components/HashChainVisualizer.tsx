"use client";

import React, { useEffect, useState } from "react";
import { api } from "@/services/api";
import { Layers, ShieldCheck, AlertOctagon, CheckCircle2, ArrowRight } from "lucide-react";

interface ChainState {
  is_valid: boolean;
  total_blocks: number;
  genesis_hash: string;
  latest_hash: string;
  broken_index?: number | null;
}

export function HashChainVisualizer() {
  const [chainState, setChainState] = useState<ChainState | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function fetchChain() {
      try {
        const res = await api.get("/registry/integrity");
        setChainState(res.data);
      } catch (e) {
        console.error("Failed to load hash chain state", e);
      } finally {
        setLoading(false);
      }
    }
    fetchChain();
  }, []);

  if (loading) {
    return (
      <div className="p-4 sm:p-6 rounded-2xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 animate-pulse w-full">
        <div className="h-4 bg-slate-200 dark:bg-slate-800 rounded w-1/3 sm:w-1/4 mb-4" />
        <div className="h-16 bg-slate-100 dark:bg-slate-800/50 rounded-xl" />
      </div>
    );
  }

  const isValid = chainState?.is_valid ?? true;

  return (
    <div className="p-4 sm:p-6 rounded-2xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 shadow-sm space-y-4 w-full">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2.5">
        <div className="flex items-center gap-2.5 min-w-0">
          <div className="h-8 w-8 rounded-lg bg-navy-50 dark:bg-slate-800 text-navy-800 dark:text-navy-300 flex items-center justify-center flex-shrink-0">
            <Layers className="h-4 w-4" />
          </div>
          <div className="min-w-0">
            <h3 className="text-xs sm:text-sm font-bold text-slate-900 dark:text-white uppercase tracking-wider">
              HASH-CHAIN LEDGER
            </h3>
            <p className="text-[11px] sm:text-xs text-slate-500 dark:text-slate-400">
              Ledger Height: <span className="font-semibold text-slate-700 dark:text-slate-200">{chainState?.total_blocks || 0} Entries</span>
            </p>
          </div>
        </div>

        <div
          className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] sm:text-xs font-semibold w-fit ${
            isValid
              ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-800"
              : "bg-crimson-50 text-crimson-700 dark:bg-crimson-950/40 dark:text-crimson-300 border border-crimson-200 dark:border-crimson-800"
          }`}
        >
          {isValid ? (
            <>
              <CheckCircle2 className="h-3.5 w-3.5 flex-shrink-0" />
              <span>Chain Integrity Verified</span>
            </>
          ) : (
            <>
              <AlertOctagon className="h-3.5 w-3.5 flex-shrink-0" />
              <span>Tampering Detected (Block #{chainState?.broken_index})</span>
            </>
          )}
        </div>
      </div>

      {/* Visual Chain Blocks */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 pt-1">
        {/* Genesis Anchor */}
        <div className="p-3 sm:p-3.5 rounded-xl bg-slate-50 dark:bg-slate-800/60 border border-slate-200 dark:border-slate-750">
          <div className="flex items-center justify-between text-[10px] sm:text-[11px] font-semibold text-slate-400 uppercase tracking-wider mb-1">
            <span>Genesis Anchor</span>
            <span className="text-emerald-600 dark:text-emerald-400">Root Constant</span>
          </div>
          <p className="hash-font text-[11px] sm:text-xs text-slate-700 dark:text-slate-300 truncate select-all">
            {chainState?.genesis_hash || "0000000000000000000000000000000000000000000000000000000000000000"}
          </p>
        </div>

        {/* Head Block */}
        <div className="p-3 sm:p-3.5 rounded-xl bg-slate-50 dark:bg-slate-800/60 border border-slate-200 dark:border-slate-750">
          <div className="flex items-center justify-between text-[10px] sm:text-[11px] font-semibold text-slate-400 uppercase tracking-wider mb-1">
            <span>Current Ledger Head</span>
            <span className="text-navy-700 dark:text-navy-300">Latest Signed</span>
          </div>
          <p className="hash-font text-[11px] sm:text-xs text-slate-700 dark:text-slate-300 truncate select-all">
            {chainState?.latest_hash || "0000000000000000000000000000000000000000000000000000000000000000"}
          </p>
        </div>
      </div>
    </div>
  );
}
