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
import PendingOutboundCard from "./PendingOutboundCard";
import PlayerRow from "./PlayerRow";
import QueueStartScreen, { type StartChoices } from "./QueueStartScreen";

const POLL_INTERVAL_MS = 15000;
const POLL_INTERVAL_SSE_DOWN_MS = 3000;
const SSE_DEBOUNCE_MS = 400;

function SpyAvailableCard({ entry }: { entry: AvailableEntry }) {
  return (
    <div className="rounded-2xl border border-border bg-panel/60 p-3 shadow-panel">
      <div className="mb-2 flex items-center justify-between gap-2 px-0.5">
        <FillingSurfaceIcons surface={entry.fillingSurface} />
      </div>
      <div className="flex flex-wrap items-center justify-center gap-1.5">
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

function RankedOpponentCard({
  entry,
  busy,
  onChallenge,
}: {
  entry: AvailableEntry;
  busy: boolean;
  onChallenge: (entry: AvailableEntry) => void;
}) {
  const icon = rankIconSrc(entry.teamAvgRank ?? "unranked");
  return (
    <div className="rounded-2xl border border-border bg-panel/60 p-3 shadow-panel">
      <div className="mb-3 flex justify-center py-2">
        {icon ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={icon}
            alt={rankLabel(entry.teamAvgRank)}
            title={rankLabel(entry.teamAvgRank)}
            className="h-16 w-16"
          />
        ) : (
          <span className="text-sm text-muted">?</span>
        )}
      </div>
      <button
        type="button"
        onClick={() => onChallenge(entry)}
        disabled={busy}
        className="w-full rounded-xl border border-border bg-elevated px-3 py-2 text-sm font-semibold text-fg transition hover:border-accent/50 hover:text-accent disabled:opacity-50"
      >
        Challenge
      </button>
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
}: {
  title: string;
  count?: number;
  children: React.ReactNode;
}) {
  return (
    <section className="flex max-h-[min(70vh,36rem)] flex-col rounded-2xl border border-border bg-panel/80 shadow-panel">
      <header className="flex items-center justify-between px-4 pb-1 pt-4">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-muted">{title}</h2>
        {count != null && <span className="text-xs text-muted">{count}</span>}
      </header>
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
  const mountedRef = useRef(true);
  const sseDebounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pollIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const lastFetchAtRef = useRef(0);

  const fetchState = useCallback(
    async (showSpinner: boolean) => {
      if (showSpinner) setLoading(true);
      try {
        const state = await getQueueState();
        if (!mountedRef.current) return;
        lastFetchAtRef.current = Date.now();
        setData(state);
        setError(null);
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
    [router]
  );

  const scheduleFetch = useCallback(
    (showSpinner: boolean, debounceMs = 0) => {
      if (debounceMs <= 0) {
        void fetchState(showSpinner);
        return;
      }
      if (sseDebounceRef.current) clearTimeout(sseDebounceRef.current);
      sseDebounceRef.current = setTimeout(() => {
        // Skip if we just refreshed (e.g. manual invite refresh + SSE bump).
        if (Date.now() - lastFetchAtRef.current < SSE_DEBOUNCE_MS) return;
        void fetchState(showSpinner);
      }, debounceMs);
    },
    [fetchState]
  );

  useEffect(() => {
    mountedRef.current = true;
    fetchState(true);

    const startPoll = (ms: number) => {
      if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
      pollIntervalRef.current = setInterval(() => fetchState(false), ms);
    };
    startPoll(POLL_INTERVAL_MS);

    const unsub = subscribeEvents(
      (eventType) => {
        // Ignore connect handshake + match chat; refresh for queue/party/hub bumps.
        if (eventType === "connected" || eventType === "chat") return;
        scheduleFetch(false, SSE_DEBOUNCE_MS);
      },
      () => {
        // SSE unhealthy — fall back to faster polling until reconnect.
        startPoll(POLL_INTERVAL_SSE_DOWN_MS);
      }
    );
    return () => {
      mountedRef.current = false;
      if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
      if (sseDebounceRef.current) clearTimeout(sseDebounceRef.current);
      unsub();
    };
  }, [fetchState, scheduleFetch]);

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
            : "Link your Wii friend code on your Profile page before queueing."
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
        const warId = entry.warId ?? entry.id;
        await createMatchRequest(warId);
      } else if (entry.action === "request_join" && entry.warId) {
        const myRole =
          data?.myGroup?.members.find((m) => m.discordId === data.myGroup?.captainDiscordId)
            ?.role ?? data?.myGroup?.members[0]?.role;
        await requestAlly(entry.warId, myRole === "bagger" ? "Bagger" : "Runner");
        setError(null);
      } else {
        const target =
          entry.inviteTargetDiscordId ?? entry.players[0]?.discordId ?? "";
        await inviteEntry(target, data?.myGroup?.partyId);
      }
      await fetchState(false);
    } catch (err) {
      if (entry.kind === "opponents") {
        setError("Couldn't send that challenge. Try again.");
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
  const seekingOpponents = showOpponents && !queueSpy;
  const rankedMode = (data.myGroup.mode ?? "ranked").toLowerCase() === "ranked";
  const list = seekingOpponents || (queueSpy && showOpponents)
    ? data?.opponents ?? []
    : data?.available ?? [];
  const availableTitle = queueSpy
    ? "Available · Preview"
    : seekingOpponents
      ? "Opponents"
      : "Available";

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
        <div className="flex min-w-0 flex-col gap-2.5">
          <GroupCard
            group={data.myGroup}
            queueActionBusy={queueActionBusy}
            onJoinQueue={() => runQueueAction(() => joinQueue(data.myGroup?.partyId))}
            onLeaveQueue={() => runQueueAction(() => leaveQueue(data.myGroup?.partyId))}
            onPostToAllies={() =>
              runQueueAction(() => postToAlliesBillboard(data.myGroup?.partyId))
            }
            onLeaveGroup={() => runQueueAction(leaveGroup)}
            onChangeTrack={(warType) => patchParty({ war_type: warType })}
            onChangeRole={(role) =>
              patchParty({ role: role === "bagger" ? "Bagger" : "Runner" })
            }
          />
          {(data.myGroup.pendingOutbound ?? []).map((pending) => (
            <PendingOutboundCard
              key={pending.id}
              pending={pending}
              busy={busyUndoIds.has(pending.id)}
              onUndo={handleUndoInvite}
            />
          ))}
        </div>

        {showAvailable ? (
          <ColumnShell title={availableTitle} count={list.length}>
            {queueSpy ? (
              <p className="mb-2 px-0.5 text-xs text-muted">
                Supporter preview — ranks only. Join queue to interact and apply role filters.
              </p>
            ) : null}
            {!list.length ? (
              <p className="py-8 text-center text-sm text-muted">
                {seekingOpponents
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
                {list.map((entry) => {
                  if (queueSpy) {
                    return <SpyAvailableCard key={entry.id} entry={entry} />;
                  }
                  if (seekingOpponents && (entry.anonymous || rankedMode)) {
                    return (
                      <RankedOpponentCard
                        key={entry.id}
                        entry={entry}
                        busy={busyInviteTargets.has(entry.id)}
                        onChallenge={handleAvailableAction}
                      />
                    );
                  }
                  return (
                    <AvailableCard
                      key={entry.id}
                      entry={entry}
                      busy={busyInviteTargets.has(entry.id)}
                      onAction={handleAvailableAction}
                      actionLabel={
                        entry.kind === "opponents"
                          ? "Challenge"
                          : entry.action === "request_join"
                            ? "Request to join"
                            : "Invite"
                      }
                    />
                  );
                })}
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
