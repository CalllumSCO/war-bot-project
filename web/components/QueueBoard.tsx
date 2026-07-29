"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  ApiError,
  createMatchRequest,
  createParty,
  getQueueState,
  inviteEntry,
  joinQueue,
  leaveGroup,
  leaveQueue,
  postToAlliesBillboard,
  requestAlly,
  respondToInvitation,
  subscribeEvents,
  undoInvite,
  updateParty,
  type AvailableEntry,
  type QueueState,
} from "@/lib/api";
import { rankIconSrc, rankLabel } from "@/lib/ranks";
import GroupCard from "./GroupCard";
import InviteCard from "./InviteCard";
import FillingSurfaceIcons from "./FillingSurfaceIcons";
import PlayerRow from "./PlayerRow";
import QueueStartScreen, { type StartChoices } from "./QueueStartScreen";

const POLL_INTERVAL_MS = 15000;

function SpyAvailableCard({ entry }: { entry: AvailableEntry }) {
  return (
    <div className="rounded-2xl border border-border bg-panel/60 p-3 shadow-panel">
      <div className="mb-2 flex items-center justify-between gap-2 px-0.5">
        <FillingSurfaceIcons surface={entry.fillingSurface} />
        {entry.lookingFor && (
          <p className="truncate text-right text-xs text-accent/90">{entry.lookingFor}</p>
        )}
      </div>
      <div className="flex flex-wrap items-center gap-1.5">
        {entry.players.map((player) => {
          const icon = rankIconSrc(player.rank ?? "unranked");
          return icon ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              key={player.discordId}
              src={icon}
              alt={rankLabel(player.rank)}
              title={rankLabel(player.rank)}
              className="h-8 w-8"
            />
          ) : (
            <span
              key={player.discordId}
              className="flex h-8 w-8 items-center justify-center rounded-full bg-elevated text-[10px] text-muted"
            >
              ?
            </span>
          );
        })}
      </div>
    </div>
  );
}

function AvailableCard({
  entry,
  busy,
  onAction,
  actionLabel = "Invite",
}: {
  entry: AvailableEntry;
  busy: boolean;
  onAction: (entry: AvailableEntry) => void;
  actionLabel?: string;
}) {
  return (
    <div className="rounded-2xl border border-border bg-panel/60 p-2.5 shadow-panel">
      <div className="mb-2 flex items-center justify-between gap-2 px-0.5">
        <FillingSurfaceIcons surface={entry.fillingSurface} />
        {entry.lookingFor && (
          <p className="truncate text-right text-xs text-accent/90">{entry.lookingFor}</p>
        )}
      </div>
      <div className="space-y-2">
        {entry.players.map((player) => (
          <PlayerRow key={player.discordId} player={player} showSr />
        ))}
      </div>
      <button
        type="button"
        onClick={() => onAction(entry)}
        disabled={busy}
        className="mt-2.5 w-full rounded-xl border border-border bg-elevated px-3 py-2 text-sm font-semibold text-fg transition hover:border-accent/50 hover:text-accent disabled:opacity-50"
      >
        {actionLabel}
      </button>
    </div>
  );
}

function ColumnShell({
  title,
  count,
  children,
  tabs,
}: {
  title: string;
  count?: number;
  children: React.ReactNode;
  tabs?: React.ReactNode;
}) {
  return (
    <section className="flex max-h-[min(70vh,36rem)] flex-col rounded-2xl border border-border bg-panel/80 shadow-panel">
      <header className="flex items-center justify-between px-4 pb-1 pt-4">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-muted">{title}</h2>
        {count != null && <span className="text-xs text-muted">{count}</span>}
      </header>
      {tabs}
      <div className="scroll-thin min-h-0 flex-1 space-y-2.5 overflow-y-auto p-3 pt-2">
        {children}
      </div>
    </section>
  );
}

