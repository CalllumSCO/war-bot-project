import type { FavoriteLane } from "./favoriteLane";
import type { RankKey } from "./ranks";

export const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

const TOKEN_KEY = "warbot_jwt";
const ME_CACHE_KEY = "warbot_me";

export type CachedMe = {
  discord_id: number | string;
  display_name?: string | null;
  displayName?: string | null;
  avatar?: string | null;
  avatarUrl?: string | null;
  supporter?: boolean;
};

const ME_FETCHED_AT_KEY = "warbot_me_fetched_at";
const ME_TTL_MS = 60_000;

function _cacheMeFromProfile(me: MeProfile): CachedMe {
  const cached: CachedMe = {
    discord_id: me.discord_id,
    display_name: me.display_name ?? me.displayName,
    avatar: me.avatar ?? me.avatarUrl,
    supporter: Boolean(me.supporter),
  };
  setCachedMe(cached);
  if (typeof window !== "undefined") {
    window.localStorage.setItem(ME_FETCHED_AT_KEY, String(Date.now()));
  }
  return cached;
}

/** Return cached /me when fresh; otherwise refresh (NavBar / start screen). */
export async function getMeCached(
  maxAgeMs: number = ME_TTL_MS,
  init?: RequestInit
): Promise<MeProfile> {
  if (typeof window !== "undefined") {
    const fetchedAt = Number(window.localStorage.getItem(ME_FETCHED_AT_KEY) || 0);
    const cached = getCachedProfile();
    if (cached && fetchedAt && Date.now() - fetchedAt < maxAgeMs) {
      return cached;
    }
  }
  return getMe(init);
}

export function getStoredToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export function setStoredToken(token: string | null): void {
  if (typeof window === "undefined") return;
  if (!token) {
    window.localStorage.removeItem(TOKEN_KEY);
    window.localStorage.removeItem(ME_CACHE_KEY);
    window.localStorage.removeItem(ME_FETCHED_AT_KEY);
    window.localStorage.removeItem("warbot_profile");
  } else {
    window.localStorage.setItem(TOKEN_KEY, token);
  }
}

export function getCachedMe(): CachedMe | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(ME_CACHE_KEY);
    return raw ? (JSON.parse(raw) as CachedMe) : null;
  } catch {
    return null;
  }
}

export function setCachedMe(me: CachedMe | null): void {
  if (typeof window === "undefined") return;
  if (!me) window.localStorage.removeItem(ME_CACHE_KEY);
  else window.localStorage.setItem(ME_CACHE_KEY, JSON.stringify(me));
}

/** Compare Discord snowflakes without Number() precision loss. */
export function discordIdsEqual(a: unknown, b: unknown): boolean {
  if (a == null || b == null) return false;
  const left = String(a).trim();
  const right = String(b).trim();
  if (!left || !right) return false;
  return left === right;
}

/** Drop local session (JWT is stateless; server /auth/logout is optional). */
export function signOut(): void {
  setStoredToken(null);
  setCachedMe(null);
}

/** True when a JWT exists and its `exp` is still in the future (or unreadable → assume ok). */
export function hasUsableSession(): boolean {
  const token = getStoredToken();
  if (!token) return false;
  try {
    const part = (token.split(".")[1] ?? "").replace(/-/g, "+").replace(/_/g, "/");
    const padded = part + "=".repeat((4 - (part.length % 4)) % 4);
    const payload = JSON.parse(atob(padded)) as { exp?: number };
    if (typeof payload.exp === "number" && payload.exp * 1000 <= Date.now()) {
      setStoredToken(null);
      return false;
    }
  } catch {
    /* keep token; server will reject if bad */
  }
  return true;
}

export function captureTokenFromUrl(): void {
  if (typeof window === "undefined") return;
  const url = new URL(window.location.href);
  const token = url.searchParams.get("token");
  if (token) {
    setStoredToken(token);
    url.searchParams.delete("token");
    window.history.replaceState({}, "", url.pathname + url.search + url.hash);
  }
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(init.headers as Record<string, string> | undefined),
  };
  const token = getStoredToken();
  if (token) headers.Authorization = `Bearer ${token}`;

  const res = await fetch(`${API_BASE}${path}`, {
    credentials: "include",
    cache: "no-store",
    ...init,
    headers,
  });

  if (!res.ok) {
    let message = res.statusText || `Request failed (${res.status})`;
    try {
      const data = await res.clone().json();
      if (data?.detail) message = typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail);
      else if (data?.message) message = String(data.message);
    } catch {
      /* ignore */
    }
    if (res.status === 401) setStoredToken(null);
    throw new ApiError(res.status, message);
  }

  if (res.status === 204) return undefined as T;
  const text = await res.text();
  if (!text) return undefined as T;
  return JSON.parse(text) as T;
}

export type Role = "runner" | "bagger";
export type Track = "rt" | "ct";

export interface PlayerSummary {
  discordId: string;
  displayName: string;
  avatarUrl?: string | null;
  rank?: RankKey | null;
  sr?: number | null;
  role?: Role | null;
  nameColor?: string | null;
  inviteId?: string;
}

export interface RatingLane {
  sr?: number;
  rank?: string;
  revealed?: boolean;
  placement_count?: number;
  mu?: number;
}

export interface RatingRow {
  track: string;
  role: string;
  sr?: number;
  rank?: string;
  revealed?: boolean;
  placement_count?: number;
}

export interface MeProfile {
  discord_id: number | string;
  discordId?: string;
  username?: string | null;
  display_name?: string;
  displayName?: string;
  avatar?: string | null;
  avatarUrl?: string | null;
  bio?: string | null;
  mkc_url?: string | null;
  lounge_url?: string | null;
  x_url?: string | null;
  bluesky_url?: string | null;
  youtube_url?: string | null;
  twitch_url?: string | null;
  accent_color?: string | null;
  lineup_name_color?: string | null;
  favorite_track?: FavoriteLane | "rt" | "ct" | null;
  profile_alias?: string | null;
  profile_path?: string | null;
  supporter?: boolean;
  supporter_tier?: "supporter" | "supporter_plus" | null;
  supporter_tier_label?: string | null;
  display_name_custom?: boolean;
  friend_code?: string | null;
  has_linked_fc?: boolean;
  /** Present when Lounge auto-link was attempted but no FC was saved (soft miss). */
  auto_link?: boolean;
  auto_link_hint?: string | null;
  ratings?: Record<string, Record<string, RatingLane | null>>;
}

