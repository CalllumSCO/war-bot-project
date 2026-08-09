import type { Metadata } from "next";
import type { ReactNode } from "react";
import Link from "next/link";
import { rankIconSrc, rankLabel } from "@/lib/ranks";

export const metadata: Metadata = {
  title: "War Queue · How to use",
  description: "How to queue, form a group, play wars, and how Scrims Rating works.",
};

const SECTIONS = [
  { id: "general", label: "General info" },
  { id: "before", label: "Before joining" },
  { id: "joining", label: "Joining the queue" },
  { id: "group", label: "Finding a group" },
  { id: "discord", label: "Discord hub" },
  { id: "match", label: "Playing the match" },
  { id: "ranked", label: "Ranked system" },
  { id: "other", label: "Other topics" },
] as const;

const TIER_FLOORS: { key: string; floor: string }[] = [
  { key: "paragon", floor: "Special" },
  { key: "ruby", floor: "1520+" },
  { key: "emerald", floor: "1400+" },
  { key: "diamond", floor: "1280+" },
  { key: "platinum", floor: "1160+" },
  { key: "gold", floor: "1040+" },
  { key: "silver", floor: "920+" },
  { key: "bronze", floor: "800+" },
  { key: "iron", floor: "0+" },
];

function SectionNav() {
  return (
    <nav className="sticky top-16 hidden self-start lg:block">
      <p className="mb-2 text-xs font-medium uppercase tracking-wide text-muted">On this page</p>
      <ul className="space-y-1 text-sm">
        {SECTIONS.map((s) => (
          <li key={s.id}>
            <a href={`#${s.id}`} className="text-muted transition hover:text-fg">
              {s.label}
            </a>
          </li>
        ))}
      </ul>
    </nav>
  );
}

function H2({ id, children }: { id: string; children: ReactNode }) {
  return (
    <h2 id={id} className="scroll-mt-20 text-xl font-semibold text-fg">
      {children}
    </h2>
  );
}

function H3({ children }: { children: ReactNode }) {
  return <h3 className="mt-6 text-base font-semibold text-fg">{children}</h3>;
}

