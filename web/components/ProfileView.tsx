"use client";

import { useEffect, useState } from "react";
import {
  flattenRatings,
  listUserWars,
  profileAvatarUrl,
  profileDiscordUsername,
  profileDisplayName,
  type MeProfile,
  type RatingRow,
  type WarSummary,
} from "@/lib/api";
import { parseFavoriteLane, type FavoriteLane } from "@/lib/favoriteLane";
import { rankIconSrc, rankLabel } from "@/lib/ranks";
import ProfileLinkIcons from "@/components/ProfileLinkIcons";
import MatchHistoryList from "@/components/MatchHistoryList";
import PatronFooter from "@/components/PatronFooter";

const TRACK_LABELS: Record<string, string> = { rt: "Regular Tracks", ct: "Custom Tracks" };

function sortBySrDesc(rows: RatingRow[]): RatingRow[] {
  return [...rows].sort((a, b) => {
    const aScore = a.revealed && a.sr != null ? a.sr : -1;
    const bScore = b.revealed && b.sr != null ? b.sr : -1;
    return bScore - aScore;
  });
}

function pickFeaturedRating(
  rows: RatingRow[],
  favoriteLane?: FavoriteLane | string | null
): [RatingRow | undefined, RatingRow[]] {
  const sorted = sortBySrDesc(rows);
  const pref = parseFavoriteLane(favoriteLane);
  if (!pref) {
    const [top, ...rest] = sorted;
    return [top, rest];
  }
  let featured: RatingRow | undefined;
  if (pref.track && pref.role) {
    featured = sorted.find((row) => row.track === pref.track && row.role === pref.role);
  } else if (pref.track) {
    featured = sortBySrDesc(sorted.filter((row) => row.track === pref.track))[0];
  }
  featured = featured ?? sorted[0];
  if (!featured) return [undefined, []];
  const rest = sorted.filter((row) => row !== featured);
  return [featured, rest];
}

function laneTitle(row: RatingRow): string {
  const track = TRACK_LABELS[row.track] ?? row.track.toUpperCase();
  return `${track} · ${row.role}`;
}

export default function ProfileView({
  profile,
  headerAction,
}: {
  profile: MeProfile;
  headerAction?: React.ReactNode;
}) {
  const displayName = profileDisplayName(profile);
  const username = profileDiscordUsername(profile);
  const avatarUrl = profileAvatarUrl(profile);
  const [top, rest] = pickFeaturedRating(
    flattenRatings(profile.ratings),
    profile.favorite_track ?? null
  );
  const topIcon = rankIconSrc(top?.revealed ? top.rank : "unranked");
  const fc = profile.friend_code?.trim() || null;

  const [wars, setWars] = useState<WarSummary[]>([]);
  const [warsLoading, setWarsLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    const id = profile.discord_id ?? profile.discordId;
    if (id == null) {
      setWarsLoading(false);
      return;
    }
    listUserWars(id, 20)
      .then((rows) => {
        if (!cancelled) setWars(rows);
      })
      .catch(() => {
        if (!cancelled) setWars([]);
      })
      .finally(() => {
        if (!cancelled) setWarsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [profile.discord_id, profile.discordId]);

  return (
    <div>
      <div className="flex items-start justify-between gap-4">
        <div className="flex min-w-0 items-start gap-4">
          {avatarUrl ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={avatarUrl}
              alt=""
              className="h-16 w-16 rounded-full object-cover"
              style={
                profile.supporter && profile.accent_color
                  ? { boxShadow: `0 0 0 2px ${profile.accent_color}` }
                  : undefined
              }
            />
          ) : (
            <div className="flex h-16 w-16 items-center justify-center rounded-full bg-elevated text-lg font-medium text-muted">
              {displayName.slice(0, 2).toUpperCase()}
            </div>
          )}
          <div className="min-w-0">
            <h1
              className="text-xl font-semibold"
              style={
                profile.supporter && profile.accent_color
                  ? { color: profile.accent_color }
                  : undefined
              }
            >
              {displayName}
            </h1>
            <div className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-sm text-muted">
              {username && <span>@{username}</span>}
              {username && fc && <span className="text-border">·</span>}
              {fc && (
                <span className="font-mono text-xs text-fg/90" title="Wii friend code">
                  {fc}
                </span>
              )}
            </div>
            {profile.supporter && (
              <span className="mt-1 inline-block text-xs font-medium text-warning">
                {profile.supporter_tier_label ?? "Supporter"}
              </span>
            )}
            <ProfileLinkIcons profile={profile} />
          </div>
        </div>
        {headerAction}
      </div>

      {profile.bio && (
        <p className="mt-5 whitespace-pre-wrap text-sm leading-relaxed text-fg">{profile.bio}</p>
      )}

      <section className="mt-6 rounded-2xl border border-border bg-panel p-5 shadow-panel">
        <h2 className="text-sm font-semibold text-fg">Scrims Rating</h2>
        {!top ? (
          <p className="mt-3 text-sm text-muted">Play a ranked war to start earning SR.</p>
        ) : (
          <div className="mt-4">
            <div className="flex items-center gap-4 rounded-xl border border-border bg-elevated/60 px-4 py-4">
              {topIcon && (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={topIcon}
                  alt={rankLabel(top.revealed ? top.rank : "unranked")}
                  className="h-16 w-16"
                />
              )}
              <div>
                <p className="text-lg font-semibold capitalize text-fg">
                  {rankLabel(top.revealed ? top.rank : "unranked")}
                </p>
                <p className="text-sm capitalize text-muted">{laneTitle(top)}</p>
                <p className="mt-0.5 text-sm tabular-nums text-muted">
                  {top.revealed && top.sr != null
                    ? `${top.sr} SR`
                    : `${top.placement_count ?? 0}/5 placements`}
                </p>
              </div>
            </div>

            {!!rest.length && (
              <div className="mt-2 divide-y divide-border">
                {rest.map((rating) => {
                  const icon = rankIconSrc(rating.revealed ? rating.rank : "unranked");
                  return (
                    <div
                      key={`${rating.track}-${rating.role}`}
                      className="flex items-center justify-between py-2.5"
                    >
                      <div>
                        <p className="text-sm capitalize text-fg">{laneTitle(rating)}</p>
                        <p className="text-xs text-muted">
                          {rating.revealed && rating.sr != null
                            ? `${rating.sr} SR`
                            : `${rating.placement_count ?? 0}/5 placements`}
                        </p>
                      </div>
                      {icon && (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img
                          src={icon}
                          alt={rankLabel(rating.revealed ? rating.rank : "unranked")}
                          title={rankLabel(rating.revealed ? rating.rank : "unranked")}
                          className="h-8 w-8"
                        />
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}
      </section>

      <section className="mt-6 rounded-2xl border border-border bg-panel p-5 shadow-panel">
        <h2 className="text-sm font-semibold text-fg">Career</h2>
        <p className="mt-0.5 text-xs text-muted">Recent wars — open one for indivs and SR changes.</p>
        <div className="mt-4">
          {warsLoading ? (
            <div className="animate-pulse space-y-2">
              <div className="h-20 rounded-2xl bg-elevated" />
              <div className="h-20 rounded-2xl bg-elevated" />
            </div>
          ) : (
            <MatchHistoryList wars={wars} />
          )}
        </div>
      </section>

      <PatronFooter />
    </div>
  );
}
