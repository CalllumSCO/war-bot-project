"use client";

import { profileLinksFrom } from "@/lib/profileLinks";
import type { MeProfile } from "@/lib/api";

export default function ProfileLinkIcons({
  profile,
}: {
  profile: Pick<
    MeProfile,
    "mkc_url" | "lounge_url" | "x_url" | "bluesky_url" | "youtube_url" | "twitch_url"
  >;
}) {
  const links = profileLinksFrom(profile);
  if (!links.length) return null;

  return (
    <div className="mt-2 flex flex-wrap items-center gap-2">
      {links.map((link) => (
        <a
          key={link.key}
          href={link.href}
          target="_blank"
          rel="noopener noreferrer"
          title={link.label}
          aria-label={link.label}
          className="inline-flex h-8 w-8 items-center justify-center rounded-lg border border-border bg-elevated text-muted transition hover:border-accent hover:text-fg"
        >
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={link.iconSrc} alt="" className="h-4 w-4" />
        </a>
      ))}
    </div>
  );
}
