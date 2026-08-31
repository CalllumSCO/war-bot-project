"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import PlayerRow from "@/components/PlayerRow";
import {
  ApiError,
  getDiscordLoginUrl,
  getInvitePreview,
  hasUsableSession,
  joinPartyByInviteCode,
  setReturnAfterLogin,
  type InvitePreview,
} from "@/lib/api";

export default function InviteLinkPage() {
  const router = useRouter();
  const params = useParams<{ code: string }>();
  const code = String(params.code ?? "").trim();

  const [preview, setPreview] = useState<InvitePreview | null>(null);
  const [loadError, setLoadError] = useState(false);
  const [loading, setLoading] = useState(true);
  const [joining, setJoining] = useState(false);
  const [joinError, setJoinError] = useState<string | null>(null);
  const [signedIn, setSignedIn] = useState(false);

  useEffect(() => {
    setSignedIn(hasUsableSession());
  }, []);

  useEffect(() => {
    if (!code) {
      setLoadError(true);
      setLoading(false);
      return;
    }

    let mounted = true;
    (async () => {
      try {
        const data = await getInvitePreview(code);
        if (!mounted) return;
        setPreview(data);
        setLoadError(false);
      } catch {
        if (!mounted) return;
        setPreview(null);
        setLoadError(true);
      } finally {
        if (mounted) setLoading(false);
      }
    })();

    return () => {
      mounted = false;
    };
  }, [code]);

  const handleSignIn = () => {
    setReturnAfterLogin(`/q/invite/${encodeURIComponent(code)}`);
    window.location.href = getDiscordLoginUrl();
  };

  const handleJoin = async () => {
    if (!code || joining) return;
    setJoinError(null);
    setJoining(true);
    try {
      await joinPartyByInviteCode(code);
      router.push("/q");
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.status === 401) {
          setReturnAfterLogin(`/q/invite/${encodeURIComponent(code)}`);
          router.push("/login");
          return;
        }
        if (err.status === 403 && /friend code/i.test(err.message)) {
          setJoinError("Link your Wii friend code on your profile before joining a group.");
          return;
        }
        setJoinError(err.message || "Couldn't join that group. Try again.");
        return;
      }
      setJoinError("Couldn't join that group. Try again.");
    } finally {
      setJoining(false);
    }
  };

  return (
    <main className="flex min-h-[calc(100vh-3.5rem)] items-center justify-center px-4">
      <div className="w-full max-w-sm rounded-2xl border border-border bg-panel p-6 shadow-panel">
        <h1 className="text-center text-lg font-semibold text-fg">Group invite</h1>

        {loading ? (
          <p className="mt-4 text-center text-sm text-muted">Loading invite…</p>
        ) : loadError || !preview ? (
          <p className="mt-4 text-center text-sm text-muted">
            This invite link is invalid or has expired.
          </p>
        ) : preview.expired ? (
          <p className="mt-4 text-center text-sm text-muted">
            This invite link has expired.
          </p>
        ) : (
          <>
            <p className="mt-2 text-center text-sm text-muted">
              You&apos;ve been invited to join:
            </p>
            <div className="mt-4 space-y-2">
              {preview.fromPlayers.map((player) => (
                <PlayerRow key={player.discordId} player={player} showSr />
              ))}
            </div>

            {joinError && (
              <p className="mt-4 text-center text-sm text-danger">
                {joinError}
                {/friend code/i.test(joinError) ? (
                  <>
                    {" "}
                    <Link href="/me" className="text-accent hover:underline">
                      Go to profile
                    </Link>
                  </>
                ) : null}
              </p>
            )}

            {signedIn ? (
              <button
                type="button"
                onClick={() => void handleJoin()}
                disabled={joining}
                className="mt-5 w-full rounded-lg bg-accent px-4 py-2.5 text-sm font-medium text-white transition hover:bg-accent-hover disabled:opacity-50"
              >
                {joining ? "Joining…" : "Join group"}
              </button>
            ) : (
              <button
                type="button"
                onClick={handleSignIn}
                className="mt-5 w-full rounded-lg bg-accent px-4 py-2.5 text-sm font-medium text-white transition hover:bg-accent-hover"
              >
                Sign in to join
              </button>
            )}
          </>
        )}
      </div>
    </main>
  );
}
