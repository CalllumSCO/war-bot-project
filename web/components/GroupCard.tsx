"use client";

import { useMemo, useState } from "react";
import type { MyGroup } from "@/lib/api";
import FillingSurfaceIcons from "./FillingSurfaceIcons";
import PlayerRow from "./PlayerRow";

interface GroupCardProps {
  group: MyGroup | null;
  busyInviteIds: Set<string>;
  queueActionBusy: boolean;
  onUndoInvite: (inviteId: string) => void;
  onJoinQueue: () => void;
  onLeaveQueue: () => void;
  onPostToAllies: () => void;
  onLeaveGroup: () => void;
  onChangeTrack?: (warType: "RT" | "CT") => void;
  onChangeRole?: (role: "runner" | "bagger") => void;
}

export default function GroupCard({
  group,
  busyInviteIds,
  queueActionBusy,
  onUndoInvite,
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
                · {group.onBillboard ? "In queue · On allies board" : "In queue"}
              </span>
            )}
          </p>
        </div>
        {group?.inQueue && (
          <FillingSurfaceIcons surface={group.fillingSurface} className="shrink-0" />
        )}
      </header>

      {group?.isCaptain && !group.inQueue && (
        <div className="space-y-2 px-4 pb-3 pt-2">
          <div className="flex gap-1.5">
            {(["RT", "CT"] as const).map((track) => (
              <button
                key={track}
                type="button"
                disabled={queueActionBusy || !onChangeTrack}
                onClick={() => onChangeTrack?.(track)}
                className={`flex-1 rounded-lg border px-2 py-1.5 text-xs font-medium transition disabled:opacity-50 ${
                  group.warType === track
                    ? "border-accent/50 bg-accent/15 text-accent"
                    : "border-border bg-elevated text-muted hover:text-fg"
                }`}
              >
                {track}
              </button>
            ))}
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

        {!!group?.pendingOutbound?.length && (
          <div className="space-y-2 pt-2">
            {group.pendingOutbound.map((pending) => (
              <div
                key={pending.id}
                className="rounded-2xl border border-danger/60 bg-panel/60 p-2.5 shadow-panel"
              >
                <div className="mb-2 flex items-center justify-between gap-2 px-0.5">
                  <p className="text-xs font-semibold uppercase tracking-wide text-danger">
                    {pending.label}
                  </p>
                </div>
                <div className="space-y-2">
                  {pending.players.map((player) => (
                    <PlayerRow key={player.discordId} player={player} showSr />
                  ))}
                </div>
                <button
                  type="button"
                  onClick={() => onUndoInvite(pending.id)}
                  disabled={busyInviteIds.has(pending.id)}
                  className="mt-2.5 w-full rounded-xl border border-danger/40 px-3 py-2 text-sm font-semibold text-danger transition hover:bg-danger/10 disabled:opacity-50"
                >
                  Undo
                </button>
              </div>
            ))}
          </div>
        )}

        {inviteUrl && (
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
                disabled={
                  queueActionBusy || (!group.isCaptain && !group.inQueue)
                }
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
            {group.isCaptain && (
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
