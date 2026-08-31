"""Featured profile lane preference (track × role)."""

from __future__ import annotations

# Legacy rt/ct = best SR on that track; lane slugs pin a specific board.
VALID_FAVORITE_LANES = frozenset(
    {
        "rt",
        "ct",
        "rt_runner",
        "rt_bagger",
        "ct_runner",
        "ct_bagger",
    }
)


def normalize_favorite_lane(raw: str | None) -> str | None:
    if raw is None:
        return None
    value = str(raw).strip().lower()
    if not value:
        return None
    if value not in VALID_FAVORITE_LANES:
        raise ValueError(
            "favorite_track must be rt, ct, rt_runner, rt_bagger, ct_runner, or ct_bagger."
        )
    return value
