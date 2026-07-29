"use client";

import { useEffect } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { captureTokenFromUrl, getStoredToken } from "@/lib/api";

/** Captures ?token= from OAuth redirect into localStorage. */
export default function AuthTokenCapture() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  useEffect(() => {
    const hadToken = Boolean(searchParams.get("token"));
    captureTokenFromUrl();
    if (hadToken && getStoredToken() && pathname === "/") {
      router.replace("/q");
    }
  }, [pathname, router, searchParams]);

  return null;
}
