"""Ack Discord interactions within the 3s window before slow I/O."""

from __future__ import annotations


async def defer_ephemeral(ctx) -> bool:
    """
    Best-effort ephemeral defer. Safe if already deferred/responded.

    Returns True when the interaction is deferred (or was already), False if
    Discord rejected the ack (expired / unknown interaction).
    """
    if getattr(ctx, "deferred", False) or getattr(ctx, "responded", False):
        return True
    try:
        await ctx.defer(ephemeral=True)
        return True
    except Exception as exc:
        print(f"⚠️ defer_ephemeral failed: {exc}")
        return False


async def send_ephemeral(ctx, *args, **kwargs) -> bool:
    """Follow-up/send helper that never raises to the command dispatcher."""
    kwargs.setdefault("ephemeral", True)
    try:
        await ctx.send(*args, **kwargs)
        return True
    except Exception as exc:
        print(f"⚠️ send_ephemeral failed: {exc}")
        return False
