"use client";

import type { PlayerSummary } from "@/lib/api";
import { rankIconSrc, rankLabel } from "@/lib/ranks";

function initials(name: string): string {
  return name.trim().slice(0, 2).toUpperCase();
}

function Avatar({ url, name }: { url?: string | null; name: string }) {
  if (url) {
    // eslint-disable-next-line @next/next/no-img-element
    return (
      <img
        src={url}
        alt=""
        className="h-9 w-9 shrink-0 rounded-full object-cover ring-1 ring-border"
      />
    );
  }
  return (
    <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-panel text-xs font-semibold text-muted ring-1 ring-border">
      {initials(name)}
    </div>
  );
}

interface PlayerRowProps {
  player: PlayerSummary;
  action?: React.ReactNode;
  showSr?: boolean;
  /** Compact chip (default) vs bare inline row */
  variant?: "chip" | "inline";
  footer?: React.ReactNode;
}

export default function PlayerRow({
  player,
  action,
  showSr = false,
  variant = "chip",
  footer,
}: PlayerRowProps) {
  const icon = rankIconSrc(player.rank ?? "unranked");
  const meta = [
    player.role ? player.role : null,
    showSr && player.sr != null ? `${player.sr} SR` : null,
  ]
    .filter(Boolean)
    .join(" · ");

  const body = (
    <>
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 flex-1 items-center gap-3">
          <Avatar url={player.avatarUrl} name={player.displayName} />
          <div className="min-w-0">
            <p
              className="truncate text-[15px] font-semibold leading-tight tracking-tight text-fg"
              style={player.nameColor ? { color: player.nameColor } : undefined}
            >
              {player.displayName}
            </p>
            {meta ? (
              <p className="mt-0.5 truncate text-xs capitalize leading-tight text-muted">{meta}</p>
            ) : null}
          </div>
        </div>

        <div className="flex shrink-0 items-center gap-2 pt-0.5">
          {action}
          {icon && (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={icon}
              alt={rankLabel(player.rank)}
              title={rankLabel(player.rank)}
              className="h-8 w-8"
            />
          )}
        </div>
      </div>
      {footer ? <div className="mt-3">{footer}</div> : null}
    </>
  );

  if (variant === "inline") {
    return <div className="py-1.5">{body}</div>;
  }

  return (
    <div className="rounded-xl border border-border bg-elevated/90 px-3.5 py-3 shadow-[0_1px_0_0_rgba(255,255,255,0.03)_inset]">
      {body}
    </div>
  );
}
