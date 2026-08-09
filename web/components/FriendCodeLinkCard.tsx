"use client";

import { useState } from "react";
import { ApiError, linkFriendCode, type MeProfile } from "@/lib/api";

type Props = {
  profile: MeProfile;
  onLinked: (profile: MeProfile) => void;
};

export default function FriendCodeLinkCard({ profile, onLinked }: Props) {
  const [fc, setFc] = useState(profile.friend_code ?? "");
  const [busy, setBusy] = useState<"auto" | "manual" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [hint, setHint] = useState<string | null>(null);

  const linked = Boolean(profile.has_linked_fc || profile.friend_code?.trim());

  const run = async (mode: "auto" | "manual") => {
    setBusy(mode);
    setError(null);
    setHint(null);
    try {
      const updated = await linkFriendCode(mode === "manual" ? fc : null);
      const nowLinked = Boolean(updated.has_linked_fc || updated.friend_code?.trim());
      if (mode === "auto" && !nowLinked) {
        // Auto-link is optional — soft miss, keep going with manual entry.
        setHint(
          updated.auto_link_hint?.trim() ||
            "Couldn't auto-link from Lounge. Enter your WiimmFI friend code below."
        );
        onLinked(updated);
        return;
      }
      onLinked(updated);
    } catch (err) {
      if (mode === "auto") {
        // Network / unexpected auto failure: still don't block manual linking.
        setHint("Couldn't auto-link from Lounge. Enter your WiimmFI friend code below.");
      } else if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError("Couldn't link friend code. Try again.");
      }
    } finally {
      setBusy(null);
    }
  };

  if (linked) {
    return (
      <section className="rounded-2xl border border-border bg-panel p-5 shadow-panel">
        <h2 className="text-sm font-semibold text-fg">Friend code</h2>
        <p className="mt-2 font-mono text-sm text-fg">{profile.friend_code}</p>
        <p className="mt-1 text-xs text-muted">Required for queueing. You can update it below.</p>
        <div className="mt-3 flex flex-col gap-2 sm:flex-row">
          <input
            value={fc}
            onChange={(e) => setFc(e.target.value)}
            placeholder="XXXX-XXXX-XXXX"
            maxLength={14}
            className="w-full rounded-lg border border-border bg-elevated px-3 py-2 font-mono text-sm text-fg placeholder:text-muted focus:border-accent focus:outline-none"
          />
          <button
            type="button"
            disabled={busy !== null}
            onClick={() => run("manual")}
            className="shrink-0 rounded-lg border border-border bg-elevated px-4 py-2 text-sm font-medium text-fg transition hover:bg-panel disabled:opacity-50"
          >
            {busy === "manual" ? "Saving…" : "Update"}
          </button>
        </div>
        {error && <p className="mt-2 text-sm text-danger">{error}</p>}
      </section>
    );
  }

  return (
    <section className="rounded-2xl border border-accent/40 bg-accent/5 p-5 shadow-panel">
      <h2 className="text-sm font-semibold text-fg">Link your Wii friend code</h2>
      <p className="mt-1 text-sm text-muted">
        Required before joining the queue. Auto-link from Lounge if Discord is connected there, or
        enter your WiimmFI FC.
      </p>
      <div className="mt-4 flex flex-col gap-2 sm:flex-row">
        <button
          type="button"
          disabled={busy !== null}
          onClick={() => run("auto")}
          className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white transition hover:bg-accent-hover disabled:opacity-50"
        >
          {busy === "auto" ? "Looking up…" : "Auto-link from Lounge"}
        </button>
      </div>
      <div className="mt-4 flex flex-col gap-2 sm:flex-row">
        <input
          value={fc}
          onChange={(e) => setFc(e.target.value)}
          placeholder="XXXX-XXXX-XXXX"
          maxLength={14}
          className="w-full rounded-lg border border-border bg-elevated px-3 py-2 font-mono text-sm text-fg placeholder:text-muted focus:border-accent focus:outline-none"
        />
        <button
          type="button"
          disabled={busy !== null || !fc.trim()}
          onClick={() => run("manual")}
          className="shrink-0 rounded-lg border border-border bg-elevated px-4 py-2 text-sm font-medium text-fg transition hover:bg-panel disabled:opacity-50"
        >
          {busy === "manual" ? "Saving…" : "Save FC"}
        </button>
      </div>
      {hint && <p className="mt-2 text-sm text-muted">{hint}</p>}
      {error && <p className="mt-2 text-sm text-danger">{error}</p>}
    </section>
  );
}
