"use client";

import React, { Component, ErrorInfo, ReactNode } from "react";
import { AlertTriangle, RefreshCw } from "lucide-react";

interface Props {
  children?: ReactNode;
}

interface State {
  hasError: boolean;
  error?: Error;
}

export class ErrorBoundary extends Component<Props, State> {
  public state: State = {
    hasError: false,
  };

  public static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error("Uncaught error in component tree:", error, errorInfo);
  }

  public render() {
    if (this.state.hasError) {
      return (
        <div className="p-8 rounded-2xl bg-white dark:bg-slate-900 border border-crimson-200 dark:border-crimson-800 text-center space-y-4 max-w-lg mx-auto my-12 shadow-sm">
          <div className="h-12 w-12 rounded-xl bg-crimson-50 text-crimson-600 dark:bg-crimson-950/50 dark:text-crimson-300 mx-auto flex items-center justify-center">
            <AlertTriangle className="h-6 w-6" />
          </div>
          <h2 className="text-lg font-bold text-slate-900 dark:text-white">
            An Unexpected Interface Error Occurred
          </h2>
          <p className="text-xs text-slate-500 dark:text-slate-400">
            {this.state.error?.message || "Please refresh the page to restore the application state."}
          </p>
          <button
            onClick={() => window.location.reload()}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-navy-800 text-white text-xs font-semibold hover:bg-navy-700 transition-colors shadow-sm"
          >
            <RefreshCw className="h-3.5 w-3.5" />
            Reload Page
          </button>
        </div>
      );
    }

    return this.props.children;
  }
}
