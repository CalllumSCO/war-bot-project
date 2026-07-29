"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { captureTokenFromUrl, getMe, getStoredToken } from "@/lib/api";

/** OAuth landing page — persist JWT from ?token=, then go to the queue. */
export default function AuthCallbackPage() {
  const router = useRouter();

  useEffect(() => {
    let cancelled = false;
    (async () => {
      captureTokenFromUrl();
      if (!getStoredToken()) {
        router.replace("/login");
        return;
      }
      try {
        await getMe();
      } catch {
        /* queue can still load; avatar cache is best-effort */
      }
      if (!cancelled) router.replace("/q");
    })();
    return () => {
      cancelled = true;
    };
  }, [router]);

  return (
    <main className="flex min-h-[calc(100vh-3.5rem)] items-center justify-center px-4">
      <p className="text-sm text-muted">Signing you in…</p>
    </main>
  );
}
