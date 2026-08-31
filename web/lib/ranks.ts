/**
 * Scrims Rating (SR) rank helpers.
 * Mirrors the tier order/labels used by the bot's rating engine (utils/sr.py).
 */

export type RankKey =
  | "unranked"
  | "iron"
  | "bronze"
  | "silver"
  | "gold"
  | "platinum"
  | "diamond"
  | "emerald"
  | "ruby"
  | "paragon";

export const RANK_ORDER: RankKey[] = [
  "paragon",
  "ruby",
  "emerald",
  "diamond",
  "platinum",
  "gold",
  "silver",
  "bronze",
  "iron",
  "unranked",
];

const RANK_LABELS: Record<RankKey, string> = {
  unranked: "Unranked",
  iron: "Iron",
  bronze: "Bronze",
  silver: "Silver",
  gold: "Gold",
  platinum: "Platinum",
  diamond: "Diamond",
  emerald: "Emerald",
  ruby: "Ruby",
  paragon: "Paragon",
};

function normalizeRank(rank?: string | null): RankKey | null {
  if (!rank) return null;
  const key = rank.toLowerCase();
  return (RANK_LABELS as Record<string, string>)[key] ? (key as RankKey) : null;
}

/** Icon path for a rank (including Unranked ?). */
export function rankIconSrc(rank?: string | null): string | null {
  const key = normalizeRank(rank) ?? "unranked";
  if (key === "unranked") return "/ranks/unranked.png";
  return `/ranks/${key}.webp`;
}

export function rankLabel(rank?: string | null): string {
  const key = normalizeRank(rank);
  return RANK_LABELS[key ?? "unranked"];
}
