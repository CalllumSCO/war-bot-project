"use client";

import type { WarDetail, WarPlayerResult, WarSide } from "@/lib/api";
import { rankIconSrc, rankLabel } from "@/lib/ranks";

function Avatar({ url, name }: { url?: string | null; name: string }) {
  if (url) {
    // eslint-disable-next-line @next/next/no-img-element
    return (
      <img src={url} alt="" className="h-10 w-10 rounded-full object-cover ring-1 ring-border" />
    );
  }
  return (
    <div className="flex h-10 w-10 items-center justify-center rounded-full bg-elevated text-sm font-semibold text-muted ring-1 ring-border">
      {name.slice(0, 2).toUpperCase()}
    </div>
  );
}

function SrUnderName({ player }: { player: WarPlayerResult }) {
  if (!player.revealed || player.srDelta == null) {
    return <p className="text-xs text-muted">Unranked</p>;
  }
  const up = player.srDelta >= 0;
  return (
    <p className={`text-xs font-medium tabular-nums ${up ? "text-success" : "text-warning"}`}>
      {up ? "▲" : "▼"} {Math.abs(player.srDelta)} SR
    </p>
  );
}

function PlayerResultRow({ player }: { player: WarPlayerResult }) {
  const icon = rankIconSrc(player.revealed ? player.rank : "unranked");
  return (
    <div className="flex items-center gap-3 py-2">
      <Avatar url={player.avatarUrl} name={player.displayName} />
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <p className="truncate text-sm font-semibold text-fg">{player.displayName}</p>
          {icon && (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={icon}
              alt={rankLabel(player.revealed ? player.rank : "unranked")}
              className="h-5 w-5 shrink-0"
            />
          )}
        </div>
        <SrUnderName player={player} />
      </div>
      <p className="w-10 shrink-0 text-right text-sm font-semibold tabular-nums text-fg">
        {player.indiv != null ? player.indiv : "—"}
      </p>
    </div>
  );
}

function TeamColumn({
  side,
  align,
}: {
  side: WarSide;
  align: "left" | "right";
}) {
  return (
    <div className={align === "right" ? "text-right" : undefined}>
      <h2 className={`text-base font-semibold text-fg ${align === "right" ? "text-right" : ""}`}>
        {side.teamName}
      </h2>
      {side.total != null && (
        <p className={`mt-0.5 text-xs text-muted ${align === "right" ? "text-right" : ""}`}>
          Team total {side.total}
        </p>
      )}
      <div className="mt-3 divide-y divide-border">
        {side.players.map((player, i) => (
          <div key={player.discordId ?? `${side.teamName}-${i}`} className={align === "right" ? "" : ""}>
            <PlayerResultRow player={player} />
          </div>
        ))}
      </div>
    </div>
  );
}

export default function MatchResultDashboard({ war }: { war: WarDetail }) {
  const when = war.completedAt
    ? new Date(war.completedAt).toLocaleString(undefined, {
        dateStyle: "medium",
        timeStyle: "short",
      })
    : null;
  const margin = war.scrimPlusMinus ?? war.pointMargin;
  const scoreLine =
    war.winner.total != null && war.loser.total != null
      ? `${war.winner.total} – ${war.loser.total}`
      : margin != null
        ? `+${Math.abs(margin)}`
        : "Final";

  return (
    <div>
      <header className="mb-6 text-center">
        <p className="text-xs font-semibold uppercase tracking-wide text-muted">
          {war.warType ?? "RT"} · {war.mode === "casual" ? "Casual" : "Ranked"}
          {war.rxx ? ` · ${war.rxx}` : ""}
        </p>
        <h1 className="mt-1 text-2xl font-semibold text-fg">{scoreLine} Final</h1>
        {when && <p className="mt-1 text-sm text-muted">{when}</p>}
      </header>

      <div className="grid grid-cols-1 items-start gap-4 md:grid-cols-[1fr_auto_1fr]">
        <section className="rounded-2xl border border-border bg-panel/80 p-4 shadow-panel">
          <TeamColumn side={war.winner} align="left" />
        </section>

        <div className="flex flex-col items-center justify-center px-2 py-4">
          <p className="text-[10px] font-semibold uppercase tracking-wide text-muted">Scrim</p>
          <p
            className={`mt-1 text-2xl font-bold tabular-nums ${
              margin != null && margin >= 0 ? "text-success" : "text-warning"
            }`}
          >
            {margin == null ? "—" : margin >= 0 ? `+${margin}` : `${margin}`}
          </p>
        </div>

        <section className="rounded-2xl border border-border bg-panel/80 p-4 shadow-panel">
          <TeamColumn side={war.loser} align="left" />
        </section>
      </div>
    </div>
  );
}
