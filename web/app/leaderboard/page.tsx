"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import {
  getLeaderboard,
  type LeaderboardResponse,
} from "@/lib/api";
import { rankIconSrc, rankLabel } from "@/lib/ranks";

export default function LeaderboardPage() {
  const [track, setTrack] = useState<"rt" | "ct">("rt");
  const [role, setRole] = useState<"runner" | "bagger">("runner");
  const [board, setBoard] = useState<LeaderboardResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const t = params.get("track");
    const r = params.get("role");
    if (t === "rt" || t === "ct") setTrack(t);
    if (r === "runner" || r === "bagger") setRole(r);
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const boardRes = await getLeaderboard({ track, role, scope: "all", limit: 100 });
      setBoard(boardRes);
    } catch {
      setError("Couldn't load the leaderboard right now.");
      setBoard(null);
    } finally {
      setLoading(false);
    }
  }, [track, role]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <main className="mx-auto max-w-3xl px-4 py-8">
      <div className="mb-6">
        <h1 className="text-xl font-semibold text-fg">Leaderboard</h1>
        <p className="mt-1 text-sm text-muted">
          Everyone with revealed SR on each lane. Ruby+ elite rankings are on Discord via{" "}
          <span className="font-medium text-fg">/leaderboard</span>.
        </p>
      </div>

      <div className="flex flex-wrap gap-2">
        {(["rt", "ct"] as const).map((t) => (
          <button
            key={t}
            type="button"
            onClick={() => setTrack(t)}
            className={`rounded-lg border px-3 py-1.5 text-sm font-medium capitalize transition ${
              track === t
                ? "border-accent/50 bg-accent/15 text-accent"
                : "border-border bg-elevated text-muted hover:text-fg"
            }`}
          >
            {t === "rt" ? "Regular Tracks" : "Custom Tracks"}
          </button>
        ))}
      </div>

      <div className="mt-2 flex flex-wrap gap-2">
        {(["runner", "bagger"] as const).map((r) => (
          <button
            key={r}
            type="button"
            onClick={() => setRole(r)}
            className={`rounded-lg border px-3 py-1.5 text-sm font-medium capitalize transition ${
              role === r
                ? "border-accent/50 bg-accent/15 text-accent"
                : "border-border bg-elevated text-muted hover:text-fg"
            }`}
          >
            {r}
          </button>
        ))}
      </div>

      <section className="mt-6 rounded-2xl border border-border bg-panel shadow-panel">
        <header className="border-b border-border px-4 py-3">
          <p className="text-sm font-semibold text-fg">
            {board?.scope_label ?? "All placed players"}
            {board ? ` · ${board.track.toUpperCase()} ${board.role}` : ""}
          </p>
        </header>

        {loading ? (
          <p className="px-4 py-8 text-sm text-muted">Loading…</p>
        ) : error ? (
          <p className="px-4 py-8 text-sm text-danger">{error}</p>
        ) : !board?.entries.length ? (
          <p className="px-4 py-8 text-sm text-muted">No players on this board yet.</p>
        ) : (
          <ol className="divide-y divide-border">
            {board.entries.map((entry) => {
              const icon = rankIconSrc(entry.rank_tier);
              return (
                <li key={entry.discord_id} className="flex items-center gap-3 px-4 py-3">
                  <span className="w-8 shrink-0 text-sm font-semibold tabular-nums text-muted">
                    {entry.rank}
                  </span>
                  {icon ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img
                      src={icon}
                      alt={rankLabel(entry.rank_tier)}
                      className="h-8 w-8 shrink-0"
                    />
                  ) : (
                    <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-elevated text-xs text-muted">
                      ?
                    </span>
                  )}
                  <div className="min-w-0 flex-1">
                    <Link
                      href={entry.profile_path}
                      className="truncate text-sm font-medium text-fg hover:text-accent hover:underline"
                    >
                      {entry.display_name}
                    </Link>
                    <p className="text-xs text-muted">
                      {entry.sr} SR · {rankLabel(entry.rank_tier)}
                    </p>
                  </div>
                </li>
              );
            })}
          </ol>
        )}
      </section>
    </main>
  );
}
