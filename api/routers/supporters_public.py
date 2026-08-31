"""Public supporter catalog and patron thank-you list."""

from __future__ import annotations

from fastapi import APIRouter, Query

from api.services.supporter import list_public_patrons, public_perks_payload

router = APIRouter(tags=["supporters"])


@router.get("/supporter/perks")
def get_public_supporter_perks() -> dict:
    return public_perks_payload()


@router.get("/supporters/patrons")
def get_public_patrons(limit: int = Query(100, ge=1, le=200)) -> dict:
    return {"patrons": list_public_patrons(limit=limit)}
