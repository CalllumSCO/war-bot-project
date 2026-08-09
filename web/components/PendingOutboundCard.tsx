"use client";

import type { PendingOutbound } from "@/lib/api";
import { rankIconSrc, rankLabel } from "@/lib/ranks";
import PlayerRow from "./PlayerRow";

export default function PendingOutboundCard({
  pending,
  busy,
  onUndo,
}: {
  pending: PendingOutbound;
  busy: boolean;
  onUndo: (id: string) => void;
}) {
  const anon = Boolean(pending.anonymous);
  const challengeIcon = rankIconSrc(pending.teamAvgRank ?? "unranked");

  return (
    <div className="rounded-2xl border border-danger/60 bg-panel/80 p-2.5 shadow-panel">
      <div className="mb-2 flex items-center justify-between gap-2 px-0.5">
        <p className="text-xs font-semibold uppercase tracking-wide text-danger">
          {pending.label}
        </p>
      </div>
      {anon ? (
        <div className="flex justify-center py-2">
          {challengeIcon ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={challengeIcon}
              alt={rankLabel(pending.teamAvgRank)}
              title={rankLabel(pending.teamAvgRank)}
              className="h-14 w-14"
            />
          ) : null}
        </div>
      ) : (
        <div className="space-y-2">
          {pending.players.map((player) => (
            <PlayerRow key={player.discordId} player={player} showSr />
          ))}
        </div>
      )}
      <button
        type="button"
        onClick={() => onUndo(pending.id)}
        disabled={busy}
        className="mt-2.5 w-full rounded-xl border border-danger/40 px-3 py-2 text-sm font-semibold text-danger transition hover:bg-danger/10 disabled:opacity-50"
      >
        Undo
      </button>
    </div>
  );
}