export interface PublicProfile extends MeProfile {}

export function profileDisplayName(
  profile: MeProfile | PublicProfile | CachedMe | null | undefined
): string {
  if (!profile) return "Unknown";
  return (
    ("display_name" in profile ? profile.display_name : null) ||
    ("displayName" in profile ? profile.displayName : null) ||
    ("username" in profile ? profile.username : null) ||
    String(profile.discord_id ?? ("discordId" in profile ? profile.discordId : "Unknown"))
  );
}

export function profileAvatarUrl(
  profile: MeProfile | PublicProfile | CachedMe | null | undefined
): string | null {
  if (!profile) return null;
  return (
    ("avatar" in profile ? profile.avatar : null) ||
    ("avatarUrl" in profile ? profile.avatarUrl : null) ||
    null
  );
}

export function profileDiscordUsername(
  profile: MeProfile | PublicProfile | null | undefined
): string | null {
  const raw = profile?.username?.trim();
  return raw || null;
}

/** @deprecated Use ProfileLinkIcons / profileLinksFrom instead. */
export function profilePills(profile: MeProfile | PublicProfile | null | undefined): string[] {
  if (!profile) return [];
  const pills: string[] = [];
  if (profile.mkc_url) pills.push("MKCentral");
  if (profile.lounge_url) pills.push("Lounge");
  return pills;
}

export interface PendingOutbound {
  id: string;
  kind: "invited" | "requested" | "challenged";
  label: "Invited" | "Requested" | "Challenged" | string;
  players: PlayerSummary[];
  excludeIds: string[];
  inviteTargetDiscordId?: string;
  warId?: string;
  anonymous?: boolean;
  teamAvgRank?: RankKey | null;
  mode?: string;
}

/** Normalized group view for queue UI components. */
export interface MyGroup {
  members: PlayerSummary[];
  invited: PlayerSummary[];
  pendingOutbound: PendingOutbound[];
  maxSize: number;
  inQueue: boolean;
  /** True when this group has a Discord allies billboard post. */
  onBillboard: boolean;
  /** Where this group is recruiting: web, Discord hub, or both. */
  fillingSurface?: "web" | "discord" | "mixed";
  canSeekOpponents?: boolean;
  board?: string;
  warType?: "RT" | "CT";
  mode?: string;
  inviteCode?: string | null;
  partyId?: string;
  isCaptain?: boolean;
  status?: string;
  captainDiscordId?: string;
  /** friends = lobby only; preview = supporter queue spy (until Join queue). */
  lobbyMode?: "friends" | "preview" | null;
  teamAvgSr?: number | null;
  teamAvgRank?: RankKey | null;
  /** Soft-hidden from public boards due to inactivity. */
  queueHidden?: boolean;
  /** Full 5 core roster — lineup team SR can track. */
  lineupFingerprintReady?: boolean;
  lineupGamesTogether?: number;
  lineupRevealed?: boolean;
  lineupTeamSr?: number | null;
  lineupTeamRank?: RankKey | null;
}

export interface AvailableEntry {
  id: string;
  /** Real hub war id when posted to Discord (not a synthetic web-* id). */
  warId?: string;
  /** Discord id to invite (usually the other group's captain). */
  inviteTargetDiscordId?: string;
  players: PlayerSummary[];
  lookingFor?: string;
  kind?: "allies" | "opponents";
  /** invite = absorb into me; request_join = Discord ally request */
  action?: "invite" | "request_join";
  fillingSurface?: "web" | "discord" | "mixed";
  teamAvgSr?: number | null;
  teamAvgRank?: RankKey | null;
  deltaVsYou?: number | null;
  anonymous?: boolean;
  lineupSeeded?: boolean;
}

export interface IncomingInvitation {
  id: string;
  kind?: "invite" | "challenge";
  fromPlayers: PlayerSummary[];
  anonymous?: boolean;
  teamAvgRank?: RankKey | null;
  label?: string;
}

export interface QueueState {
  myGroup: MyGroup | null;
  available: AvailableEntry[];
  opponents: AvailableEntry[];
  invitations: IncomingInvitation[];
  showOpponents: boolean;
  /** True when Available column should render (in queue or supporter preview). */
  showAvailable: boolean;
  /** Supporter preview: Available is rank-icon spy view only. */
  queueSpy: boolean;
  activeMatch?: { sessionId: string; teamAName?: string; teamBName?: string } | null;
}

export interface MatchSession {
  yourTeam: PlayerSummary[];
  opponents: PlayerSummary[];
  opponentsReady: boolean;
  mapOrMode?: string;
  status: string;
  sessionId?: string;
  isCaptain?: boolean;
  cancelRequest?: {
    id: string;
    youRequested: boolean;
    pending: boolean;
  } | null;
  completionPending?: MatchSessionRaw["completion_pending"];
}

export interface InvitePreview {
  fromPlayers: PlayerSummary[];
  expired?: boolean;
}

export interface QueueGroup {
  party_id?: string;
  id?: string;
  lineup?: Array<Record<string, unknown>>;
  members?: PlayerSummary[];
  invite_code?: string;
  status?: string;
  war_type?: string;
  mode?: string;
  search_mode?: string;
  captain_discord_id?: number;
  match_post_id?: string | null;
  filling_surface?: "web" | "discord" | "mixed";
  invited?: PlayerSummary[];
  lobby_mode?: "friends" | "preview" | null;
  team_avg_sr?: number | null;
  team_avg_rank?: string | null;
  queue_hidden?: boolean;
  hidden_at?: string | null;
}

export interface InviteCardData {
  invite_id?: string;
  id?: string;
  party_id?: string;
  from_discord_id?: number;
  target_discord_id?: number;
  status?: string;
  from_lineup?: Array<Record<string, unknown>>;
}

interface MyGroupApiResponse {
  party: QueueGroup | null;
  inbound_invites: InviteCardData[];
  outbound_invites: InviteCardData[];
  outbound_pending?: any[];
  inbound_pending?: any[];
  active_match?: { session_id?: string; team_a_name?: string; team_b_name?: string } | null;
}

