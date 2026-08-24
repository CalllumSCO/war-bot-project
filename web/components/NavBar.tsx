"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import {
  getCachedMe,
  getMeCached,
  hasUsableSession,
  profileAvatarUrl,
  profileDisplayName,
  signOut,
  type CachedMe,
} from "@/lib/api";

export default function NavBar() {
  const pathname = usePathname();
  const router = useRouter();
  const [me, setMe] = useState<CachedMe | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setMe(getCachedMe());
    setMenuOpen(false);
    if (!hasUsableSession()) {
      setMe(null);
      return;
    }
    let mounted = true;
    getMeCached()
      .then((profile) => {
        if (!mounted) return;
        setMe({
          discord_id: profile.discord_id,
          display_name: profile.display_name ?? profile.displayName,
          avatar: profile.avatar ?? profile.avatarUrl,
          supporter: Boolean(profile.supporter),
        });
      })
      .catch(() => {
        if (mounted) setMe(getCachedMe());
      });
    return () => {
      mounted = false;
    };
  }, [pathname]);

  useEffect(() => {
    if (!menuOpen) return;
    const onPointerDown = (event: MouseEvent) => {
      if (!menuRef.current?.contains(event.target as Node)) {
        setMenuOpen(false);
      }
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setMenuOpen(false);
    };
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [menuOpen]);

  const avatarUrl = me ? profileAvatarUrl(me) : null;
  const name = me ? profileDisplayName(me) : null;
  const loggedIn = Boolean(me && hasUsableSession());

  const handleSignOut = () => {
    setMenuOpen(false);
    signOut();
    setMe(null);
    router.push("/login");
  };

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
            Guide
          </Link>
          {loggedIn ? (
            <div className="relative" ref={menuRef}>
              <button
                type="button"
                title={name ?? "Account menu"}
                aria-label="Account menu"
                aria-haspopup="menu"
                aria-expanded={menuOpen}
                onClick={() => setMenuOpen((open) => !open)}
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
              </button>
              {menuOpen && (
                <div
                  role="menu"
                  className="absolute right-0 mt-2 w-44 overflow-hidden rounded-xl border border-border bg-panel py-1 shadow-panel"
                >
                  {name && (
                    <p className="truncate border-b border-border px-3 py-2 text-xs text-muted">
                      {name}
                    </p>
                  )}
                  <Link
                    role="menuitem"
                    href="/me"
                    onClick={() => setMenuOpen(false)}
                    className="block px-3 py-2 text-sm text-fg transition hover:bg-elevated"
                  >
                    Profile
                  </Link>
                  <Link
                    role="menuitem"
                    href="/me/edit"
                    onClick={() => setMenuOpen(false)}
                    className="block px-3 py-2 text-sm text-fg transition hover:bg-elevated"
                  >
                    Edit profile
                  </Link>
                  <button
                    role="menuitem"
                    type="button"
                    onClick={handleSignOut}
                    className="block w-full px-3 py-2 text-left text-sm text-danger transition hover:bg-danger/10"
                  >
                    Sign out
                  </button>
                </div>
              )}
            </div>
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
