"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import {
  getCachedProfile,
  getCachedMe,
  getMeCached,
  profileAvatarUrl,
  profileDisplayName,
  type Role,
} from "@/lib/api";
import { rankIconSrc } from "@/lib/ranks";

export type StartEntry = "queue" | "friends" | "preview";

export type StartChoices = {
  warType: "RT" | "CT";
  role: Role;
  mode: "ranked" | "casual";
  entry: StartEntry;
};

export default function QueueStartScreen({
  busy,
  error,
  onStart,
}: {
  busy: boolean;
  error?: string | null;
  onStart: (choices: StartChoices) => void;
}) {
  const [warType, setWarType] = useState<"RT" | "CT">("RT");
  const [role, setRole] = useState<Role>("runner");
  const [mode, setMode] = useState<"ranked" | "casual">("ranked");
  const [isSupporter, setIsSupporter] = useState(() =>
    typeof window !== "undefined" ? Boolean(getCachedProfile()?.supporter) : false
  );
  const me = typeof window !== "undefined" ? getCachedMe() : null;
  const name = me ? profileDisplayName(me) : "You";
  const avatar = me ? profileAvatarUrl(me) : null;

  useEffect(() => {
    let cancelled = false;
    getMeCached()
      .then((profile) => {
        if (!cancelled) setIsSupporter(Boolean(profile.supporter));
      })
      .catch(() => {
        /* keep cached */
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const start = (entry: StartEntry) => onStart({ warType, role, mode, entry });

  return (
    <main className="mx-auto flex min-h-[calc(100vh-3.5rem)] max-w-md flex-col items-center justify-center px-4 py-10">
      <div className="mb-8 flex w-full items-center gap-3 rounded-xl border border-border bg-panel px-4 py-3 shadow-panel">
        {avatar ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={avatar} alt="" className="h-10 w-10 rounded-full object-cover" />
        ) : (
          <div className="flex h-10 w-10 items-center justify-center rounded-full bg-elevated text-sm text-muted">
            {name.slice(0, 1).toUpperCase()}
          </div>
        )}
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium text-fg">{name}</p>
          <p className="text-xs capitalize text-muted">{role}</p>
        </div>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={rankIconSrc("unranked")!} alt="Unranked" className="h-8 w-8" />
      </div>

      <div className="w-full space-y-5">
        <section>
          <p className="mb-2 text-xs font-medium uppercase tracking-wide text-muted">Track</p>
          <div className="grid grid-cols-2 gap-2">
            {(
              [
                ["RT", "Regular Tracks"],
                ["CT", "Custom Tracks"],
              ] as const
            ).map(([key, label]) => (
              <button
                key={key}
                type="button"
                onClick={() => setWarType(key)}
                className={`rounded-xl border px-3 py-3 text-left transition ${
                  warType === key
                    ? "border-accent bg-accent/15 text-fg"
                    : "border-border bg-elevated text-muted hover:text-fg"
                }`}
              >
                <span className="block text-sm font-semibold">{key}</span>
                <span className="text-xs opacity-80">{label}</span>
              </button>
            ))}
          </div>
        </section>

        <section>
          <p className="mb-2 text-xs font-medium uppercase tracking-wide text-muted">Your role</p>
          <div className="grid grid-cols-2 gap-2">
            {(
              [
                ["runner", "Runner"],
                ["bagger", "Bagger"],
              ] as const
            ).map(([key, label]) => (
              <button
                key={key}
                type="button"
                onClick={() => setRole(key)}
                className={`rounded-xl border px-3 py-3 text-sm font-medium transition ${
                  role === key
                    ? "border-accent bg-accent/15 text-fg"
                    : "border-border bg-elevated text-muted hover:text-fg"
                }`}
              >
                {label}
              </button>
            ))}
          </div>
        </section>

        <section>
          <p className="mb-2 text-xs font-medium uppercase tracking-wide text-muted">Mode</p>
          <div className="grid grid-cols-2 gap-2">
            {(
              [
                ["ranked", "Ranked"],
                ["casual", "Casual"],
              ] as const
            ).map(([key, label]) => (
              <button
                key={key}
                type="button"
                onClick={() => setMode(key)}
                className={`rounded-xl border px-3 py-3 text-sm font-medium transition ${
                  mode === key
                    ? "border-accent bg-accent/15 text-fg"
                    : "border-border bg-elevated text-muted hover:text-fg"
                }`}
              >
                {label}
              </button>
            ))}
          </div>
        </section>

        {error && (
          <div className="rounded-lg border border-danger/30 bg-danger/10 px-3 py-2 text-center text-sm text-danger">
            <p>{error}</p>
            {/friend code/i.test(error) ? (
              <Link
                href="/me/edit"
                className="mt-1 inline-block font-medium underline underline-offset-2"
              >
                Edit profile to link FC
              </Link>
            ) : null}
          </div>
        )}

        <div className="space-y-2.5">
          <button
            type="button"
            disabled={busy}
            onClick={() => start("queue")}
            className="w-full rounded-xl bg-accent px-4 py-3 text-sm font-semibold text-white transition hover:bg-accent-hover disabled:opacity-50"
          >
            {busy ? "Starting…" : "Join queue"}
          </button>

          <button
            type="button"
            disabled={busy}
            onClick={() => start("friends")}
            className="w-full rounded-xl border border-accent bg-transparent px-4 py-3 text-sm font-semibold text-accent transition hover:bg-accent/10 disabled:opacity-50"
          >
            Join with friends
          </button>

          {isSupporter ? (
            <button
              type="button"
              disabled={busy}
              onClick={() => start("preview")}
              className="w-full px-2 py-1.5 text-center text-sm text-muted underline-offset-2 transition hover:text-accent hover:underline disabled:opacity-50"
            >
              Preview the queue
            </button>
          ) : null}
        </div>

        <p className="text-center text-xs text-muted">
          Join queue puts you live immediately. Join with friends builds your group first —
          you won&apos;t see who&apos;s Available until you press Join queue.
        </p>

        <Link
          href="/q/info"
          className="flex w-full items-start gap-3 rounded-xl border border-border bg-panel px-4 py-3 text-left transition hover:border-accent hover:bg-accent/10"
        >
          <span className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-elevated text-sm font-semibold text-accent">
            ?
          </span>
          <span className="min-w-0">
            <span className="block text-sm font-semibold text-fg">Guide</span>
            <span className="mt-0.5 block text-xs text-muted">
              How to queue, plus how ranked SR, tiers, and team rank work
            </span>
          </span>
        </Link>
      </div>
    </main>
  );
}