interface WarPost {
  war_id?: string;
  party_id?: string;
  lineup?: Array<Record<string, unknown>>;
  search_mode?: string;
  author_discord_id?: number;
  filling_surface?: "web" | "discord" | "mixed";
  team_avg_sr?: number | null;
  team_avg_rank?: string | null;
  delta_vs_you?: number | null;
  anonymous?: boolean;
  mode?: string;
}

interface MatchSessionRaw {
  session_id?: string;
  board?: string;
  team_a_name?: string;
  team_b_name?: string;
  lineup_a?: Array<Record<string, unknown>>;
  lineup_b?: Array<Record<string, unknown>>;
  roster_a_ids?: number[];
  roster_b_ids?: number[];
  status?: string;
  war_a_id?: string;
  war_b_id?: string;
  author_a_id?: number;
  author_b_id?: number;
  is_captain?: boolean;
  completion_pending?: {
    status?: string;
    manual_fallback?: boolean;
    point_margin?: number;
    reporter_team_name?: string;
    winner_team_name?: string;
    your_team_submitted?: boolean;
    score_instructions?: string;
    fallback_reason?: string;
  } | null;
  cancel_request?: {
    request_id?: string;
    requester_discord_id?: number;
    status?: string;
  } | null;
}

const ROSTER_SIZE = 5;

export function flattenRatings(
  ratings?: Record<string, Record<string, RatingLane | null>>
): RatingRow[] {
  if (!ratings) return [];
  const rows: RatingRow[] = [];
  for (const [track, roles] of Object.entries(ratings)) {
    if (!roles || typeof roles !== "object") continue;
    for (const [role, lane] of Object.entries(roles)) {
      if (!lane || typeof lane !== "object") continue;
      rows.push({
        track,
        role,
        sr: typeof lane.sr === "number" ? lane.sr : Number(lane.sr) || undefined,
        rank: lane.rank ?? "unranked",
        revealed: Boolean(lane.revealed),
        placement_count: lane.placement_count ?? 0,
      });
    }
  }
  return rows;
}

function lineupEntryToPlayer(entry: Record<string, unknown>, inviteId?: string): PlayerSummary {
  const roleRaw = String(entry.role ?? "").toLowerCase();
  const role: Role | null =
    entry.bagger || roleRaw === "bagger" ? "bagger" : roleRaw === "runner" ? "runner" : null;
  const rankRaw = entry.rank != null ? String(entry.rank).toLowerCase() : null;
  return {
    discordId: String(entry.discord_id ?? entry.discordId ?? ""),
    displayName: String(entry.player ?? entry.displayName ?? entry.discord_id ?? "Unknown"),
    avatarUrl: (entry.avatarUrl ?? entry.avatar) as string | null | undefined,
    role,
    inviteId,
    rank: (rankRaw as RankKey | null) ?? "unranked",
    sr: typeof entry.sr === "number" ? entry.sr : null,
    nameColor: (entry.name_color ?? entry.nameColor) as string | null | undefined,
  };
}

function boardForParty(party: QueueGroup): string {
  const wt = String(party.war_type ?? "RT").toUpperCase();
  const mode = party.mode ?? "ranked";
  const track = wt === "CT" ? "ct" : "rt";
  return `${track}-${mode}`;
}

function lineupCanSeekOpponents(lineup: Array<Record<string, unknown>>): boolean {
  if (lineup.length < ROSTER_SIZE) return false;
  return lineup.some(
    (entry) => entry.bagger || String(entry.role ?? "").toLowerCase() === "bagger"
  );
}

function pendingOutboundFromRaw(raw?: any[]): PendingOutbound[] {
  return (raw ?? []).map((p) => ({
    id: String(p.id),
    kind:
      p.kind === "challenged"
        ? "challenged"
        : p.kind === "requested"
          ? "requested"
          : "invited",
    label:
      p.label ??
      (p.kind === "challenged" ? "Challenged" : p.kind === "requested" ? "Requested" : "Invited"),
    players: (p.players ?? []).map((entry: Record<string, unknown>) => lineupEntryToPlayer(entry)),
    excludeIds: (p.exclude_ids ?? []).map(String),
    inviteTargetDiscordId:
      p.invite_target_discord_id != null ? String(p.invite_target_discord_id) : undefined,
    warId: p.war_id != null ? String(p.war_id) : undefined,
    anonymous: Boolean(p.anonymous),
    teamAvgRank: (p.team_avg_rank as RankKey | null) ?? null,
    mode: p.mode != null ? String(p.mode) : undefined,
  }));
}

function inboundPendingFromRaw(raw?: any[]): IncomingInvitation[] {
  return (raw ?? []).map((p) => ({
    id: String(p.id),
    kind: "challenge" as const,
    fromPlayers: (p.players ?? []).map((entry: Record<string, unknown>) =>
      lineupEntryToPlayer(entry)
    ),
    anonymous: Boolean(p.anonymous),
    teamAvgRank: (p.team_avg_rank as RankKey | null) ?? null,
    label: p.label ?? "Challenge",
  }));
}

