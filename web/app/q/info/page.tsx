import type { Metadata } from "next";
import type { ReactNode } from "react";
import Link from "next/link";
import { rankIconSrc, rankLabel } from "@/lib/ranks";
import GuideSupporterSection from "@/components/GuideSupporterSection";
import PatronFooter from "@/components/PatronFooter";

export const metadata: Metadata = {
  title: "War Queue · Guide",
  description: "How to queue for MKWii wars and how ranked ratings, tiers, and team rank work.",
};

const PARTS = [
  {
    id: "how-to",
    label: "How to queue",
    sections: [
      { id: "before", label: "Before you start" },
      { id: "start", label: "Start a group" },
      { id: "available", label: "Go live & find allies" },
      { id: "discord", label: "Discord hub" },
      { id: "match", label: "During a match" },
      { id: "tips", label: "Tips & admin" },
    ],
  },
  {
    id: "about",
    label: "About the service",
    sections: [
      { id: "overview", label: "What this is" },
      { id: "modes", label: "Tracks & modes" },
      { id: "baggers", label: "Baggers & MKC seeding" },
      { id: "sr", label: "Scrims Rating (SR)" },
      { id: "placements", label: "Placements & tiers" },
      { id: "team-rank", label: "Team rank on cards" },
      { id: "team-mmr", label: "Lineup team SR" },
      { id: "updates", label: "What moves SR" },
    ],
  },
  {
    id: "supporters",
    label: "Supporter perks",
    sections: [{ id: "supporter-tiers", label: "Tiers & perks" }],
  },
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
      <p className="mb-3 text-xs font-medium uppercase tracking-wide text-muted">On this page</p>
      <div className="space-y-5">
        {PARTS.map((part) => (
          <div key={part.id}>
            <a
              href={`#${part.id}`}
              className="text-sm font-semibold text-fg transition hover:text-accent"
            >
              {part.label}
            </a>
            <ul className="mt-2 space-y-1 border-l border-border pl-3 text-sm">
              {part.sections.map((s) => (
                <li key={s.id}>
                  <a href={`#${s.id}`} className="text-muted transition hover:text-fg">
                    {s.label}
                  </a>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
    </nav>
  );
}

function PartHeader({ id, children }: { id: string; children: ReactNode }) {
  return (
    <div id={id} className="scroll-mt-20 border-b border-border pb-3 pt-2">
      <h2 className="text-2xl font-semibold tracking-tight text-fg">{children}</h2>
    </div>
  );
}

function H3({ id, children }: { id?: string; children: ReactNode }) {
  return (
    <h3 id={id} className="scroll-mt-20 text-base font-semibold text-fg">
      {children}
    </h3>
  );
}

function Callout({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="rounded-xl border border-border bg-panel px-4 py-3">
      <p className="font-medium text-fg">{title}</p>
      <div className="mt-1 text-muted">{children}</div>
    </div>
  );
}

export default function QueueInfoPage() {
  return (
    <main className="mx-auto max-w-6xl px-4 py-10">
      <div className="mb-8 flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-xs font-medium uppercase tracking-wide text-muted">War Queue</p>
          <h1 className="mt-1 text-3xl font-semibold tracking-tight text-fg">Guide</h1>
          <p className="mt-2 max-w-2xl text-sm text-muted">
            Two parts: a step-by-step queue walkthrough, and an overview of how ranked ratings and
            team rank work. Same account on web and Discord.
          </p>
        </div>
        <Link
          href="/q"
          className="rounded-xl border border-border bg-panel px-4 py-2 text-sm font-medium text-fg transition hover:border-accent hover:bg-accent/10"
        >
          ← Back to queue
        </Link>
      </div>

      <div className="mb-8 flex flex-wrap gap-2">
        {PARTS.map((part) => (
          <a
            key={part.id}
            href={`#${part.id}`}
            className="rounded-full border border-border bg-panel px-4 py-1.5 text-sm font-medium text-fg transition hover:border-accent hover:bg-accent/10"
          >
            {part.label}
          </a>
        ))}
      </div>

      <div className="grid gap-10 lg:grid-cols-[14rem_minmax(0,1fr)]">
        <SectionNav />

        <div className="max-w-3xl space-y-14 text-sm leading-relaxed text-muted">
          {/* ── Part 1: How to queue ── */}
          <div className="space-y-10">
            <PartHeader id="how-to">How to queue</PartHeader>

            <section className="space-y-3">
              <H3 id="before">Before you start</H3>
              <p>
                <Link href="/login" className="text-accent hover:underline">
                  Sign in with Discord
                </Link>{" "}
                — your War Bot profile is the same account on web and in team servers.
              </p>
              <p>
                Link your Lounge / FC on Discord with{" "}
                <code className="rounded bg-elevated px-1.5 py-0.5 text-fg">/profile link</code>.
                Ratings and identity stay in sync. Linking while you are online on{" "}
                <strong className="text-fg">Wiimmfi</strong> can auto-parse your FC. View stats at{" "}
                <Link href="/me" className="text-accent hover:underline">
                  /me
                </Link>
                .
              </p>
            </section>

            <section className="space-y-3">
              <H3 id="start">Start a group</H3>
              <p>
                On <Link href="/q" className="text-accent hover:underline">/q</Link>, pick track type
                (RT or CT), runner or bagger, ranked or casual, then{" "}
                <strong className="text-fg">Join the queue lobby</strong> (or{" "}
                <strong className="text-fg">Join with friends</strong> to fill a roster before going
                live).
              </p>
              <p>
                That creates <strong className="text-fg">My Group</strong> — up to five players. You
                are not visible to others until the captain joins the queue or posts to a billboard.
              </p>
            </section>

            <section className="space-y-3">
              <H3 id="available">Go live & find allies</H3>
              <p>The queue board has three columns:</p>
              <ul className="list-disc space-y-2 pl-5">
                <li>
                  <strong className="text-fg">My Group</strong> — your roster, captain controls,
                  pending outbound invites.
                </li>
                <li>
                  <strong className="text-fg">Available</strong> — other groups looking for allies or
                  opponents (depends on your search mode).
                </li>
                <li>
                  <strong className="text-fg">Invitations</strong> — inbound invites and ally
                  requests to accept or decline.
                </li>
              </ul>
              <Callout title="Join queue">
                Captain action. Puts your group in the web <em>Available</em> column so other web
                groups can invite or merge. Web-only groups that sit idle with no roster changes for
                an hour are soft-hidden; the captain can restore visibility from the banner on /q.
              </Callout>
              <Callout title="Post to allies billboard">
                Posts the same group to Discord hub channels so Discord players can request to join.
                Separate from web Available — icons on cards show web, Discord, or both.
              </Callout>
              <Callout title="Leave queue / Leave roster">
                Captains <strong className="text-fg">Leave queue</strong> to stop searching but keep
                the group. Non-captains who leave get a fresh solo lobby immediately so they can join
                another roster.
              </Callout>
              <p>
                Share your invite link, invite from Available, or accept inbound invites. Discord-led
                hub groups may send an ally request to their server instead of merging instantly.
              </p>
              <p>
                <strong className="text-fg">Looking for opponents</strong> needs a full 5/5 lineup
                with a bagger. Ally search can post with a smaller roster to fill the squad first.
              </p>
            </section>

            <section className="space-y-3">
              <H3 id="discord">Discord hub</H3>
              <p>
                Team servers use hub channels (RT/CT × ranked/casual). Captains post with{" "}
                <code className="rounded bg-elevated px-1.5 py-0.5 text-fg">/queue post</code> or the
                web billboard button. Discord-origin parties on the allies board are not idle-hidden.
              </p>
              <ul className="list-disc space-y-2 pl-5">
                <li>
                  <strong className="text-fg">Request Ally</strong> — ask to join a posted team as
                  runner or bagger.
                </li>
                <li>
                  <strong className="text-fg">Challenge</strong> — challenge a full team looking for
                  opponents (ranked LFO cards show team tier only, not the team name).
                </li>
              </ul>
            </section>

            <section className="space-y-3">
              <H3 id="match">During a match</H3>
              <p>
                When a match locks, Discord creates{" "}
                <code className="rounded bg-elevated px-1.5 py-0.5 text-fg">war-vs-*</code> channels
                and the web opens a match page. Finish with{" "}
                <code className="rounded bg-elevated px-1.5 py-0.5 text-fg">/war complete</code>{" "}
                (scores from Wiimmfi when possible).
              </p>
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
                    Prefix with <code className="rounded bg-elevated px-1.5 py-0.5 text-fg">g:</code>{" "}
                    or <code className="rounded bg-elevated px-1.5 py-0.5 text-fg">.g </code> for
                    team-only messages. Web match pages have Match and Group tabs; group messages
                    relay to Discord in real time.
                  </p>
                </div>
              </div>
            </section>

            <section className="space-y-3">
              <H3 id="tips">Tips & admin</H3>
              <p>
                <strong className="text-fg">Auto-invite allies</strong> — when an ally is accepted and
                not in the host Discord, War Bot can DM a one-time 1-hour invite and grant the{" "}
                <strong className="text-fg">War Bot Ally</strong> role. On by default; admins toggle
                with <code className="rounded bg-elevated px-1.5 py-0.5 text-fg">/config</code>.
              </p>
              <p>
                After bot updates, admins run{" "}
                <code className="rounded bg-elevated px-1.5 py-0.5 text-fg">
                  /config action:Check for updates
                </code>{" "}
                to review new toggles and refresh the Discord{" "}
                <code className="rounded bg-elevated px-1.5 py-0.5 text-fg">#how-to-use</code>{" "}
                channel (created by <code className="rounded bg-elevated px-1.5 py-0.5 text-fg">/setup</code>
                ).
              </p>
            </section>
          </div>

          {/* ── Part 2: About the service ── */}
          <div className="space-y-10">
            <PartHeader id="about">About the service</PartHeader>

            <section className="space-y-3">
              <H3 id="overview">What this is</H3>
              <p>
                War Queue is matchmaking for Mario Kart Wii <strong className="text-fg">5v5 wars</strong>.
                You form a group, find allies or an opponent, play the war, and submit results. The
                companion site and Discord share the same queue, ratings, and match flow — use whichever
                surface is easier.
              </p>
            </section>

            <section className="space-y-3">
              <H3 id="modes">Tracks & modes</H3>
              <ul className="list-disc space-y-2 pl-5">
                <li>
                  <strong className="text-fg">RT</strong> — regular tracks.{" "}
                  <strong className="text-fg">CT</strong> — custom tracks. Ratings are separate per
                  track.
                </li>
                <li>
                  <strong className="text-fg">Ranked</strong> — updates Scrims Rating (SR). Opponent
                  cards in ranked LFO hide team names and show tier only.
                </li>
                <li>
                  <strong className="text-fg">Casual</strong> — no SR changes; rosters and lineups
                  are visible on cards.
                </li>
                <li>
                  Each player has a <strong className="text-fg">runner</strong> or{" "}
                  <strong className="text-fg">bagger</strong> role per track. Your RT runner rating
                  is independent of your CT bagger rating.
                </li>
              </ul>
            </section>

            <section className="space-y-3">
              <H3 id="baggers">Baggers</H3>
              <p>
                Every 5v5 war roster needs at least <strong className="text-fg">one bagger</strong>.
                You choose runner or bagger when you join a queue lobby. Baggers have their own SR
                lane (RT bagger and CT bagger are separate from runner ratings).
              </p>
              <H3>Roster rules</H3>
              <ul className="list-disc space-y-2 pl-5">
                <li>
                  <strong className="text-fg">Looking for opponents</strong> requires a full 5/5
                  roster with a bagger.
                </li>
                <li>
                  If a team already has <strong className="text-fg">4 runners</strong>, the last
                  open slot is <strong className="text-fg">bagger only</strong>.
                </li>
                <li>
                  If a team already has a bagger, new allies must join as{" "}
                  <strong className="text-fg">runners</strong>.
                </li>
                <li>
                  Allies can fill either role when the host still has flexible slots — the rules
                  above kick in as the roster fills.
                </li>
              </ul>
              <H3>Linking MKCentral (baggers)</H3>
              <p>
                Bagger seeding uses your <strong className="text-fg">MKCentral</strong> tournament
                history. When you link your friend code (
                <code className="rounded bg-elevated px-1.5 py-0.5 text-fg">/profile link</code> on
                Discord or <Link href="/me" className="text-accent hover:underline">/me</Link> on
                the web), the bot may attach an MKCentral profile if:
              </p>
              <ul className="list-disc space-y-2 pl-5">
                <li>Your friend code matches an MKCentral registry player, and</li>
                <li>
                  That MKCentral account is linked to the <strong className="text-fg">same Discord</strong>{" "}
                  you sign in with.
                </li>
              </ul>
              <p>
                You can also paste your MKCentral profile URL on{" "}
                <Link href="/me" className="text-accent hover:underline">/me</Link> if auto-link
                did not run. Anti-alt: MKCentral URLs are only attached when Discord ownership
                matches — you cannot claim someone else&apos;s registry page.
              </p>
              <H3>Bagger seeding</H3>
              <p>
                If MKCentral is linked, the bot can <strong className="text-fg">seed</strong> your
                bagger SR from verified <strong className="text-fg">5v5</strong> tournament
                placements — especially events where you registered on the{" "}
                <strong className="text-fg">bagger clause</strong>. Top finishes push the estimate
                up; deep finishes push it down (roughly centered around 1000 SR).
              </p>
              <Callout title="Seeding ≠ ranked">
                A seed sets your <strong className="text-fg">hidden</strong> starting point for the
                bagger lane on that track. You still show{" "}
                <strong className="text-fg">Unranked (0/5)</strong> until you finish{" "}
                <strong className="text-fg">5 ranked bagger wars</strong> in RT or CT — same placement
                rule as runners. Seeding does not skip placements or reveal your tier early.
              </Callout>
              <p>
                RT and CT bagger seeds are independent — strong MKC RT results seed RT bagger; CT is
                seeded separately when CT placement data exists.
              </p>
              <p>
                In ranked wars, bagger SR updates are <strong className="text-fg">dampened</strong>{" "}
                compared to runners (see{" "}
                <a href="#updates" className="text-accent hover:underline">
                  What moves SR
                </a>
                ).
              </p>
            </section>

            <section className="space-y-3">
              <H3 id="sr">Scrims Rating (SR)</H3>
              <p>
                Ranked wars update SR. Display SR
                is roughly skill mean × 40. The system tracks uncertainty — early games move you more;
                established players move slightly less.
              </p>
              <p>
                Everyone who played in the war (core roster and allies) receives a personal SR update
                for that track × role lane.
              </p>
            </section>

            <section className="space-y-3">
              <H3 id="placements">Placements & tiers</H3>
              <p>
                You stay <strong className="text-fg">Unranked</strong> until you finish{" "}
                <strong className="text-fg">5</strong> ranked games in that track × role. After that
                your tier is revealed. A soft reset hides the tier again until you place out once
                more.
              </p>
              <p>Once revealed, tiers follow SR floors:</p>
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
            </section>

            <section className="space-y-3">
              <H3 id="team-rank">Team rank on cards</H3>
              <p>
                When you browse ranked opponents (web or Discord), each card shows a{" "}
                <strong className="text-fg">team rank</strong> — the average SR of everyone currently
                on that roster, mapped to a tier icon (e.g. Silver, Gold). This is a{" "}
                <strong className="text-fg">live snapshot</strong> for matchmaking visibility, not a
                stored team rating.
              </p>
              <ul className="list-disc space-y-2 pl-5">
                <li>Unranked players still count toward the average using their hidden SR.</li>
                <li>Hub allies who joined mid-search are included in the lineup average for display.</li>
              </ul>
            </section>

            <section className="space-y-3">
              <H3 id="team-mmr">Lineup team SR</H3>
              <p>
                When the exact same <strong className="text-fg">five core players</strong> (no allies)
                finish ranked wars together, that lineup earns its own{" "}
                <strong className="text-fg">lineup team SR</strong> — separate from anyone&apos;s
                personal SR. Swap one player and it&apos;s a different lineup with its own counter.
              </p>
              <ul className="list-disc space-y-2 pl-5">
                <li>
                  <strong className="text-fg">RT and CT are separate</strong> — the same five have
                  one lineup rating for RT wars and another for CT.
                </li>
                <li>
                  After <strong className="text-fg">5 ranked wars</strong> together on that track,
                  the lineup rating is <strong className="text-fg">revealed</strong> on My Group and
                  your profile. Until then you may see <strong className="text-fg">(n/5)</strong>{" "}
                  on your group card.
                </li>
                <li>
                  <strong className="text-fg">Ranked LFO</strong> still shows the anonymous average-SR
                  tier icon — opponents don&apos;t see your lineup SR until a match locks.
                </li>
                <li>
                  <strong className="text-fg">Casual LFO</strong> can show the seeded lineup tier on
                  opponent cards once that five has revealed their lineup SR.
                </li>
                <li>
                  Hub allies never count toward lineup identity or lineup SR updates, but still get
                  personal SR.
                </li>
              </ul>
            </section>

            <section className="space-y-3">
              <H3 id="updates">What moves SR</H3>
              <ul className="list-disc space-y-2 pl-5">
                <li>Only ranked wars change SR. Casual wars do not.</li>
                <li>Win or loss of the war is primary; margin of victory can nudge the update.</li>
                <li>Individual placement within the war can slightly amplify or dampen your delta.</li>
                <li>Bagger SR updates are dampened relative to runners.</li>
              </ul>
            </section>
          </div>

          <GuideSupporterSection />
          <PatronFooter />
        </div>
      </div>
    </main>
  );
}
