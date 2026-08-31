"use client";

import {
  FAVORITE_LANE_OPTIONS,
  isFavoriteLane,
  type FavoriteLane,
} from "@/lib/favoriteLane";
import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ApiError, getMe, updateMe, type MeProfile } from "@/lib/api";
import FriendCodeLinkCard from "@/components/FriendCodeLinkCard";

type LinkField = {
  key: "mkc_url" | "lounge_url" | "x_url" | "bluesky_url" | "youtube_url" | "twitch_url";
  label: string;
  placeholder: string;
};

const LINK_FIELDS: LinkField[] = [
  { key: "mkc_url", label: "MKCentral", placeholder: "https://mkcentral.com/..." },
  { key: "lounge_url", label: "Lounge", placeholder: "https://mkwlounge.gg/..." },
  { key: "x_url", label: "X", placeholder: "https://x.com/..." },
  { key: "bluesky_url", label: "Bluesky", placeholder: "https://bsky.app/..." },
  { key: "youtube_url", label: "YouTube", placeholder: "https://youtube.com/..." },
  { key: "twitch_url", label: "Twitch", placeholder: "https://twitch.tv/..." },
];

export default function EditProfilePage() {
  const router = useRouter();
  const [profile, setProfile] = useState<MeProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  const [bio, setBio] = useState("");
  const [links, setLinks] = useState<Record<LinkField["key"], string>>({
    mkc_url: "",
    lounge_url: "",
    x_url: "",
    bluesky_url: "",
    youtube_url: "",
    twitch_url: "",
  });
  /** Fields that were already set when the page loaded — locked until Unlink. */
  const [locked, setLocked] = useState<Partial<Record<LinkField["key"], boolean>>>({});
  const [accentColor, setAccentColor] = useState("#3b82f6");
  const [lineupNameColor, setLineupNameColor] = useState("#f59e0b");
  const [displayName, setDisplayName] = useState("");
  const [favoriteTrack, setFavoriteTrack] = useState<FavoriteLane>("");
  const [profileAlias, setProfileAlias] = useState("");

  useEffect(() => {
    let mounted = true;
    (async () => {
      try {
        const me = await getMe();
        if (!mounted) return;
        setProfile(me);
        setBio(me.bio ?? "");
        const nextLinks = {
          mkc_url: me.mkc_url ?? "",
          lounge_url: me.lounge_url ?? "",
          x_url: me.x_url ?? "",
          bluesky_url: me.bluesky_url ?? "",
          youtube_url: me.youtube_url ?? "",
          twitch_url: me.twitch_url ?? "",
        };
        setLinks(nextLinks);
        setLocked(
          Object.fromEntries(
            LINK_FIELDS.map((field) => [field.key, Boolean(nextLinks[field.key].trim())])
          ) as Record<LinkField["key"], boolean>
        );
        setAccentColor(me.accent_color ?? "#3b82f6");
        setLineupNameColor(me.lineup_name_color ?? "#f59e0b");
        setDisplayName(me.display_name ?? "");
        setFavoriteTrack(
          isFavoriteLane(me.favorite_track ?? "") ? (me.favorite_track as FavoriteLane) : ""
        );
        setProfileAlias(me.profile_alias ?? "");
      } catch (err) {
        if (!mounted) return;
        if (err instanceof ApiError && err.status === 401) {
          router.push("/login");
          return;
        }
        setError("Couldn't load your profile right now.");
      } finally {
        if (mounted) setLoading(false);
      }
    })();
    return () => {
      mounted = false;
    };
  }, [router]);

  const unlink = (key: LinkField["key"]) => {
    setLinks((prev) => ({ ...prev, [key]: "" }));
    setLocked((prev) => ({ ...prev, [key]: false }));
  };

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    setSaved(false);
    try {
      const updated = await updateMe({
        bio,
        mkc_url: links.mkc_url || null,
        lounge_url: links.lounge_url || null,
        x_url: links.x_url || null,
        bluesky_url: links.bluesky_url || null,
        youtube_url: links.youtube_url || null,
        twitch_url: links.twitch_url || null,
        ...(profile?.supporter
          ? {
              accent_color: accentColor,
              lineup_name_color: lineupNameColor,
              display_name: displayName.trim() || null,
              favorite_track: favoriteTrack || null,
            }
          : {}),
        ...(profile?.supporter_tier === "supporter_plus"
          ? { profile_alias: profileAlias.trim() || null }
          : {}),
      });
      setProfile(updated);
      setLocked(
        Object.fromEntries(
          LINK_FIELDS.map((field) => [
            field.key,
            Boolean((updated[field.key] ?? links[field.key] ?? "").toString().trim()),
          ])
        ) as Record<LinkField["key"], boolean>
      );
      setSaved(true);
      setTimeout(() => router.push("/me"), 600);
    } catch {
      setError("Couldn't save your changes. Try again.");
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <main className="mx-auto max-w-2xl px-4 py-8">
        <p className="text-sm text-muted">Loading…</p>
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
    <main className="mx-auto max-w-2xl px-4 py-8 pb-24">
      <div className="mb-6 flex items-center justify-between gap-3">
        <h1 className="text-lg font-semibold text-fg">Edit profile</h1>
        <Link href="/me" className="text-sm text-muted transition hover:text-fg">
          Cancel
        </Link>
      </div>

      {error && (
        <div className="mb-4 rounded-lg border border-danger/30 bg-danger/10 px-4 py-2.5 text-sm text-danger">
          {error}
        </div>
      )}

      <div className="mb-4">
        <FriendCodeLinkCard
          profile={profile}
          onLinked={(updated) => {
            setProfile(updated);
          }}
        />
      </div>

      <section className="rounded-2xl border border-border bg-panel p-5 shadow-panel">
        <h2 className="text-sm font-semibold text-fg">Bio</h2>
        <textarea
          value={bio}
          onChange={(e) => setBio(e.target.value)}
          maxLength={280}
          rows={3}
          placeholder="Say a little about your playstyle…"
          className="mt-3 w-full resize-none rounded-lg border border-border bg-elevated px-3 py-2 text-sm text-fg placeholder:text-muted focus:border-accent focus:outline-none"
        />
        <p className="mt-1 text-right text-xs text-muted">{bio.length}/280</p>
      </section>

      <section className="mt-4 rounded-2xl border border-border bg-panel p-5 shadow-panel">
        <h2 className="text-sm font-semibold text-fg">Links</h2>
        <p className="mt-1 text-xs text-muted">
          Optional — shown as icons on your public profile. Linked fields stay locked until you
          unlink them.
        </p>
        <div className="mt-3 space-y-3">
          {LINK_FIELDS.map((field) => {
            const isLocked = Boolean(locked[field.key] && links[field.key].trim());
            return (
              <div key={field.key}>
                <div className="flex items-center justify-between gap-2">
                  <span className="text-xs text-muted">{field.label}</span>
                  {isLocked && (
                    <button
                      type="button"
                      onClick={() => unlink(field.key)}
                      className="text-xs font-medium text-danger transition hover:underline"
                    >
                      Unlink
                    </button>
                  )}
                </div>
                <input
                  value={links[field.key]}
                  onChange={(e) =>
                    setLinks((prev) => ({ ...prev, [field.key]: e.target.value }))
                  }
                  placeholder={field.placeholder}
                  readOnly={isLocked}
                  disabled={isLocked}
                  className={`mt-1 w-full rounded-lg border border-border px-3 py-2 text-sm placeholder:text-muted focus:border-accent focus:outline-none ${
                    isLocked
                      ? "cursor-not-allowed bg-bg text-muted"
                      : "bg-elevated text-fg"
                  }`}
                />
              </div>
            );
          })}
        </div>
      </section>

      {profile.supporter && (
        <section className="mt-4 rounded-2xl border border-border bg-panel p-5 shadow-panel">
          <div className="flex items-start justify-between gap-3">
            <div>
              <h2 className="text-sm font-semibold text-fg">Supporter customization</h2>
              <p className="mt-1 text-xs text-muted">
                Profile accent, custom display name, featured lane, and match/chat name color.
              </p>
            </div>
            <Link
              href="/me/supporter"
              className="shrink-0 text-xs font-medium text-accent hover:underline"
            >
              Perks
            </Link>
          </div>
          <div className="mt-4 space-y-4">
            <label className="block">
              <span className="text-xs text-muted">Display name</span>
              <input
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
                maxLength={64}
                placeholder={profile.username ?? "Your name"}
                className="mt-1 w-full rounded-lg border border-border bg-elevated px-3 py-2 text-sm text-fg placeholder:text-muted focus:border-accent focus:outline-none"
              />
            </label>
            <label className="block">
              <span className="text-xs text-muted">Featured lane on profile</span>
              <select
                value={favoriteTrack}
                onChange={(e) => {
                  const value = e.target.value;
                  setFavoriteTrack(isFavoriteLane(value) ? value : "");
                }}
                className="mt-1 w-full rounded-lg border border-border bg-elevated px-3 py-2 text-sm text-fg focus:border-accent focus:outline-none"
              >
                {FAVORITE_LANE_OPTIONS.map((opt) => (
                  <option key={opt.value || "default"} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
            </label>
            <div className="flex flex-wrap gap-6">
              <label className="flex items-center gap-3">
                <input
                  type="color"
                  value={accentColor}
                  onChange={(e) => setAccentColor(e.target.value)}
                  className="h-8 w-8 cursor-pointer rounded-full"
                />
                <span className="text-sm text-muted">Profile accent</span>
              </label>
              <label className="flex items-center gap-3">
                <input
                  type="color"
                  value={lineupNameColor}
                  onChange={(e) => setLineupNameColor(e.target.value)}
                  className="h-8 w-8 cursor-pointer rounded-full"
                />
                <span className="text-sm text-muted">Match & chat name color</span>
              </label>
            </div>
          </div>
        </section>
      )}

      {profile.supporter_tier === "supporter_plus" && (
        <section className="mt-4 rounded-2xl border border-border bg-panel p-5 shadow-panel">
          <h2 className="text-sm font-semibold text-fg">Supporter+ vanity URL</h2>
          <p className="mt-1 text-xs text-muted">
            Share <span className="font-mono text-fg">/u/your-alias</span> instead of your Discord id.
          </p>
          <div className="mt-3 flex items-center gap-2">
            <span className="text-sm text-muted">/u/</span>
            <input
              value={profileAlias}
              onChange={(e) => setProfileAlias(e.target.value.toLowerCase())}
              maxLength={32}
              placeholder="your-alias"
              className="flex-1 rounded-lg border border-border bg-elevated px-3 py-2 font-mono text-sm text-fg placeholder:text-muted focus:border-accent focus:outline-none"
            />
          </div>
        </section>
      )}

      {!profile.supporter && (
        <section className="mt-4 rounded-2xl border border-dashed border-border bg-panel/50 p-5">
          <h2 className="text-sm font-semibold text-fg">Supporter perks</h2>
          <p className="mt-1 text-sm text-muted">
            Queue peeking, profile styling, vanity URLs (Supporter+), and more planned perks.
          </p>
          <Link
            href="/me/supporter"
            className="mt-3 inline-block text-sm font-medium text-accent hover:underline"
          >
            Learn more
          </Link>
        </section>
      )}

      <div className="fixed inset-x-0 bottom-0 border-t border-border bg-bg/95 backdrop-blur">
        <div className="mx-auto flex max-w-2xl items-center justify-end gap-3 px-4 py-3">
          {saved && <span className="text-xs text-success">Saved</span>}
          <button
            type="button"
            onClick={handleSave}
            disabled={saving}
            className="rounded-lg bg-accent px-5 py-2 text-sm font-medium text-white transition hover:bg-accent-hover disabled:opacity-50"
          >
            {saving ? "Saving…" : "Save changes"}
          </button>
        </div>
      </div>
    </main>
  );
}