function partyToMyGroup(
  party: QueueGroup,
  outbound: InviteCardData[],
  viewerId?: number | string | null,
  outboundPending?: any[]
): MyGroup {
  const lineup = party.lineup ?? [];
  const warType = String(party.war_type ?? "RT").toUpperCase() === "CT" ? "CT" : "RT";
  const lobbyRaw = party.lobby_mode;
  const lobbyMode =
    lobbyRaw === "friends" || lobbyRaw === "preview" ? lobbyRaw : null;
  const teamAvgRankRaw = (party as any).team_avg_rank;
  return {
    members: lineup.map((entry) => lineupEntryToPlayer(entry)),
    invited: outbound.map((inv) =>
      lineupEntryToPlayer(
        { discord_id: inv.target_discord_id, player: String(inv.target_discord_id ?? "Invited") },
        inv.invite_id ?? inv.id
      )
    ),
    pendingOutbound: pendingOutboundFromRaw(outboundPending),
    maxSize: ROSTER_SIZE,
    inQueue: party.status === "posted",
    onBillboard: Boolean(party.match_post_id),
    fillingSurface: party.filling_surface ?? (party.match_post_id ? "mixed" : "web"),
    canSeekOpponents: lineupCanSeekOpponents(lineup),
    board: boardForParty(party),
    warType,
    mode: party.mode ?? "ranked",
    inviteCode: party.invite_code ?? null,
    partyId: party.party_id ?? party.id,
    isCaptain:
      viewerId != null && discordIdsEqual(party.captain_discord_id, viewerId),
    status: party.status,
    captainDiscordId: party.captain_discord_id != null ? String(party.captain_discord_id) : undefined,
    lobbyMode,
    teamAvgSr: typeof (party as any).team_avg_sr === "number" ? (party as any).team_avg_sr : null,
    teamAvgRank: (teamAvgRankRaw as RankKey | null) ?? null,
    queueHidden: Boolean(party.queue_hidden),
    lineupFingerprintReady: Boolean((party as any).lineup_fingerprint_ready),
    lineupGamesTogether:
      typeof (party as any).lineup_games_together === "number"
        ? (party as any).lineup_games_together
        : 0,
    lineupRevealed: Boolean((party as any).lineup_revealed),
    lineupTeamSr:
      typeof (party as any).lineup_team_sr === "number" ? (party as any).lineup_team_sr : null,
    lineupTeamRank: ((party as any).lineup_team_rank as RankKey | null) ?? null,
  };
}

function warToAvailableEntry(war: WarPost, kind: "allies" | "opponents" = "allies"): AvailableEntry {
  const lineup = war.lineup ?? [];
  const captainId =
    war.author_discord_id != null
      ? String(war.author_discord_id)
      : String(lineup[0]?.discord_id ?? "");
  const avg = war.team_avg_sr;
  const delta = war.delta_vs_you;
  let lookingFor: string | undefined =
    war.search_mode === "opponents" ? "Looking for opponents" : "Looking for allies";
  if (kind === "opponents" && war.anonymous) {
    lookingFor = undefined;
  } else if (kind === "opponents" && avg != null) {
    const deltaTxt =
      delta == null ? "" : ` · ${delta > 0 ? "+" : ""}${Math.round(delta)} vs you`;
    lookingFor = `Avg SR ${Math.round(avg)}${deltaTxt}`;
  }
  const warId = war.war_id ? String(war.war_id) : undefined;
  const isHubWar = Boolean(warId && !warId.startsWith("web-"));
  return {
    id: warId ?? war.party_id ?? captainId,
    warId,
    inviteTargetDiscordId: captainId || undefined,
    players: lineup.map((entry) => lineupEntryToPlayer(entry)),
    lookingFor,
    kind,
    action: kind === "allies" && isHubWar ? "request_join" : "invite",
    fillingSurface: war.filling_surface,
    teamAvgSr: avg ?? null,
    teamAvgRank: (war.team_avg_rank as RankKey | null) ?? null,
    deltaVsYou: delta ?? null,
    anonymous: Boolean(war.anonymous),
    lineupSeeded: Boolean((war as any).lineup_seeded),
  };
}

function inviteToIncomingInvitation(inv: InviteCardData & { from_lineup?: Array<Record<string, unknown>> }): IncomingInvitation {
  const lineup = inv.from_lineup ?? [];
  const fromPlayers =
    lineup.length > 0
      ? lineup.map((entry) => lineupEntryToPlayer(entry))
      : [
          lineupEntryToPlayer({
            discord_id: inv.from_discord_id,
            player: String(inv.from_discord_id ?? "Unknown"),
          }),
        ];
  return {
    id: inv.invite_id ?? inv.id ?? "",
    kind: "invite",
    fromPlayers,
  };
}

function mapMatchSession(raw: MatchSessionRaw, userId?: number | string | null): MatchSession {
  const uid = userId != null ? String(userId) : null;
  const onTeamB =
    uid != null && (raw.roster_b_ids ?? []).some((id) => discordIdsEqual(id, uid));
  const yourLineup = onTeamB ? raw.lineup_b : raw.lineup_a;
  const oppLineup = onTeamB ? raw.lineup_a : raw.lineup_b;
  const yourAuthor = onTeamB ? raw.author_b_id : raw.author_a_id;
  const cancel = raw.cancel_request;
  const cancelPending = Boolean(cancel && cancel.status === "pending");

  return {
    yourTeam: (yourLineup ?? []).map((entry) => lineupEntryToPlayer(entry)),
    opponents: (oppLineup ?? []).map((entry) => lineupEntryToPlayer(entry)),
    opponentsReady: (oppLineup?.length ?? 0) > 0,
    mapOrMode:
      raw.team_a_name && raw.team_b_name
        ? `${raw.team_a_name} vs ${raw.team_b_name}`
        : raw.board,
    status: raw.status ?? "active",
    sessionId: raw.session_id,
    isCaptain:
      raw.is_captain ??
      (uid != null && yourAuthor != null && discordIdsEqual(yourAuthor, uid)),
    cancelRequest: cancelPending
      ? {
          id: String(cancel?.request_id ?? ""),
          youRequested: uid != null && discordIdsEqual(cancel?.requester_discord_id, uid),
          pending: true,
        }
      : null,
    completionPending: raw.completion_pending ?? null,
  };
}

function mapInvitePreview(data: {
  lineup?: Array<Record<string, unknown>>;
  status?: string;
  expired?: boolean;
}): InvitePreview {
  const lineup = data.lineup ?? [];
  return {
    fromPlayers: lineup.map((entry) => lineupEntryToPlayer(entry)),
    expired:
      data.expired ??
      (data.status === "cancelled" || data.status === "matched"),
  };
}

async function fetchMyGroupRaw(init?: RequestInit): Promise<MyGroupApiResponse> {
  return request<MyGroupApiResponse>("/me/group", init);
}

export type ChatScope = "match" | "group";

export interface ChatMessage {
  id: string | number;
  author_discord_id?: number;
  authorId?: string;
  author_name?: string;
  authorName?: string;
  author_color?: string | null;
  body?: string;
  text?: string;
  created_at?: string;
  sentAt?: string;
}

const RETURN_TO_KEY = "warbot_return_to";

