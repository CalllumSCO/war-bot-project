/** Clickable profile link icons (MKC, Lounge, socials). */

export type ProfileLinkKey =
  | "mkc"
  | "lounge"
  | "x"
  | "bluesky"
  | "youtube"
  | "twitch";

export interface ProfileLink {
  key: ProfileLinkKey;
  label: string;
  href: string;
  iconSrc: string;
}

const LINK_META: Record<
  ProfileLinkKey,
  { label: string; field: string; iconSrc: string }
> = {
  mkc: {
    label: "MKCentral",
    field: "mkc_url",
    iconSrc: "/links/mkcentral.png",
  },
  lounge: {
    label: "Lounge",
    field: "lounge_url",
    iconSrc: "/links/lounge.png",
  },
  x: { label: "X", field: "x_url", iconSrc: "/links/x.svg" },
  bluesky: {
    label: "Bluesky",
    field: "bluesky_url",
    iconSrc: "/links/bluesky.svg",
  },
  youtube: {
    label: "YouTube",
    field: "youtube_url",
    iconSrc: "/links/youtube.svg",
  },
  twitch: {
    label: "Twitch",
    field: "twitch_url",
    iconSrc: "/links/twitch.svg",
  },
};

const ORDER: ProfileLinkKey[] = ["mkc", "lounge", "x", "bluesky", "youtube", "twitch"];

export function profileLinksFrom(
  profile: Partial<Record<string, string | null | undefined>> | null | undefined
): ProfileLink[] {
  if (!profile) return [];
  const links: ProfileLink[] = [];
  for (const key of ORDER) {
    const meta = LINK_META[key];
    const href = String(profile[meta.field] ?? "").trim();
    if (!href) continue;
    links.push({ key, label: meta.label, href, iconSrc: meta.iconSrc });
  }
  return links;
}
