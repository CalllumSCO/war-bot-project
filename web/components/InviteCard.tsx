"use client";

import type { IncomingInvitation } from "@/lib/api";
import { rankIconSrc, rankLabel } from "@/lib/ranks";
import PlayerRow from "./PlayerRow";

interface InviteCardProps {
  invitation: IncomingInvitation;
  busy: boolean;
  onAccept: (id: string) => void;
  onDeny: (id: string) => void;
}

export default function InviteCard({ invitation, busy, onAccept, onDeny }: InviteCardProps) {
  const isChallenge = invitation.kind === "challenge";
  const anonymous = Boolean(invitation.anonymous);
  const icon = rankIconSrc(invitation.teamAvgRank ?? "unranked");

  return (
    <div className="rounded-2xl border border-border bg-panel/60 p-2.5 shadow-panel">
      {isChallenge && anonymous ? (
        <div className="flex flex-col items-center gap-2 py-2">
          <p className="text-xs font-semibold uppercase tracking-wide text-muted">
            {invitation.label ?? "Challenge"}
          </p>
          {icon ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={icon}
              alt={rankLabel(invitation.teamAvgRank)}
              title={rankLabel(invitation.teamAvgRank)}
              className="h-14 w-14"
            />
          ) : (
            <span className="text-sm text-muted">?</span>
          )}
        </div>
      ) : (
        <div className="space-y-2">
          {isChallenge && (
            <p className="px-0.5 text-xs font-semibold uppercase tracking-wide text-muted">
              {invitation.label ?? "Challenge"}
            </p>
          )}
          {invitation.fromPlayers.map((player) => (
            <PlayerRow key={player.discordId} player={player} showSr />
          ))}
        </div>
      )}
      <div className="mt-2.5 flex gap-2">
        <button
          type="button"
          onClick={() => onAccept(invitation.id)}
          disabled={busy}
          className="flex-1 rounded-xl border border-success/30 bg-success/10 px-3 py-2 text-sm font-semibold text-success transition hover:bg-success/20 disabled:opacity-50"
        >
          Accept
        </button>
        <button
          type="button"
          onClick={() => onDeny(invitation.id)}
          disabled={busy}
          className="flex-1 rounded-xl border border-danger/30 bg-danger/10 px-3 py-2 text-sm font-semibold text-danger transition hover:bg-danger/20 disabled:opacity-50"
        >
          Deny
        </button>
      </div>
    </div>
  );
}