/** Remember where to land after Discord OAuth (invite links, etc.). */
export function setReturnAfterLogin(path: string): void {
  if (typeof window === "undefined") return;
  const trimmed = path.trim();
  if (!trimmed.startsWith("/") || trimmed.startsWith("//")) return;
  window.sessionStorage.setItem(RETURN_TO_KEY, trimmed);
}

export function consumeReturnAfterLogin(fallback = "/q"): string {
  if (typeof window === "undefined") return fallback;
  const path = window.sessionStorage.getItem(RETURN_TO_KEY);
  window.sessionStorage.removeItem(RETURN_TO_KEY);
  if (!path || !path.startsWith("/") || path.startsWith("//")) return fallback;
  return path;
}

export function getDiscordLoginUrl(): string {
  return `${API_BASE}/auth/login`;
}

export async function logout(): Promise<void> {
  try {
    await request<void>("/auth/logout", { method: "POST" });
  } finally {
    setStoredToken(null);
  }
}

export async function getMe(init?: RequestInit): Promise<MeProfile> {
  const me = await request<MeProfile>("/me/profile", init);
  _cacheMeFromProfile(me);
  setCachedProfile(me);
  return me;
}

const PROFILE_CACHE_KEY = "warbot_profile";

export function getCachedProfile(): MeProfile | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(PROFILE_CACHE_KEY);
    return raw ? (JSON.parse(raw) as MeProfile) : null;
  } catch {
    return null;
  }
}

export function setCachedProfile(profile: MeProfile | null): void {
  if (typeof window === "undefined") return;
  if (!profile) window.localStorage.removeItem(PROFILE_CACHE_KEY);
  else window.localStorage.setItem(PROFILE_CACHE_KEY, JSON.stringify(profile));
}

export async function updateMe(
  payload: {
    bio?: string | null;
    mkc_url?: string | null;
    lounge_url?: string | null;
    x_url?: string | null;
    bluesky_url?: string | null;
    youtube_url?: string | null;
    twitch_url?: string | null;
    accent_color?: string | null;
    lineup_name_color?: string | null;
    display_name?: string | null;
    favorite_track?: FavoriteLane | "rt" | "ct" | null;
    profile_alias?: string | null;
  },
  init?: RequestInit
): Promise<MeProfile> {
  await request<MeProfile>("/me/profile", {
    method: "PATCH",
    body: JSON.stringify(payload),
    ...init,
  });
  // PATCH returns a partial row — re-fetch full profile for cache + UI.
  return getMe(init);
}

export interface SupporterPerk {
  id: string;
  tier: "supporter" | "supporter_plus";
  title: string;
  description: string;
  status?: "live" | "wip" | "soon";
}

export interface SupporterTierInfo {
  id: "supporter" | "supporter_plus";
  label: string;
  includes?: "supporter";
  perks: SupporterPerk[];
}

export interface SupporterStatus {
  active: boolean;
  tier?: "supporter" | "supporter_plus" | null;
  tier_label?: string | null;
  supporter?: boolean;
  source: string;
  perks: SupporterPerk[];
  catalog?: { tiers: SupporterTierInfo[]; patreon_page_url?: string | null };
  patreon_page_url?: string | null;
  membership?: {
    member_id?: string;
    patron_status?: string;
    pledge_cents?: number | null;
    discord_id?: number | null;
    next_charge_date?: string | null;
    last_event_at?: string | null;
    updated_at?: string | null;
  } | null;
  supporter_expires_at?: string | null;
  accent_color?: string | null;
  lineup_name_color?: string | null;
  favorite_track?: FavoriteLane | "rt" | "ct" | null;
  profile_alias?: string | null;
  display_name_custom?: boolean;
}

export interface PublicPatron {
  discord_id: string;
  display_name: string;
  tier: "supporter" | "supporter_plus";
  tier_label?: string | null;
  profile_path: string;
}

export async function getSupporterStatus(init?: RequestInit): Promise<SupporterStatus> {
  return request<SupporterStatus>("/me/supporter", init);
}

export async function getPublicSupporterPerks(init?: RequestInit): Promise<{
  tiers: SupporterTierInfo[];
  patreon_page_url?: string | null;
}> {
  return request("/supporter/perks", init);
}

export async function getPublicPatrons(init?: RequestInit): Promise<PublicPatron[]> {
  const data = await request<{ patrons: PublicPatron[] }>("/supporters/patrons", init);
  return data.patrons ?? [];
}

export type LeaderboardScope = "all" | "elite";

export interface LeaderboardEntry {
  rank: number;
  discord_id: string;
  display_name: string;
  sr: number;
  rank_tier: string;
  placement_count?: number;
  profile_path: string;
  supporter_tier?: string | null;
}

export interface LeaderboardResponse {
  track: string;
  role: string;
  scope: LeaderboardScope;
  scope_label: string;
  elite_min_sr?: number | null;
  entries: LeaderboardEntry[];
  total: number;
  offset?: number;
  limit?: number;
}

export interface LeaderboardMeta {
  scopes: Array<{ id: LeaderboardScope; label: string; description: string; min_sr?: number }>;
  default_scope: LeaderboardScope;
  web_default_scope?: LeaderboardScope;
  discord_default_scope?: LeaderboardScope;
  tracks: string[];
  roles: string[];
}

export function getLeaderboard(
  params: {
    track?: string;
    role?: string;
    scope?: LeaderboardScope;
    limit?: number;
    offset?: number;
  },
  init?: RequestInit
): Promise<LeaderboardResponse> {
  const qs = new URLSearchParams();
  if (params.track) qs.set("track", params.track);
  if (params.role) qs.set("role", params.role);
  if (params.scope) qs.set("scope", params.scope);
  if (params.limit != null) qs.set("limit", String(params.limit));
  if (params.offset != null) qs.set("offset", String(params.offset));
  const suffix = qs.toString() ? `?${qs}` : "";
  return request<LeaderboardResponse>(`/leaderboard${suffix}`, init);
}

export function getLeaderboardMeta(init?: RequestInit): Promise<LeaderboardMeta> {
  return request<LeaderboardMeta>("/leaderboard/meta", init);
}

