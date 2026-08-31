export type QueueComboId = "rt-ranked" | "rt-casual" | "ct-ranked" | "ct-casual";

export type QueueCombo = {
  id: QueueComboId;
  war_type: "RT" | "CT";
  mode: "ranked" | "casual";
  label: string;
  enabled: boolean;
  coming_soon: boolean;
};

/** Mirror utils/queue_modes.py — only RT ranked is live at 1.0. */
export const QUEUE_COMBOS: QueueCombo[] = [
  {
    id: "rt-ranked",
    war_type: "RT",
    mode: "ranked",
    label: "RT Ranked",
    enabled: true,
    coming_soon: false,
  },
  {
    id: "rt-casual",
    war_type: "RT",
    mode: "casual",
    label: "RT Casual",
    enabled: false,
    coming_soon: true,
  },
  {
    id: "ct-ranked",
    war_type: "CT",
    mode: "ranked",
    label: "CT Ranked",
    enabled: false,
    coming_soon: true,
  },
  {
    id: "ct-casual",
    war_type: "CT",
    mode: "casual",
    label: "CT Casual",
    enabled: false,
    coming_soon: true,
  },
];

export const DEFAULT_QUEUE_COMBO = QUEUE_COMBOS[0];

export function findQueueCombo(warType: "RT" | "CT", mode: "ranked" | "casual"): QueueCombo | undefined {
  return QUEUE_COMBOS.find((c) => c.war_type === warType && c.mode === mode);
}

export function isQueueComboEnabled(warType: "RT" | "CT", mode: "ranked" | "casual"): boolean {
  return Boolean(findQueueCombo(warType, mode)?.enabled);
}
