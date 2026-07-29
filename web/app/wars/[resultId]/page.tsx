"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { ApiError, getWarResult, type WarDetail } from "@/lib/api";
import MatchResultDashboard from "@/components/MatchResultDashboard";

export default function WarResultPage() {
  const params = useParams<{ resultId: string }>();
  const router = useRouter();
  const resultId = params?.resultId;
  const [war, setWar] = useState<WarDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!resultId) return;
    let cancelled = false;
    (async () => {
      try {
        const detail = await getWarResult(resultId);
        if (!cancelled) {
          setWar(detail);
          setError(null);
        }
      } catch (err) {
        if (!cancelled) {
          if (err instanceof ApiError && err.status === 401) {
            router.push("/login");
            return;
          }
          setError(err instanceof ApiError && err.status === 404 ? "War not found." : "Couldn't load this war.");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [resultId, router]);

  return (
    <main className="mx-auto max-w-5xl px-4 py-8">
      <div className="mb-4">
        <Link href="/me" className="text-sm text-muted transition hover:text-accent">
          ← Back to profile
        </Link>
      </div>
      {loading && (
        <div className="animate-pulse space-y-4">
          <div className="mx-auto h-8 w-40 rounded bg-elevated" />
          <div className="h-64 rounded-2xl bg-elevated" />
        </div>
      )}
      {!loading && error && <p className="text-sm text-danger">{error}</p>}
      {!loading && war && <MatchResultDashboard war={war} />}
    </main>
  );
}
