# War Queue — companion web app

A Next.js (App Router) + TypeScript + Tailwind CSS front end for the war bot's queue,
profiles, and match flow. It talks to the bot's HTTP API over `fetch` with cookies for
session auth (Discord OAuth).

## Getting started

```bash
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

## Configuration

Create `web/.env.local` and point it at the backend API that serves `/auth/discord/login`,
`/api/me`, `/api/queue`, etc.:

```bash
NEXT_PUBLIC_API_BASE=http://localhost:8000
```

If unset, requests fall back to the Next.js server's own origin — fine for local
proxying, but the queue/profile pages will show a friendly error until a real backend
is reachable.

## Structure

```
app/
  page.tsx                      redirects to /q
  login/page.tsx                "Continue with Discord" entry point
  q/page.tsx                    3-column queue dashboard (My Group | Available | Invitations)
  q/invite/[code]/page.tsx      deep-link invite → join group
  me/page.tsx                   edit bio, linked accounts, view SR, supporter colors
  u/[discordId]/page.tsx        public profile
  match/[sessionId]/page.tsx    match lineups + Match/Group Chat tabs
components/
  QueueBoard.tsx                queue dashboard logic + layout
  GroupCard.tsx                 "My Group" column, including Invited/Undo
  InviteCard.tsx                incoming invitation (Accept/Deny)
  PlayerRow.tsx                 player row: avatar, name, rank icon on the right
  NavBar.tsx                    top navigation
lib/
  api.ts                        fetch helpers + types, all calls go through NEXT_PUBLIC_API_BASE
  ranks.ts                      rank key → /ranks/{rank}.webp + display label
public/ranks/                   rank icon assets (bronze, silver, gold, platinum, diamond, emerald, ruby, paragon, iron)
```

## Expected backend endpoints

The app is built against this contract; adjust `lib/api.ts` if the bot's API differs.

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/auth/discord/login` | Starts Discord OAuth (redirect, not JSON) |
| POST | `/auth/logout` | Clears the session |
| GET | `/api/me` | Current user profile + SR |
| PATCH | `/api/me` | Update bio / linked accounts / supporter colors |
| GET | `/api/users/:discordId` | Public profile |
| GET | `/api/queue` | `{ myGroup, available, invitations }` |
| POST | `/api/queue/join` / `/api/queue/leave` | Toggle your group's queue status |
| POST | `/api/groups/leave` | Leave your current group |
| POST | `/api/groups/invite` | Body `{ targetId }` — invite a player/group from Available |
| DELETE | `/api/groups/invite/:inviteId` | Undo a pending outgoing invite |
| POST | `/api/invitations/:id/accept` / `/deny` | Respond to an incoming invitation |
| GET | `/api/invite/:code` | Preview a deep-link invite |
| POST | `/api/invite/:code/join` | Join a group via deep link |
| GET | `/api/match/:sessionId` | Match lineups + `opponentsReady` flag |
| GET | `/api/match/:sessionId/chat?scope=match\|group` | Chat history |
| POST | `/api/match/:sessionId/chat` | Body `{ scope, text }` |

All requests are sent with `credentials: "include"`, so the API must set its session
cookie with the right `SameSite`/`Secure` attributes for cross-origin use in production.

## UX notes

- Every call-to-action for reaching out to another group/player says **Invite** — never
  "Join" or "Request".
- The **Opponents** panel on the match page stays hidden (replaced with a short waiting
  message) until the API reports `opponentsReady: true` with a non-empty roster.
- Outgoing invites sent from your group show up under **My Group → Invited**, each with
  an **Undo** button.
- The **Invitations** column only ever shows invites sent *to* you, with **Accept** /
  **Deny** actions.
