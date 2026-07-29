"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import {
  getCachedMe,
  getMe,
  hasUsableSession,
  profileAvatarUrl,
  profileDisplayName,
  type CachedMe,
} from "@/lib/api";

export default function NavBar() {
  const pathname = usePathname();
  const [me, setMe] = useState<CachedMe | null>(null);

  useEffect(() => {
    setMe(getCachedMe());
    if (!hasUsableSession()) {
      setMe(null);
      return;
    }
    let mounted = true;
    getMe()
      .then((profile) => {
        if (!mounted) return;
        setMe({
          discord_id: profile.discord_id,
          display_name: profile.display_name ?? profile.displayName,
          avatar: profile.avatar ?? profile.avatarUrl,
        });
      })
      .catch(() => {
        if (mounted) setMe(getCachedMe());
      });
    return () => {
      mounted = false;
    };
  }, [pathname]);

  const avatarUrl = me ? profileAvatarUrl(me) : null;
  const name = me ? profileDisplayName(me) : null;
  const loggedIn = Boolean(me && hasUsableSession());

  return (
    <header className="sticky top-0 z-20 border-b border-border bg-bg/90 backdrop-blur">
      <div className="mx-auto flex h-14 max-w-6xl items-center justify-between px-4">
        <Link href="/q" className="flex items-center gap-2 text-sm font-semibold text-fg">
          <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-accent text-white">
            W
          </span>
          War Queue
        </Link>
        <nav className="flex items-center gap-2 text-sm">
          <Link
            href="/q"
            className="rounded-lg px-3 py-1.5 text-muted transition hover:bg-panel hover:text-fg"
          >
            Queue
          </Link>
          <Link
            href="/q/info"
            className="rounded-lg px-3 py-1.5 text-muted transition hover:bg-panel hover:text-fg"
          >
            How to use
          </Link>
          {loggedIn ? (
            <Link
              href="/me"
              title={name ?? "Your profile"}
              aria-label="Your profile"
              className="rounded-full p-0.5 transition hover:bg-panel"
            >
              {avatarUrl ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={avatarUrl}
                  alt=""
                  className="h-8 w-8 rounded-full object-cover ring-1 ring-border"
                />
              ) : (
                <span className="flex h-8 w-8 items-center justify-center rounded-full bg-elevated text-xs font-medium text-muted ring-1 ring-border">
                  {(name ?? "?").slice(0, 1).toUpperCase()}
                </span>
              )}
            </Link>
          ) : (
            <Link
              href="/login"
              className="rounded-lg px-3 py-1.5 text-muted transition hover:bg-panel hover:text-fg"
            >
              Sign in
            </Link>
          )}
        </nav>
      </div>
    </header>
  );
}