export default function QueueBoard() {
  const router = useRouter();
  const [data, setData] = useState<QueueState | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [startError, setStartError] = useState<string | null>(null);
  const [queueActionBusy, setQueueActionBusy] = useState(false);
  const [startBusy, setStartBusy] = useState(false);
  const [busyInviteTargets, setBusyInviteTargets] = useState<Set<string>>(new Set());
  const [busyUndoIds, setBusyUndoIds] = useState<Set<string>>(new Set());
  const [busyInvitationIds, setBusyInvitationIds] = useState<Set<string>>(new Set());
  const [availableTab, setAvailableTab] = useState<"allies" | "opponents">("allies");
  const mountedRef = useRef(true);

  const fetchState = useCallback(
    async (showSpinner: boolean) => {
      if (showSpinner) setLoading(true);
      try {
        const state = await getQueueState();
        if (!mountedRef.current) return;
        setData(state);
        setError(null);
        if (!state.showOpponents && availableTab === "opponents") {
          setAvailableTab("allies");
        }
      } catch (err) {
        if (!mountedRef.current) return;
        if (err instanceof ApiError && err.status === 401) {
          router.push("/login");
          return;
        }
        setError((prev) => prev ?? "Couldn't load the queue right now.");
      } finally {
        if (mountedRef.current && showSpinner) setLoading(false);
      }
    },
    [router, availableTab]
  );

  useEffect(() => {
    mountedRef.current = true;
    fetchState(true);
    const interval = setInterval(() => fetchState(false), POLL_INTERVAL_MS);
    const unsub = subscribeEvents(() => {
      void fetchState(false);
    });
    return () => {
      mountedRef.current = false;
      clearInterval(interval);
      unsub();
    };
  }, [fetchState]);

  const withInviteBusy = (id: string, busy: boolean, set: typeof setBusyInviteTargets) => {
    set((prev) => {
      const next = new Set(prev);
      if (busy) next.add(id);
      else next.delete(id);
      return next;
    });
  };

  const handleStart = async (choices: StartChoices) => {
    setStartBusy(true);
    setStartError(null);
    try {
      await createParty({
        war_type: choices.warType,
        mode: choices.mode,
        role: choices.role === "bagger" ? "Bagger" : "Runner",
        search_time: "ASAP",
        ...(choices.entry === "queue"
          ? { join_queue: true }
          : {
              lobby_mode: choices.entry === "preview" ? "preview" : "friends",
              join_queue: false,
            }),
      });
      await fetchState(false);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        router.push("/login");
        return;
      }
      if (err instanceof ApiError && err.status === 403) {
        const detail = String(err.message || "").toLowerCase();
        setStartError(
          detail.includes("supporter")
            ? "Queue preview is a supporter perk."
            : "Link your Wii friend code in Discord with /profile link before queueing."
        );
      } else if (err instanceof ApiError && err.status === 409) {
        await fetchState(false);
      } else {
        setStartError("Couldn't start your lobby. Try again.");
      }
    } finally {
      setStartBusy(false);
    }
  };

  const handleAvailableAction = async (entry: AvailableEntry) => {
    if (data?.queueSpy) return;
    const key = entry.id;
    withInviteBusy(key, true, setBusyInviteTargets);
    try {
      if (entry.kind === "opponents") {
        await createMatchRequest(entry.id);
      } else if (entry.action === "request_join" && entry.warId) {
        const myRole =
          data?.myGroup?.members.find((m) => m.discordId === data.myGroup?.captainDiscordId)
            ?.role ?? data?.myGroup?.members[0]?.role;
        await requestAlly(entry.warId, myRole === "bagger" ? "Bagger" : "Runner");
        setError(null);
      } else {
        const target =
          entry.inviteTargetDiscordId ?? entry.players[0]?.discordId ?? "";
        await inviteEntry(target);
      }
      await fetchState(false);
    } catch (err) {
      if (entry.kind === "opponents") {
        setError("Couldn't send that match request. Try again.");
      } else if (entry.action === "request_join") {
        const detail =
          err instanceof ApiError
            ? String(err.message || "").replace(/\*\*/g, "").trim()
            : "";
        setError(detail || "Couldn't send that ally request. Try again.");
      } else {
        setError("Couldn't send that invite. Try again.");
      }
    } finally {
      withInviteBusy(key, false, setBusyInviteTargets);
    }
  };

  const handleUndoInvite = async (inviteId: string) => {
    withInviteBusy(inviteId, true, setBusyUndoIds);
    try {
      await undoInvite(inviteId);
      await fetchState(false);
    } catch {
      setError("Couldn't undo that invite. Try again.");
    } finally {
      withInviteBusy(inviteId, false, setBusyUndoIds);
    }
  };

  const handleRespond = async (id: string, accept: boolean) => {
    withInviteBusy(id, true, setBusyInvitationIds);
    try {
      await respondToInvitation(id, accept);
      await fetchState(false);
    } catch {
      setError(accept ? "Couldn't accept that invite." : "Couldn't deny that invite.");
    } finally {
      withInviteBusy(id, false, setBusyInvitationIds);
    }
  };

  const runQueueAction = async (action: () => Promise<unknown>) => {
    setQueueActionBusy(true);
    try {
      await action();
    } catch (err) {
      const detail =
        err instanceof ApiError ? String(err.message || "").replace(/\*\*/g, "").trim() : "";
      setError(detail || "That queue action failed. Try again.");
    } finally {
      try {
        await fetchState(false);
      } catch {
        /* ignore */
      }
      if (mountedRef.current) setQueueActionBusy(false);
    }
  };

  const patchParty = async (body: { war_type?: string; role?: string }) => {
    const id = data?.myGroup?.partyId;
    if (!id) return;
    setQueueActionBusy(true);
    try {
      await updateParty(id, body);
      await fetchState(false);
    } catch {
      setError("Couldn't update the group. Try again.");
    } finally {
      setQueueActionBusy(false);
    }
  };

  if (loading) {
    return (
      <main className="mx-auto max-w-6xl px-4 py-8">
        <div className="mx-auto max-w-md animate-pulse space-y-3">
          <div className="h-16 rounded-xl bg-elevated" />
          <div className="h-28 rounded-xl bg-elevated" />
          <div className="h-12 rounded-xl bg-elevated" />
        </div>
      </main>
    );
  }

  if (!data?.myGroup) {
    return (
      <QueueStartScreen busy={startBusy} error={startError} onStart={handleStart} />
    );
  }

  const showAvailable = Boolean(data?.showAvailable);
  const showOpponents = Boolean(data?.showOpponents);
  const queueSpy = Boolean(data?.queueSpy);
  const list =
    showOpponents && availableTab === "opponents"
      ? data?.opponents ?? []
      : data?.available ?? [];

  return (
    <main className="mx-auto max-w-6xl px-4 py-6">
      {error && (
        <div className="mb-4 flex items-center justify-between rounded-lg border border-danger/30 bg-danger/10 px-4 py-2.5 text-sm text-danger">
          <span>{error}</span>
          <button
            type="button"
            onClick={() => fetchState(true)}
            className="rounded-md border border-danger/40 px-2 py-1 text-xs font-medium transition hover:bg-danger/20"
          >
            Retry
          </button>
        </div>
      )}

      <div
        className={`grid grid-cols-1 items-start gap-4 ${
          showAvailable ? "md:grid-cols-3" : "md:grid-cols-2"
        }`}
      >
        <GroupCard
          group={data.myGroup}
          busyInviteIds={busyUndoIds}
          queueActionBusy={queueActionBusy}
          onUndoInvite={handleUndoInvite}
          onJoinQueue={() => runQueueAction(joinQueue)}
          onLeaveQueue={() => runQueueAction(leaveQueue)}
          onPostToAllies={() => runQueueAction(postToAlliesBillboard)}
          onLeaveGroup={() => runQueueAction(leaveGroup)}
          onChangeTrack={(warType) => patchParty({ war_type: warType })}
          onChangeRole={(role) =>
            patchParty({ role: role === "bagger" ? "Bagger" : "Runner" })
          }
        />

        {showAvailable ? (
          <ColumnShell
            title={queueSpy ? "Available · Preview" : "Available"}
            count={list.length}
            tabs={
              showOpponents ? (
                <div className="flex gap-1 border-b border-border px-3 py-2">
                  <button
                    type="button"
                    onClick={() => setAvailableTab("allies")}
                    className={`rounded-md px-2.5 py-1 text-xs font-medium ${
                      availableTab === "allies"
                        ? "bg-accent/15 text-accent"
                        : "text-muted hover:text-fg"
                    }`}
                  >
                    Allies
                  </button>
                  <button
                    type="button"
                    onClick={() => setAvailableTab("opponents")}
                    className={`rounded-md px-2.5 py-1 text-xs font-medium ${
                      availableTab === "opponents"
                        ? "bg-accent/15 text-accent"
                        : "text-muted hover:text-fg"
                    }`}
                  >
                    Opponents
                  </button>
                </div>
              ) : null
            }
          >
            {queueSpy ? (
              <p className="mb-2 px-0.5 text-xs text-muted">
                Supporter preview — ranks only. Join queue to interact and apply role filters.
              </p>
            ) : null}
            {!list.length ? (
              <p className="py-8 text-center text-sm text-muted">
                {availableTab === "opponents"
                  ? "No opponent groups right now."
                  : queueSpy
                    ? "No one else is queueing right now."
                    : data.myGroup.inQueue
                      ? data.myGroup.members.filter((m) => m.role === "runner").length >= 4 &&
                        !data.myGroup.members.some((m) => m.role === "bagger")
                        ? "Only bagger groups show when you have 4 runners (last slot)."
                        : "No one else is queueing right now."
                      : "Invite friends, then Join queue to appear here for others."}
              </p>
            ) : (
              <div className="flex flex-col gap-2.5">
                {list.map((entry) =>
                  queueSpy ? (
                    <SpyAvailableCard key={entry.id} entry={entry} />
                  ) : (
                    <AvailableCard
                      key={entry.id}
                      entry={entry}
                      busy={busyInviteTargets.has(entry.id)}
                      onAction={handleAvailableAction}
                      actionLabel={
                        entry.kind === "opponents"
                          ? "Request match"
                          : entry.action === "request_join"
                            ? "Request to join"
                            : "Invite"
                      }
                    />
                  )
                )}
              </div>
            )}
          </ColumnShell>
        ) : null}

        <ColumnShell title="Invitations" count={data.invitations.length}>
          {!data.invitations.length ? (
            <p className="py-8 text-center text-sm text-muted">No pending invitations.</p>
          ) : (
            <div className="flex flex-col gap-2.5">
              {data.invitations.map((invitation) => (
                <InviteCard
                  key={invitation.id}
                  invitation={invitation}
                  busy={busyInvitationIds.has(invitation.id)}
                  onAccept={(id) => handleRespond(id, true)}
                  onDeny={(id) => handleRespond(id, false)}
                />
              ))}
            </div>
          )}
        </ColumnShell>
      </div>
    </main>
  );
}
