"use client";

import { useEffect } from "react";
import posthog from "posthog-js";

// PostHog analytics, guarded on the public key so the app runs fine before the
// key is pasted into Vercel. us cloud per the org observability standard.
export function PostHogProvider({ children }: { children: React.ReactNode }) {
  useEffect(() => {
    const key = process.env.NEXT_PUBLIC_POSTHOG_KEY;
    if (!key) return;
    posthog.init(key, {
      api_host: process.env.NEXT_PUBLIC_POSTHOG_HOST ?? "https://us.i.posthog.com",
      capture_pageview: true,
      capture_pageleave: true,
    });
  }, []);

  return <>{children}</>;
}
