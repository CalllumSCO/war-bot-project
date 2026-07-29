"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  ApiError,
  getMatchMessages,
  getMatchSession,
  sendMatchMessage,
  subscribeEvents,
  type ChatMessage,
  type ChatScope,
  type MatchSession,
} from "@/lib/api";
import PlayerRow from "@/components/PlayerRow";

const POLL_INTERVAL_MS = 5000;

type Tab = "match" | "group";

function LineupPanel({ title, players }: { title: string; players: MatchSession["yourTeam"] }) {
  return (
    <div className="rounded-xl border border-border bg-elevated p-3">
      <p className="mb-1 px-0.5 text-xs font-medium uppercase tracking-wide text-muted">
        {title}
      </p>
      {!players.length ? (
        <p className="py-3 text-center text-sm text-muted">No players yet.</p>
      ) : (
        <div className="divide-y divide-border">
          {players.map((player) => (
            <PlayerRow key={player.discordId} player={player} showSr />
          ))}
        </div>
      )}
    </div>
  );
}

function ChatPanel({ sessionId, scope }: { sessionId: string; scope: ChatScope }) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [text, setText] = useState("");
  const [sending, setSending] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const mountedRef = useRef(true);
  const bottomRef = useRef<HTMLDivElement | null>(null);

  const fetchMessages = useCallback(async () => {
    try {
      const msgs = await getMatchMessages(sessionId, scope);
      if (mountedRef.current) setMessages(msgs);
    } catch {
      // silently retry on next poll
    } finally {
      if (mountedRef.current) setLoaded(true);
    }
  }, [sessionId, scope]);

  useEffect(() => {
    mountedRef.current = true;
    setLoaded(false);
    fetchMessages();
    const interval = setInterval(fetchMessages, POLL_INTERVAL_MS);
    const unsub = subscribeEvents((eventType, payload) => {
      if (eventType !== "chat") return;
      const msg = payload as { session_id?: string; channel?: string };
      if (msg.session_id && msg.session_id !== sessionId) return;
      if (msg.channel && msg.channel !== scope) return;
      void fetchMessages();
    });
    return () => {
      mountedRef.current = false;
      clearInterval(interval);
      unsub();
    };
  }, [fetchMessages, sessionId, scope]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: "end" });
  }, [messages]);

  const handleSend = async () => {
    const trimmed = text.trim();
    if (!trimmed) return;
    setSending(true);
    try {
      await sendMatchMessage(sessionId, scope, trimmed);
      setText("");
      await fetchMessages();
    } catch {
      // leave text in place so the player can retry
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="flex h-full flex-col rounded-xl border border-border bg-elevated">
      <div className="scroll-thin flex-1 space-y-2 overflow-y-auto p-3">
        {!loaded ? (
          <p className="text-sm text-muted">Loading messages…</p>
        ) : !messages.length ? (
          <p className="py-6 text-center text-sm text-muted">No messages yet. Say hi!</p>
        ) : (
          messages.map((msg) => (
            <div key={msg.id} className="text-sm">
              <span className="font-medium text-fg">{msg.authorName ?? msg.author_name ?? "Unknown"}</span>
              <span className="ml-2 text-muted">{msg.text ?? msg.body ?? ""}</span>
            </div>
          ))
        )}
        <div ref={bottomRef} />
      </div>
      <div className="flex items-center gap-2 border-t border-border p-2.5">
        <input
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              handleSend();
            }
          }}
          placeholder="Message"
          className="flex-1 rounded-lg border border-border bg-bg px-3 py-1.5 text-sm text-fg placeholder:text-muted focus:border-accent focus:outline-none"
        />
        <button
          type="button"
          onClick={handleSend}
          disabled={sending || !text.trim()}
          className="rounded-lg bg-accent px-3 py-1.5 text-sm font-medium text-white transition hover:bg-accent-hover disabled:opacity-50"
        >
          Send
        </button>
      </div>
    </div>
  );
}

export default function MatchClient({ sessionId }: { sessionId: string }) {
  const router = useRouter();
  const [session, setSession] = useState<MatchSession | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("match");
  const mountedRef = useRef(true);

  const fetchSession = useCallback(
    async (showSpinner: boolean) => {
      if (showSpinner) setLoading(true);
      try {
        const data = await getMatchSession(sessionId);
        if (!mountedRef.current) return;
        setSession(data);
        setError(null);
      } catch (err) {
        if (!mountedRef.current) return;
        if (err instanceof ApiError && err.status === 401) {
          router.push("/login");
          return;
        }
        setError("Couldn't load this match right now.");
      } finally {
        if (mountedRef.current && showSpinner) setLoading(false);
      }
    },
    [router, sessionId]
  );

  useEffect(() => {
    mountedRef.current = true;
    fetchSession(true);
    const interval = setInterval(() => fetchSession(false), POLL_INTERVAL_MS);
    return () => {
      mountedRef.current = false;
      clearInterval(interval);
    };
  }, [fetchSession]);

  if (loading) {
    return (
      <main className="mx-auto max-w-4xl px-4 py-8">
        <p className="text-sm text-muted">Loading match…</p>
      </main>
    );
  }

  if (error || !session) {
    return (
      <main className="mx-auto max-w-4xl px-4 py-8">
        <div className="flex items-center justify-between rounded-lg border border-danger/30 bg-danger/10 px-4 py-2.5 text-sm text-danger">
          <span>{error ?? "This match isn't available."}</span>
          <button
            type="button"
            onClick={() => fetchSession(true)}
            className="rounded-md border border-danger/40 px-2 py-1 text-xs font-medium transition hover:bg-danger/20"
          >
            Retry
          </button>
        </div>
      </main>
    );
  }

  const opponentsVisible = session.opponentsReady && session.opponents.length > 0;

  return (
    <main className="mx-auto max-w-4xl px-4 py-6">
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-lg font-semibold text-fg">
          {session.mapOrMode ?? "Match"}
        </h1>
        <span className="rounded-full border border-border bg-elevated px-2.5 py-0.5 text-xs capitalize text-muted">
          {session.status}
        </span>
      </div>

      <div className="mb-4 flex gap-1 rounded-lg border border-border bg-elevated p-1 text-sm">
        <button
          type="button"
          onClick={() => setTab("match")}
          className={`flex-1 rounded-md px-3 py-1.5 font-medium transition ${
            tab === "match" ? "bg-accent text-white" : "text-muted hover:text-fg"
          }`}
        >
          Match
        </button>
        <button
          type="button"
          onClick={() => setTab("group")}
          className={`flex-1 rounded-md px-3 py-1.5 font-medium transition ${
            tab === "group" ? "bg-accent text-white" : "text-muted hover:text-fg"
          }`}
        >
          Group Chat
        </button>
      </div>

      {tab === "match" ? (
        <div className="space-y-4">
          <div className={`grid grid-cols-1 gap-3 ${opponentsVisible ? "md:grid-cols-2" : ""}`}>
            <LineupPanel title="Your team" players={session.yourTeam} />
            {opponentsVisible ? (
              <LineupPanel title="Opponents" players={session.opponents} />
            ) : (
              <div className="flex items-center justify-center rounded-xl border border-dashed border-border p-6 text-center text-sm text-muted md:col-span-1">
                Opponents will appear here once the match is ready.
              </div>
            )}
          </div>
          <div className="h-72">
            <ChatPanel sessionId={sessionId} scope="match" />
          </div>
        </div>
      ) : (
        <div className="h-96">
          <ChatPanel sessionId={sessionId} scope="group" />
        </div>
      )}
    </main>
  );
}
