"""Which track × mode combinations are open for web queueing."""

from __future__ import annotations

from typing import Any

# Only RT ranked is live at 1.0; flip entries here when opening more boards.
_ENABLED: frozenset[tuple[str, str]] = frozenset({("RT", "ranked")})

_QUEUE_COMBOS: tuple[dict[str, Any], ...] = (
    {"id": "rt-ranked", "war_type": "RT", "mode": "ranked", "label": "RT Ranked"},
    {"id": "rt-casual", "war_type": "RT", "mode": "casual", "label": "RT Casual"},
    {"id": "ct-ranked", "war_type": "CT", "mode": "ranked", "label": "CT Ranked"},
    {"id": "ct-casual", "war_type": "CT", "mode": "casual", "label": "CT Casual"},
)


def normalize_queue_combo(war_type: str, mode: str) -> tuple[str, str]:
    return str(war_type or "RT").strip().upper(), str(mode or "ranked").strip().lower()


def is_queue_combo_enabled(war_type: str, mode: str) -> bool:
    return normalize_queue_combo(war_type, mode) in _ENABLED


def queue_combo_block_reason(war_type: str, mode: str) -> str | None:
    """None when allowed; otherwise a short user-facing reason."""
    wt, m = normalize_queue_combo(war_type, mode)
    if is_queue_combo_enabled(wt, m):
        return None
    if wt == "RT" and m == "casual":
        return "RT Casual is coming soon."
    if wt == "CT" and m == "ranked":
        return "CT Ranked is coming soon."
    if wt == "CT" and m == "casual":
        return "CT Casual is coming soon."
    return "This queue mode is not available yet."


def assert_queue_combo_enabled(war_type: str, mode: str) -> None:
    reason = queue_combo_block_reason(war_type, mode)
    if reason:
        raise ValueError(reason)


def list_queue_combos() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for combo in _QUEUE_COMBOS:
        wt, m = combo["war_type"], combo["mode"]
        enabled = is_queue_combo_enabled(wt, m)
        out.append(
            {
                **combo,
                "enabled": enabled,
                "coming_soon": not enabled,
            }
        )
    return out
