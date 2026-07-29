"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ApiError, getCachedProfile, getMe, type MeProfile } from "@/lib/api";
import ProfileView from "@/components/ProfileView";

function ProfileSkeleton() {
  return (
    <div className="animate-pulse">
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-start gap-4">
          <div className="h-16 w-16 rounded-full bg-elevated" />
          <div className="space-y-2 pt-1">
            <div className="h-5 w-40 rounded bg-elevated" />
            <div className="h-4 w-24 rounded bg-elevated" />
          </div>
        </div>
        <div className="h-8 w-14 rounded-lg bg-elevated" />
      </div>
      <div className="mt-6 h-28 rounded-2xl border border-border bg-panel" />
    </div>
  );
}

export default function MePage() {
  const router = useRouter();
  const [profile, setProfile] = useState<MeProfile | null>(() =>
    typeof window !== "undefined" ? getCachedProfile() : null
  );
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(!profile);

  useEffect(() => {
    let mounted = true;
    // Don't paint a stale cached profile that predates SR backfill.
    const cached = getCachedProfile();
    const cachedHasRatings =
      cached?.ratings &&
      Object.values(cached.ratings).some(
        (roles) => roles && Object.values(roles).some((lane) => lane != null)
      );
    if (cached && cachedHasRatings) setProfile(cached);
    else setRefreshing(true);

    (async () => {
      try {
        const me = await getMe();
        if (!mounted) return;
        setProfile(me);
        setError(null);
      } catch (err) {
        if (!mounted) return;
        if (err instanceof ApiError && err.status === 401) {
          router.push("/login");
          return;
        }
        if (!cachedHasRatings) setError("Couldn't load your profile right now.");
      } finally {
        if (mounted) setRefreshing(false);
      }
    })();
    return () => {
      mounted = false;
    };
  }, [router]);

  if (!profile && refreshing) {
    return (
      <main className="mx-auto max-w-2xl px-4 py-8">
        <ProfileSkeleton />
      </main>
    );
  }

  if (!profile) {
    return (
      <main className="mx-auto max-w-2xl px-4 py-8">
        <p className="text-sm text-danger">{error ?? "Couldn't load your profile."}</p>
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-3xl px-4 py-8">
      <ProfileView
        profile={profile}
        headerAction={
          <Link
            href="/me/edit"
            className="shrink-0 rounded-lg border border-border bg-elevated px-3 py-1.5 text-sm font-medium text-fg transition hover:bg-panel"
          >
            Edit
          </Link>
        }
      />
    </main>
  );
}