/** Link FC manually, or omit friendCode to try Lounge auto-link. */
export async function linkFriendCode(
  friendCode?: string | null,
  init?: RequestInit
): Promise<MeProfile> {
  const me = await request<MeProfile>("/me/friend-code", {
    method: "POST",
    body: JSON.stringify({ friend_code: friendCode?.trim() || null }),
    ...init,
  });
  _cacheMeFromProfile(me);
  setCachedProfile(me);
  return me;
}

export function getPublicProfile(identifier: string, init?: RequestInit): Promise<PublicProfile> {
  return request<PublicProfile>(`/users/${encodeURIComponent(identifier)}`, init);
}

export interface WarPlayerResult {
  discordId?: string | null;
  displayName: string;
  avatarUrl?: string | null;
  role?: Role | null;
  indiv?: number | null;
  srDelta?: number | null;
  rank?: string | null;
  revealed?: boolean;
}

export interface WarSide {
  teamName: string;
  players: WarPlayerResult[];
  total?: number | null;
}

export interface WarSummary {
  resultId: string;
  completedAt?: string;
  warType?: string;
  mode?: string;
  pointMargin?: number | null;
  winner: WarSide;
  loser: WarSide;
  viewerOutcome?: "W" | "L" | null;
  viewerSrDelta?: number | null;
}

export interface WarDetail extends WarSummary {
  scrimPlusMinus?: number | null;
  rxx?: string | null;
  syncMethod?: string | null;
}

export async function listUserWars(
  discordId: string | number,
  limit = 20,
  init?: RequestInit
): Promise<WarSummary[]> {
  const raw = await request<{ wars: WarSummary[] }>(
    `/users/${discordId}/wars?limit=${limit}`,
    init
  );
  return raw.wars ?? [];
}

export async function getWarResult(resultId: string, init?: RequestInit): Promise<WarDetail> {
  return request<WarDetail>(`/wars/${encodeURIComponent(resultId)}`, init);
}

export function getMyGroup(init?: RequestInit): Promise<MyGroup | null> {
  return fetchMyGroupRaw(init).then(async (raw) => {
    if (!raw.party) return null;
    const me = await getMe(init).catch(() => null);
    return partyToMyGroup(raw.party, raw.outbound_invites, me?.discord_id, raw.outbound_pending);
  });
}

export async function getQueueState(init?: RequestInit): Promise<QueueState> {
  // Identity from cache — avoid full /me/profile on every board refresh.
  const me = getCachedMe() ?? getCachedProfile();
  const raw = await fetchMyGroupRaw(init);
  const myGroup = raw.party
    ? partyToMyGroup(raw.party, raw.outbound_invites, me?.discord_id, raw.outbound_pending)
    : null;
  const board = myGroup?.board ?? (raw.party ? boardForParty(raw.party) : "rt-ranked");
  const myPartyId = raw.party?.party_id ?? raw.party?.id;
  const supporter = Boolean(
    (me && "supporter" in me ? (me as CachedMe).supporter : null) ??
      getCachedProfile()?.supporter
  );
  const queueSpy = Boolean(
    myGroup && !myGroup.inQueue && myGroup.lobbyMode === "preview" && supporter
  );
  const showAvailable = Boolean(myGroup?.inQueue || queueSpy);
  const showOpponents = Boolean(
    (myGroup?.canSeekOpponents && myGroup?.inQueue) || queueSpy
  );

  const [alliesResult, opponentsResult] = await Promise.all([
    showAvailable
      ? request<WarPost[]>(`/available/allies?board=${encodeURIComponent(board)}`, init).catch(
          () => [] as WarPost[]
        )
      : Promise.resolve([] as WarPost[]),
    showOpponents
      ? request<WarPost[]>(
          `/available/opponents?board=${encodeURIComponent(board)}`,
          init
        ).catch(() => [] as WarPost[])
      : Promise.resolve([] as WarPost[]),
  ]);
  const allies = alliesResult;
  const opponents = opponentsResult;

  const notMine = (war: WarPost) => (myPartyId ? war.party_id !== myPartyId : true);

  // Viewer-only: hide parties you've invited / requested, and parties that invited you.
  const excluded = new Set(
    (myGroup?.pendingOutbound ?? []).flatMap((p) => p.excludeIds)
  );
  for (const inv of raw.inbound_invites ?? []) {
    if (inv.party_id != null) excluded.add(String(inv.party_id));
    if (inv.from_discord_id != null) excluded.add(String(inv.from_discord_id));
    for (const entry of inv.from_lineup ?? []) {
      const pid = entry.discord_id ?? entry.discordId;
      if (pid != null) excluded.add(String(pid));
    }
  }
  for (const pending of raw.inbound_pending ?? []) {
    for (const id of pending.exclude_ids ?? []) excluded.add(String(id));
    if (pending.war_id != null) excluded.add(String(pending.war_id));
    for (const pl of pending.players ?? []) {
      const pid = pl.discord_id ?? pl.discordId;
      if (pid != null) excluded.add(String(pid));
    }
  }
  const isExcluded = (e: AvailableEntry) =>
    excluded.has(e.id) ||
    (!!e.warId && excluded.has(e.warId)) ||
    (!!e.inviteTargetDiscordId && excluded.has(e.inviteTargetDiscordId)) ||
    e.players.some((p) => excluded.has(p.discordId));

  return {
    myGroup,
    available: allies
      .filter(notMine)
      .map((war) => warToAvailableEntry(war, "allies"))
      .filter((e) => !isExcluded(e)),
    opponents: opponents
      .filter(notMine)
      .map((war) => warToAvailableEntry(war, "opponents"))
      .filter((e) => !isExcluded(e)),
    invitations: [
      ...(raw.inbound_invites ?? []).map(inviteToIncomingInvitation),
      ...inboundPendingFromRaw(raw.inbound_pending),
    ],
    showOpponents,
    showAvailable,
    queueSpy,
    activeMatch: raw.active_match?.session_id
      ? {
          sessionId: String(raw.active_match.session_id),
          teamAName: raw.active_match.team_a_name,
          teamBName: raw.active_match.team_b_name,
        }
      : null,
  };
}

export function createParty(
  body: {
    war_type: string;
    mode: string;
    role: string;
    search_time?: string;
    lobby_mode?: "friends" | "preview" | null;
    join_queue?: boolean;
  },
  init?: RequestInit
): Promise<QueueGroup> {
  return request<QueueGroup>("/parties", {
    method: "POST",
    body: JSON.stringify(body),
    ...init,
  });
}

