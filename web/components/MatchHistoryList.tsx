"use client";

import Link from "next/link";
import type { WarPlayerResult, WarSummary } from "@/lib/api";

function Avatar({ url, name }: { url?: string | null; name: string }) {
  if (url) {
    // eslint-disable-next-line @next/next/no-img-element
    return (
      <img src={url} alt="" className="h-7 w-7 rounded-full object-cover ring-1 ring-border" />
    );
  }
  return (
    <div className="flex h-7 w-7 items-center justify-center rounded-full bg-elevated text-[10px] font-semibold text-muted ring-1 ring-border">
      {name.slice(0, 1).toUpperCase()}
    </div>
  );
}

function PlayerChip({ player }: { player: WarPlayerResult }) {
  const short =
    player.displayName.length > 10
      ? `${player.displayName.slice(0, 9)}…`
      : player.displayName;
  return (
    <div className="flex min-w-0 items-center gap-1.5">
      <Avatar url={player.avatarUrl} name={player.displayName} />
      <span className="truncate text-xs text-fg" title={player.displayName}>
        {short}
      </span>
    </div>
  );
}

function SrDelta({ delta }: { delta?: number | null }) {
  if (delta == null) return null;
  const up = delta >= 0;
  return (
    <span className={`text-xs font-medium tabular-nums ${up ? "text-success" : "text-warning"}`}>
      {up ? "▲" : "▼"} {Math.abs(delta)} SR
    </span>
  );
}

function groupByDate(wars: WarSummary[]): { label: string; wars: WarSummary[] }[] {
  const groups: { label: string; wars: WarSummary[] }[] = [];
  for (const war of wars) {
    const d = war.completedAt ? new Date(war.completedAt) : null;
    const label = d
      ? d.toLocaleDateString(undefined, {
          weekday: "long",
          month: "numeric",
          day: "numeric",
        })
      : "Unknown date";
    const last = groups[groups.length - 1];
    if (last && last.label === label) last.wars.push(war);
    else groups.push({ label, wars: [war] });
  }
  return groups;
}

function sideScore(war: WarSummary, side: "winner" | "loser"): string {
  const total = war[side].total;
  if (total != null) return String(total);
  if (side === "winner" && war.pointMargin != null) return `+${war.pointMargin}`;
  if (side === "loser" && war.pointMargin != null) return "—";
  return "–";
}

export default function MatchHistoryList({
  wars,
  emptyText = "No completed wars yet.",
}: {
  wars: WarSummary[];
  emptyText?: string;
}) {
  if (!wars.length) {
    return <p className="py-6 text-center text-sm text-muted">{emptyText}</p>;
  }

  return (
    <div className="space-y-5">
      {groupByDate(wars).map((group) => (
        <section key={group.label}>
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">
            {group.label}
          </h3>
          <div className="space-y-2.5">
            {group.wars.map((war) => (
              <Link
                key={war.resultId}
                href={`/wars/${war.resultId}`}
                className="block rounded-2xl border border-border bg-panel/80 p-3 shadow-panel transition hover:border-accent/40 hover:bg-accent/5"
              >
                <div className="mb-2 flex items-center justify-between gap-2 text-[11px] text-muted">
                  <span>
                    {war.warType ?? "RT"} · {war.mode === "casual" ? "Casual" : "Ranked"}
                  </span>
                  <SrDelta delta={war.viewerSrDelta} />
                </div>

                <div className="space-y-2">
                  <div className="flex items-center gap-2">
                    <div className="grid min-w-0 flex-1 grid-cols-2 gap-x-2 gap-y-1 sm:grid-cols-5">
                      {war.winner.players.map((p, i) => (
                        <PlayerChip key={p.discordId ?? `w-${i}`} player={p} />
                      ))}
                    </div>
                    <span className="w-8 shrink-0 text-right text-lg font-semibold tabular-nums text-fg">
                      {sideScore(war, "winner")}
                    </span>
                  </div>
                  <div className="flex items-center gap-2">
                    <div className="grid min-w-0 flex-1 grid-cols-2 gap-x-2 gap-y-1 sm:grid-cols-5">
                      {war.loser.players.map((p, i) => (
                        <PlayerChip key={p.discordId ?? `l-${i}`} player={p} />
                      ))}
                    </div>
                    <span className="w-8 shrink-0 text-right text-lg font-semibold tabular-nums text-muted">
                      {sideScore(war, "loser")}
                    </span>
                  </div>
                </div>
              </Link>
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}
