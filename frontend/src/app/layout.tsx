"use client";

import "./globals.css";
import React, { useEffect } from "react";
import { useAuthStore } from "@/services/authStore";
import { Toaster } from "sonner";
import { ErrorBoundary } from "@/components/ErrorBoundary";

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const { initAuth } = useAuthStore();

  useEffect(() => {
    initAuth();
  }, [initAuth]);

  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <title>National Content Provenance & Verification Platform</title>
        <meta
          name="description"
          content="Deepfake-Resistant Government Content Provenance System with WhatsApp verification & immutable hash chain ledger."
        />
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link
          href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600;700&display=swap"
          rel="stylesheet"
        />
      </head>
      <body className="bg-slate-50 dark:bg-slate-950 text-slate-900 dark:text-slate-50 font-sans antialiased min-h-screen">
        <div className="gov-ribbon w-full sticky top-0 z-50" />
        <ErrorBoundary>{children}</ErrorBoundary>
        <Toaster richColors position="top-right" />
      </body>
    </html>
  );
}