export function updateParty(
  partyId: string,
  body: { war_type?: string; role?: string; search_time?: string },
  init?: RequestInit
): Promise<QueueGroup> {
  return request<QueueGroup>(`/parties/${partyId}`, {
    method: "PATCH",
    body: JSON.stringify(body),
    ...init,
  });
}

export async function leaveParty(
  partyId: string,
  init?: RequestInit,
  opts?: { recreateSolo?: boolean }
): Promise<{ left?: boolean; party?: QueueGroup | null }> {
  const qs = opts?.recreateSolo ? "recreate_solo=true" : "recreate_solo=false";
  return request<{ left?: boolean; party?: QueueGroup | null }>(
    `/parties/${partyId}/leave?${qs}`,
    { method: "POST", ...init }
  );
}

export function postParty(partyId: string, init?: RequestInit): Promise<void> {
  return request<void>(`/parties/${partyId}/post`, { method: "POST", ...init });
}

export function joinPartyQueue(partyId: string, init?: RequestInit): Promise<void> {
  return request<void>(`/parties/${partyId}/join-queue`, { method: "POST", ...init });
}

export function leavePartyQueue(partyId: string, init?: RequestInit): Promise<void> {
  return request<void>(`/parties/${partyId}/leave-queue`, { method: "POST", ...init });
}

export function unhidePartyQueue(partyId: string, init?: RequestInit): Promise<void> {
  return request<void>(`/parties/${partyId}/unhide-queue`, { method: "POST", ...init });
}

export function deleteParty(partyId: string, init?: RequestInit): Promise<void> {
  return request<void>(`/parties/${partyId}`, { method: "DELETE", ...init });
}

export function inviteToParty(
  partyId: string,
  targetDiscordId: number | string,
  init?: RequestInit
): Promise<void> {
  // Keep as digit string — Number() corrupts Discord snowflakes (>2^53).
  const target = String(targetDiscordId).trim();
  if (!/^\d{17,20}$/.test(target)) {
    throw new ApiError(400, "Invite target must be a Discord user id.");
  }
  return request<void>(`/parties/${partyId}/invites`, {
    method: "POST",
    body: JSON.stringify({ target_discord_id: target }),
    ...init,
  });
}

export function createMatchRequest(warId: string, init?: RequestInit): Promise<void> {
  return request<void>(`/hub/${encodeURIComponent(warId)}/match-request`, {
    method: "POST",
    ...init,
  });
}

/** Request to join a Discord hub war as an ally (captain accepts in Discord). */
export function requestAlly(
  warId: string,
  role: "Runner" | "Bagger" = "Runner",
  init?: RequestInit
): Promise<void> {
  return request<void>(`/hub/${encodeURIComponent(warId)}/ally-request`, {
    method: "POST",
    body: JSON.stringify({ role }),
    ...init,
  });
}

export function getAvailableOpponents(board: string, init?: RequestInit): Promise<unknown> {
  return request(`/available/opponents?board=${encodeURIComponent(board)}`, init);
}

export async function getInvitePreview(code: string, init?: RequestInit): Promise<InvitePreview> {
  const raw = await request<{
    lineup?: Array<Record<string, unknown>>;
    status?: string;
    expired?: boolean;
  }>(`/parties/invite/${encodeURIComponent(code)}/preview`, init);
  return mapInvitePreview(raw);
}

export function joinPartyByInviteCode(code: string, init?: RequestInit): Promise<void> {
  return request<void>(`/parties/invite/${encodeURIComponent(code)}/join`, {
    method: "POST",
    ...init,
  });
}

export function respondToRequest(
  requestId: string,
  accept: boolean,
  init?: RequestInit
): Promise<void> {
  return request<void>(`/requests/${requestId}/${accept ? "accept" : "deny"}`, {
    method: "POST",
    ...init,
  });
}

export function undoPartyInvite(inviteId: string, init?: RequestInit): Promise<void> {
  return request<void>(`/requests/${inviteId}/deny`, { method: "POST", ...init });
}

export async function getMatchSession(sessionId: string, init?: RequestInit): Promise<MatchSession> {
  const raw = await request<MatchSessionRaw>(`/matches/${sessionId}`, init);
  const me = getCachedMe() ?? getCachedProfile();
  const userId = me?.discord_id ?? ("discordId" in (me || {}) ? (me as MeProfile).discordId : null);
  return mapMatchSession(raw, userId);
}

export function requestMatchCancel(sessionId: string, init?: RequestInit): Promise<void> {
  return request<void>(`/matches/${encodeURIComponent(sessionId)}/cancel`, {
    method: "POST",
    ...init,
  });
}

export function respondMatchCancel(
  sessionId: string,
  accept: boolean,
  init?: RequestInit
): Promise<void> {
  return request<void>(
    `/matches/${encodeURIComponent(sessionId)}/cancel/${accept ? "accept" : "decline"}`,
    { method: "POST", ...init }
  );
}

export function submitMatchResult(
  sessionId: string,
  body: { margin: number; rxx: string; reporter_won: boolean; scores?: string },
  init?: RequestInit
): Promise<void> {
  return request<void>(`/matches/${encodeURIComponent(sessionId)}/submit`, {
    method: "POST",
    body: JSON.stringify(body),
    ...init,
  });
}

export interface MatchSessionSummary {
  session_id: string;
  status?: string;
  team_a_name?: string;
  team_b_name?: string;
  created_at?: string;
}

export async function getMyActiveMatch(init?: RequestInit): Promise<MatchSessionSummary | null> {
  const rows = await request<MatchSessionSummary[]>("/matches/me", init);
  const active = (rows ?? []).find((s) => (s.status ?? "active") === "active");
  return active?.session_id ? active : null;
}

export function getMatchMessages(
  sessionId: string,
  channel: ChatScope,
  init?: RequestInit
): Promise<ChatMessage[]> {
  return request<ChatMessage[]>(
    `/matches/${sessionId}/messages?channel=${channel}`,
    init
  );
}

