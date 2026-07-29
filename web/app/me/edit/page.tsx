"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ApiError, getMe, updateMe, type MeProfile } from "@/lib/api";

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
  const [accentColor, setAccentColor] = useState("#3b82f6");

  useEffect(() => {
    let mounted = true;
    (async () => {
      try {
        const me = await getMe();
        if (!mounted) return;
        setProfile(me);
        setBio(me.bio ?? "");
        setLinks({
          mkc_url: me.mkc_url ?? "",
          lounge_url: me.lounge_url ?? "",
          x_url: me.x_url ?? "",
          bluesky_url: me.bluesky_url ?? "",
          youtube_url: me.youtube_url ?? "",
          twitch_url: me.twitch_url ?? "",
        });
        setAccentColor(me.accent_color ?? "#3b82f6");
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
        ...(profile?.supporter ? { accent_color: accentColor } : {}),
      });
      setProfile(updated);
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
          Optional — shown as icons on your public profile.
        </p>
        <div className="mt-3 space-y-3">
          {LINK_FIELDS.map((field) => (
            <label key={field.key} className="block">
              <span className="text-xs text-muted">{field.label}</span>
              <input
                value={links[field.key]}
                onChange={(e) =>
                  setLinks((prev) => ({ ...prev, [field.key]: e.target.value }))
                }
                placeholder={field.placeholder}
                className="mt-1 w-full rounded-lg border border-border bg-elevated px-3 py-2 text-sm text-fg placeholder:text-muted focus:border-accent focus:outline-none"
              />
            </label>
          ))}
        </div>
      </section>

      {profile.supporter && (
        <section className="mt-4 rounded-2xl border border-border bg-panel p-5 shadow-panel">
          <h2 className="text-sm font-semibold text-fg">Supporter customization</h2>
          <p className="mt-1 text-xs text-muted">
            Pick colors that show up on your profile and in queue lists.
          </p>
          <div className="mt-3 flex flex-wrap gap-6">
            <label className="flex items-center gap-3">
              <input
                type="color"
                value={accentColor}
                onChange={(e) => setAccentColor(e.target.value)}
                className="h-8 w-8 cursor-pointer rounded-full"
              />
              <span className="text-sm text-muted">Accent color</span>
            </label>
          </div>
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
