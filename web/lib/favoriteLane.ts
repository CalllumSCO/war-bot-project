export type FavoriteLane =
  | ""
  | "rt"
  | "ct"
  | "rt_runner"
  | "rt_bagger"
  | "ct_runner"
  | "ct_bagger";

export const FAVORITE_LANE_OPTIONS: Array<{ value: FavoriteLane; label: string }> = [
  { value: "", label: "Highest SR lane (default)" },
  { value: "rt_runner", label: "Regular Tracks · Runner" },
  { value: "rt_bagger", label: "Regular Tracks · Bagger" },
  { value: "ct_runner", label: "Custom Tracks · Runner" },
  { value: "ct_bagger", label: "Custom Tracks · Bagger" },
];

export function parseFavoriteLane(
  raw: string | null | undefined
): { track?: string; role?: string } | null {
  if (!raw) return null;
  const value = raw.trim().toLowerCase();
  if (!value) return null;
  if (value.includes("_")) {
    const [track, role] = value.split("_", 2);
    if (track && role) return { track, role };
  }
  return { track: value };
}

export function isFavoriteLane(value: string): value is FavoriteLane {
  return FAVORITE_LANE_OPTIONS.some((opt) => opt.value === value);
}