export default function QueueInfoPage() {
  return (
    <main className="mx-auto max-w-6xl px-4 py-10">
      <div className="mb-8 flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-xs font-medium uppercase tracking-wide text-muted">War Queue</p>
          <h1 className="mt-1 text-3xl font-semibold tracking-tight text-fg">How to use</h1>
          <p className="mt-2 max-w-2xl text-sm text-muted">
            MKWii 5v5 war matchmaking on the companion site and Discord. Same groups, same ratings —
            pick whichever surface is easier for you.
          </p>
        </div>
        <Link
          href="/q"
          className="rounded-xl border border-border bg-panel px-4 py-2 text-sm font-medium text-fg transition hover:border-accent hover:bg-accent/10"
        >
          ← Back to queue
        </Link>
      </div>

      <div className="grid gap-10 lg:grid-cols-[14rem_minmax(0,1fr)]">
        <SectionNav />

        <article className="max-w-3xl space-y-10 text-sm leading-relaxed text-muted">
          <section className="space-y-3">
            <H2 id="general">General info</H2>
            <p>
              War Queue connects teams looking for allies and opponents for Mario Kart Wii wars.
              You build a group of up to <strong className="text-fg">5 players</strong>, then look for a match on{" "}
              <strong className="text-fg">RT</strong> or <strong className="text-fg">CT</strong>, in{" "}
              <strong className="text-fg">ranked</strong> or <strong className="text-fg">casual</strong>{" "}
              mode.
            </p>
            <p>
              Ranked games update your <strong className="text-fg">Scrims Rating (SR).</strong> — Casual games do not change
              SR.
            </p>
          </section>

          <section className="space-y-3">
            <H2 id="before">Before joining</H2>
            <H3>Sign in with Discord</H3>
            <p>
              <Link href="/login" className="text-accent hover:underline">Sign in</Link> and
              authorize Discord. Your War Bot profile is the same account used on Discord.
            </p>
            <H3>Link your Lounge / FC</H3>
            <p>
              On Discord, run <code className="rounded bg-elevated px-1.5 py-0.5 text-fg">/profile link</code>{" "}
              so ratings and identity stay consistent across both surfaces. You can view your profile
              at <Link href="/me" className="text-accent hover:underline">/me</Link>. It's recommended to link your profile while 
              already online on <strong className="text-fg">Wiimmfi</strong> since it will autoparse your FC from the server.
            </p>
          </section>

          <section className="space-y-3">
            <H2 id="joining">Joining the queue</H2>
            <H3>Start a lobby</H3>
            <p>
              On <Link href="/q" className="text-accent hover:underline">/q</Link>, choose track type
              (RT/CT), your role (runner/bagger), and ranked or casual, then{" "}
              <strong className="text-fg">Join the queue lobby</strong>. That creates{" "}
              <strong className="text-fg">My Group</strong> — you are not visible to others yet.
            </p>
            <H3>Join queue vs Discord billboard</H3>
            <ul className="list-disc space-y-2 pl-5">
              <li>
                <strong className="text-fg">Join queue</strong> — appear in the web{" "}
                <em>Available</em> column so other web groups can invite or merge with you.
              </li>
              <li>
                <strong className="text-fg">Leave queue</strong> — Want to leave your current roster but keep playing? This drops you from the queue and allows you to start a new group immediately.
              </li>
              <li>
                <strong className="text-fg">Post to allies billboard</strong> — post the same group to
                Discord hub channels so Discord players can request to join as allies. This is separate
                from web Available.
              </li>
            </ul>
            <p>
              Icons on group cards show whether a group is filling on web, Discord, or both!
            </p>
          </section>

          <section className="space-y-3">
            <H2 id="group">Finding a group</H2>
            <p>
              Use the three columns: <strong className="text-fg">My Group</strong>,{" "}
              <strong className="text-fg">Available</strong>, and{" "}
              <strong className="text-fg">Invitations</strong>.
            </p>
            <ul className="list-disc space-y-2 pl-5">
              <li>Invite friends with a share link, or send invites from the Available column.</li> 
              <li>
                Accept invites from Invitations. Requesting to join a Discord-led hub group may send an ally
                request to that team&apos;s Discord instead of absorbing instantly.
              </li>
              <li>
                Looking for opponents still requires a full <strong className="text-fg">5/5</strong>{" "}
                lineup with a bagger. Allies can post to the billboard with a smaller roster to help fill up their squad.
              </li>
            </ul>
          </section>

          <section className="space-y-3">
            <H2 id="discord">Discord Hub</H2>
            <p>
              Team servers use hub channels (RT/CT × ranked/casual). Captains post with{" "}
              <code className="rounded bg-elevated px-1.5 py-0.5 text-fg">/queue post</code> or the
              web billboard button.
            </p>
            <ul className="list-disc space-y-2 pl-5">
              <li>
                <strong className="text-fg">Request Ally</strong> — ask to join a posted team.
              </li>
              <li>
                <strong className="text-fg">Challenge</strong> — challenge a full team looking for
                opponents.
              </li>
            </ul>
            <p>
              Accepted allies who aren&apos;t in the host Discord can get a one-time invite DM (see{" "}
              <a href="#other" className="text-accent hover:underline">Other topics</a>).
            </p>
          </section>

          <section className="space-y-3">
            <H2 id="match">Playing the match</H2>
            <p>
              When a match locks, Discord creates <code className="rounded bg-elevated px-1.5 py-0.5 text-fg">war-vs-*</code>{" "}
              channels and the web opens a match page. Finish with{" "}
              <code className="rounded bg-elevated px-1.5 py-0.5 text-fg">/war complete</code> (scores
              from Wiimmfi when possible).
            </p>
            <H3>Match chat colors (Discord)</H3>
            <div className="mt-3 space-y-3">
              <div className="rounded-xl border border-[#3B9EFF]/40 bg-[#3B9EFF]/10 px-4 py-3">
                <p className="font-medium text-[#7eb8ff]">Blue · match chat</p>
                <p className="mt-1">
                  Normal messages go to both teams (shared match chat), same as web match chat.
                </p>
              </div>
              <div className="rounded-xl border border-[#2ECC71]/40 bg-[#2ECC71]/10 px-4 py-3">
                <p className="font-medium text-[#5ee09a]">Green · group chat</p>
                <p className="mt-1">
                  Prefix with <code className="rounded bg-elevated px-1.5 py-0.5 text-fg">g:</code> or{" "}
                  <code className="rounded bg-elevated px-1.5 py-0.5 text-fg">.g </code> for team-only
                  messages. Example: <code className="rounded bg-elevated px-1.5 py-0.5 text-fg">g: hey let's go a luck track</code>
                  Players on the web will see 2 tabs in their chat, match and group. Those messages will be relayed to the Discord group chat channel in real time!
                </p>
              </div>
            </div>
          </section>

          <section className="space-y-3">
            <H2 id="ranked">Ranked system</H2>
            <H3>Scrims Rating (SR)</H3>
            <p>
              Ranked wars update SR via <strong className="text-fg">TrueSkill</strong>. Your display
              SR is roughly skill mean × 40. Each track × role lane is tracked separately (e.g. RT
              runner ≠ CT bagger).
            </p>
            <H3>Placements</H3>
            <p>
              You stay <strong className="text-fg">Unranked</strong> until you finish{" "}
              <strong className="text-fg">5</strong> ranked games in that track × role. After that
              your tier is revealed. Soft resets hide the tier again until you place out once more.
            </p>
            <H3>Tiers</H3>
            <p>Once revealed, tiers are based on SR floors:</p>
            <ul className="mt-3 grid gap-2 sm:grid-cols-2">
              {TIER_FLOORS.map(({ key, floor }) => (
                <li
                  key={key}
                  className="flex items-center gap-2 rounded-lg border border-border bg-panel px-3 py-2"
                >
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img src={rankIconSrc(key)!} alt="" className="h-7 w-7" />
                  <span className="text-fg">{rankLabel(key)}</span>
                  <span className="ml-auto text-xs text-muted">{floor}</span>
                </li>
              ))}
            </ul>
            <p className="mt-3 text-xs text-muted">
              Unranked stays until that lane finishes placements (or after a soft reset).
            </p>
            <H3>What moves your rating</H3>
            <ul className="list-disc space-y-2 pl-5">
              <li>Only ranked wars change SR.</li>
              <li>Win/loss of the war matters; individual performance can nudge updates slightly.</li>
              <li>Bagger updates are dampened relative to runners.</li>
            </ul>
          </section>

          <section className="space-y-3">
            <H2 id="other">Other topics</H2>
            <H3>Leave roster</H3>
            <p>
              Non-captains who leave a group (Leave roster / Leave) drop off that
              roster and immediately get a fresh solo lobby on the web — same as starting from the
              queue home screen — so you can invite or join another group right away.
            </p>
            <H3>Auto-invite allies</H3>
            <p>
              When an ally is accepted and they aren&apos;t in the host Discord yet, War Bot can DM a{" "}
              <strong className="text-fg">one-time, 1-hour</strong> invite. Joining grants the{" "}
              <strong className="text-fg">War Bot Ally</strong> role for{" "}
              <code className="rounded bg-elevated px-1.5 py-0.5 text-fg">#team-queue</code>. This is{" "}
              <strong className="text-fg">on by default</strong>; server admins toggle it with{" "}
              <code className="rounded bg-elevated px-1.5 py-0.5 text-fg">/config</code> → Auto-invite
              allies.
            </p>
            <H3>Config updates (admins)</H3>
            <p>
              After War Bot ships new server preferences, Discord admins can run{" "}
              <code className="rounded bg-elevated px-1.5 py-0.5 text-fg">/config action:Check for updates</code>
              . You&apos;ll see new toggles with their defaults, then{" "}
              <strong className="text-fg">Keep defaults</strong> or set each one — and refresh the Discord{" "}
              <code className="rounded bg-elevated px-1.5 py-0.5 text-fg">#how-to-use</code> guide when it
              changes.
            </p>
            <H3>Discord how-to channel</H3>
            <p>
              After <code className="rounded bg-elevated px-1.5 py-0.5 text-fg">/setup</code>, each
              team server gets a <code className="rounded bg-elevated px-1.5 py-0.5 text-fg">#how-to-use</code>{" "}
              channel with a short Discord-focused guide that also links here.
            </p>
          </section>
        </article>
      </div>
    </main>
  );
}