export function sendMatchMessage(
  sessionId: string,
  channel: ChatScope,
  body: string,
  init?: RequestInit
): Promise<ChatMessage> {
  return request<ChatMessage>(`/matches/${sessionId}/messages`, {
    method: "POST",
    body: JSON.stringify({ channel, body }),
    ...init,
  });
}

export function eventsUrl(): string {
  const token = getStoredToken();
  const q = token ? `?token=${encodeURIComponent(token)}` : "";
  return `${API_BASE}/events${q}`;
}

function capturePartyPrefs(
  party: QueueGroup,
  myId: number | string | null | undefined
): { war_type: string; mode: string; role: string } {
  const lineup = party.lineup ?? [];
  const myEntry =
    myId != null
      ? lineup.find((entry) => discordIdsEqual(entry.discord_id ?? entry.discordId, myId))
      : undefined;
  const roleRaw = String(myEntry?.role ?? "").toLowerCase();
  const isBagger = Boolean(myEntry?.bagger) || roleRaw === "bagger";
  return {
    war_type: String(party.war_type ?? "RT"),
    mode: party.mode ?? "ranked",
    role: isBagger ? "Bagger" : "Runner",
  };
}

async function ensureSoloGroupAfterLeave(
  init: RequestInit | undefined,
  prefs: { war_type: string; mode: string; role: string }
): Promise<void> {
  const raw = await fetchMyGroupRaw(init);
  if (!raw.party) {
    await createParty({ ...prefs, search_time: "ASAP" }, init);
  }
}

async function leaveOrCancelParty(init?: RequestInit): Promise<void> {
  const [raw, me] = await Promise.all([
    fetchMyGroupRaw(init),
    getMe(init).catch(() => null),
  ]);
  const party = raw.party;
  if (!party) throw new ApiError(400, "No active group");
  const id = party.party_id ?? party.id;
  if (!id) throw new ApiError(400, "No active group");

  const myId = me?.discord_id ?? me?.discordId;
  const isCaptain =
    myId != null && discordIdsEqual(party.captain_discord_id, myId);

  if (isCaptain) {
    await deleteParty(String(id), init);
    return;
  }

  await leaveParty(String(id), init);
}

/** Leave/cancel the active group (captains cancel; members leave). */
export const leaveGroup = leaveOrCancelParty;

export async function joinQueue(partyId?: string | null, init?: RequestInit): Promise<void> {
  let id = partyId || null;
  if (!id) {
    const raw = await fetchMyGroupRaw(init);
    id = raw.party?.party_id ?? raw.party?.id ?? null;
  }
  if (!id) throw new ApiError(400, "No active group");
  await joinPartyQueue(String(id), init);
}

/** Restore visibility after idle soft-hide. */
export async function restoreQueueVisibility(
  partyId?: string | null,
  init?: RequestInit
): Promise<void> {
  let id = partyId || null;
  if (!id) {
    const raw = await fetchMyGroupRaw(init);
    id = raw.party?.party_id ?? raw.party?.id ?? null;
  }
  if (!id) throw new ApiError(400, "No active group");
  await unhidePartyQueue(String(id), init);
}

/** Leave web queue. Captains unpost (keep group); members leave the roster entirely. */
export async function leaveQueue(
  partyId?: string | null,
  init?: RequestInit
): Promise<void> {
  const me = getCachedMe() ?? getCachedProfile();
  // Need party payload for captain/status — one /me/group is enough (no /me/profile).
  const raw = await fetchMyGroupRaw(init);
  const party = raw.party;
  if (!party) throw new ApiError(400, "No active group");
  if (party.status !== "posted" && party.status !== "preparing") return;
  const id = partyId || party.party_id || party.id;
  if (!id) throw new ApiError(400, "No active group");

  const myId = me?.discord_id ?? ("discordId" in (me || {}) ? (me as MeProfile).discordId : null);
  const isCaptain = myId != null && discordIdsEqual(party.captain_discord_id, myId);

  if (isCaptain) {
    if (party.status === "posted") await leavePartyQueue(String(id), init);
    return;
  }

  const prefs = capturePartyPrefs(party, myId);
  await leaveParty(String(id), init, { recreateSolo: true });
  await ensureSoloGroupAfterLeave(init, prefs);
}

/** Post the active group to the Discord allies billboard (captain). */
export async function postToAlliesBillboard(
  partyId?: string | null,
  init?: RequestInit
): Promise<void> {
  let id = partyId || null;
  if (!id) {
    const raw = await fetchMyGroupRaw(init);
    id = raw.party?.party_id ?? raw.party?.id ?? null;
  }
  if (!id) throw new ApiError(400, "No active group");
  await postParty(String(id), init);
}

export const inviteEntry = async (
  targetDiscordId: string,
  partyId?: string | null,
  init?: RequestInit
) => {
  let id = partyId || null;
  if (!id) {
    const raw = await fetchMyGroupRaw(init);
    id = raw.party?.party_id ?? raw.party?.id ?? null;
  }
  if (!id) throw new ApiError(400, "No active group");
  if (!/^\d+$/.test(String(targetDiscordId))) {
    throw new ApiError(400, "Invite target must be a Discord user id.");
  }
  await inviteToParty(String(id), targetDiscordId, init);
};

/** Subscribe to companion SSE; calls onEvent for each named event (and any message). */
export function subscribeEvents(
  onEvent: (eventType: string, data: unknown) => void,
  onError?: (err: Event) => void
): () => void {
  if (typeof window === "undefined") return () => undefined;
  const source = new EventSource(eventsUrl());
  const handler = (eventType: string) => (ev: MessageEvent) => {
    let data: unknown = ev.data;
    try {
      data = JSON.parse(String(ev.data));
    } catch {
      /* keep raw */
    }
    onEvent(eventType, data);
  };
  // Default messages (no `event:` field) plus every queue-relevant named event.
  source.onmessage = handler("message");
  for (const name of ["connected", "party", "chat", "hub", "queue", "party_sync", "match_confirmed"]) {
    source.addEventListener(name, handler(name) as EventListener);
  }
  source.onerror = (err) => {
    onError?.(err);
  };
  return () => source.close();
}

export const undoInvite = undoPartyInvite;
export const respondToInvitation = respondToRequest;
export const joinGroupByCode = joinPartyByInviteCode;
