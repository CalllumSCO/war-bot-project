"use client";

import { useMemo, useState } from "react";
import type { MyGroup } from "@/lib/api";
import { rankIconSrc, rankLabel } from "@/lib/ranks";
import FillingSurfaceIcons from "./FillingSurfaceIcons";
import PlayerRow from "./PlayerRow";
import { isQueueComboEnabled } from "@/lib/queueModes";

interface GroupCardProps {
  group: MyGroup | null;
  queueActionBusy: boolean;
  onJoinQueue: () => void;
  onLeaveQueue: () => void;
  onPostToAllies: () => void;
  onLeaveGroup: () => void;
  onChangeTrack?: (warType: "RT" | "CT") => void;
  onChangeRole?: (role: "runner" | "bagger") => void;
}

export default function GroupCard({
  group,
  queueActionBusy,
  onJoinQueue,
  onLeaveQueue,
  onPostToAllies,
  onLeaveGroup,
  onChangeTrack,
  onChangeRole,
}: GroupCardProps) {
  const size = group?.members.length ?? 0;
  const maxSize = group?.maxSize ?? 5;
  const [copied, setCopied] = useState(false);

  const inviteUrl = useMemo(() => {
    if (!group?.inviteCode || typeof window === "undefined") return null;
    return `${window.location.origin}/q/invite/${group.inviteCode}`;
  }, [group?.inviteCode]);

  const copyInvite = async () => {
    if (!inviteUrl) return;
    try {
      await navigator.clipboard.writeText(inviteUrl);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* ignore */
    }
  };

  const myRole =
    group?.members.find((m) => m.discordId === group.captainDiscordId)?.role ??
    group?.members[0]?.role;

  const avgRankIcon = rankIconSrc(group?.teamAvgRank ?? "unranked");
  const lineupRankIcon = rankIconSrc(group?.lineupTeamRank ?? "unranked");
  const showLineupRank = Boolean(
    group?.lineupFingerprintReady && group?.lineupRevealed && lineupRankIcon
  );
  const showLineupProgress = Boolean(
    group?.lineupFingerprintReady && !group?.lineupRevealed && (group?.lineupGamesTogether ?? 0) > 0
  );
  const seekingOpponents = Boolean(group?.inQueue && group?.canSeekOpponents);

  return (
    <section className="flex max-h-[min(70vh,36rem)] flex-col rounded-2xl border border-border bg-panel/80 shadow-panel">
      <header className="flex items-center justify-between gap-2 px-4 pb-1 pt-4">
        <div>
          <h2 className="text-xs font-semibold uppercase tracking-wide text-muted">My Group</h2>
          <p className="mt-0.5 text-sm text-fg">
            {group?.warType ?? "RT"} · {group?.mode === "casual" ? "Casual" : "Ranked"}
            <span className="text-muted">
              {" "}
              · {size}/{maxSize}
            </span>
            {group?.inQueue && (
              <span className="text-accent">
                {" "}
                ·{" "}
                {seekingOpponents
                  ? "Looking for opponents"
                  : group.onBillboard
                    ? "In queue · On allies board"
                    : "In queue"}
              </span>
            )}
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          {group?.inQueue && (
            <FillingSurfaceIcons surface={group.fillingSurface} className="shrink-0" />
          )}
          {showLineupRank && lineupRankIcon && (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={lineupRankIcon}
              alt={rankLabel(group?.lineupTeamRank)}
              title={`Lineup team · ${rankLabel(group?.lineupTeamRank)}${
                group?.lineupTeamSr != null ? ` · ${group.lineupTeamSr} SR` : ""
              }`}
              className="h-9 w-9"
            />
          )}
          {!showLineupRank && showLineupProgress && (
            <span
              className="rounded-lg border border-border bg-elevated px-2 py-1 text-[11px] font-medium text-muted"
              title="Lineup team SR placements"
            >
              {group?.lineupGamesTogether}/5
            </span>
          )}
          {!showLineupRank && !showLineupProgress && avgRankIcon && (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={avgRankIcon}
              alt={rankLabel(group?.teamAvgRank)}
              title={`Team avg · ${rankLabel(group?.teamAvgRank)}`}
              className="h-9 w-9"
            />
          )}
        </div>
      </header>

      {group?.isCaptain && !group.inQueue && (
        <div className="space-y-2 px-4 pb-3 pt-2">
          <div className="flex gap-1.5">
            {(["RT", "CT"] as const).map((track) => {
              const mode = (group.mode === "casual" ? "casual" : "ranked") as "ranked" | "casual";
              const trackDisabled =
                queueActionBusy || !onChangeTrack || !isQueueComboEnabled(track, mode);
              return (
              <button
                key={track}
                type="button"
                disabled={trackDisabled}
                onClick={() => onChangeTrack?.(track)}
                className={`relative flex-1 rounded-lg border px-2 py-1.5 text-xs font-medium transition disabled:cursor-not-allowed disabled:opacity-50 ${
                  group.warType === track
                    ? "border-accent/50 bg-accent/15 text-accent"
                    : "border-border bg-elevated text-muted hover:text-fg"
                }`}
              >
                {track}
                {track !== "RT" || group.mode === "casual" ? (
                  <span className="ml-1 text-[10px] font-semibold uppercase text-muted">Soon</span>
                ) : null}
              </button>
            );
            })}
          </div>
          <div className="flex gap-1.5">
            {(["runner", "bagger"] as const).map((role) => (
              <button
                key={role}
                type="button"
                disabled={queueActionBusy || !onChangeRole}
                onClick={() => onChangeRole?.(role)}
                className={`flex-1 rounded-lg border px-2 py-1.5 text-xs font-medium capitalize transition disabled:opacity-50 ${
                  myRole === role
                    ? "border-accent/50 bg-accent/15 text-accent"
                    : "border-border bg-elevated text-muted hover:text-fg"
                }`}
              >
                {role}
              </button>
            ))}
          </div>
        </div>
      )}

      <div className="scroll-thin min-h-0 flex-1 space-y-2 overflow-y-auto px-4 pb-3">
        {!group || size === 0 ? (
          <div className="rounded-xl border border-dashed border-border px-3 py-8 text-center">
            <p className="text-sm text-muted">No group yet.</p>
          </div>
        ) : (
          group.members.map((member) => (
            <PlayerRow key={member.discordId} player={member} showSr />
          ))
        )}

        {inviteUrl && !seekingOpponents && (
          <div className="pt-1">
            <p className="mb-1.5 px-0.5 text-xs font-semibold uppercase tracking-wide text-muted">
              Invite link
            </p>
            <div className="flex gap-2">
              <input
                readOnly
                value={inviteUrl}
                className="min-w-0 flex-1 truncate rounded-xl border border-border bg-elevated px-3 py-2 text-xs text-muted"
              />
              <button
                type="button"
                onClick={copyInvite}
                className="shrink-0 rounded-xl border border-border bg-elevated px-3 py-2 text-xs font-medium text-fg transition hover:border-accent/40 hover:text-accent"
              >
                {copied ? "Copied" : "Copy"}
              </button>
            </div>
          </div>
        )}
      </div>

      <footer className="space-y-2 border-t border-border p-3">
        {group && size > 0 ? (
          <>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={group.inQueue ? onLeaveQueue : onJoinQueue}
                disabled={queueActionBusy || (!group.isCaptain && !group.inQueue)}
                className={`flex-1 rounded-xl px-3 py-2.5 text-sm font-semibold transition disabled:opacity-50 ${
                  group.inQueue
                    ? "border border-border text-fg hover:bg-elevated"
                    : "bg-accent text-white hover:bg-accent-hover"
                }`}
              >
                {group.inQueue
                  ? group.isCaptain
                    ? "Leave queue"
                    : "Leave roster"
                  : "Join queue"}
              </button>
              <button
                type="button"
                onClick={onLeaveGroup}
                disabled={queueActionBusy}
                className="rounded-xl border border-border px-3 py-2.5 text-sm font-medium text-danger transition hover:bg-danger/10 disabled:opacity-50"
              >
                Leave
              </button>
            </div>
            {group.isCaptain && !seekingOpponents && (
              <button
                type="button"
                onClick={onPostToAllies}
                disabled={queueActionBusy || group.onBillboard}
                className={`w-full rounded-xl border px-3 py-2.5 text-sm font-semibold transition disabled:opacity-50 ${
                  group.onBillboard
                    ? "border-border bg-elevated text-muted"
                    : "border-accent/40 text-accent hover:bg-accent/10"
                }`}
                title={
                  group.onBillboard
                    ? "Already on the Discord allies billboard"
                    : "Also show this group on the Discord allies channel"
                }
              >
                {group.onBillboard ? "Posted to allies billboard" : "Post to allies billboard"}
              </button>
            )}
          </>
        ) : (
          <p className="w-full text-center text-xs text-muted">Start from the lobby screen.</p>
        )}
      </footer>
    </section>
  );
}
