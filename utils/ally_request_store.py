import json
import os
import uuid
from datetime import datetime
from typing import Any, Dict, Optional

from utils.config import DATA_DIR

ALLY_REQUESTS_PATH = os.path.join(DATA_DIR, "ally-requests.json")


def _load_all() -> Dict[str, Any]:
    if not os.path.exists(ALLY_REQUESTS_PATH):
        return {"requests": {}}
    try:
        with open(ALLY_REQUESTS_PATH, "r", encoding="utf-8") as handle:
            data = json.load(handle)
            return data if "requests" in data else {"requests": {}}
    except json.JSONDecodeError:
        return {"requests": {}}


def _save_all(data: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(ALLY_REQUESTS_PATH), exist_ok=True)
    with open(ALLY_REQUESTS_PATH, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False)


def get_ally_request(request_id: str) -> Optional[Dict[str, Any]]:
    return _load_all()["requests"].get(request_id)


def upsert_ally_request(request: Dict[str, Any]) -> Dict[str, Any]:
    data = _load_all()
    data["requests"][request["request_id"]] = request
    _save_all(data)
    return request


def delete_ally_request(request_id: str) -> bool:
    data = _load_all()
    if request_id not in data["requests"]:
        return False
    del data["requests"][request_id]
    _save_all(data)
    return True


def pending_ally_for_war(war_id: str) -> Optional[Dict[str, Any]]:
    for request in _load_all()["requests"].values():
        if request.get("war_id") == war_id and request.get("status") == "pending":
            return request
    return None


def pending_ally_for_user(discord_id: int) -> Optional[Dict[str, Any]]:
    for request in _load_all()["requests"].values():
        if (
            request.get("requester_discord_id") == discord_id
            and request.get("status") == "pending"
        ):
            return request
    return None


def pending_ally_for_war_and_user(war_id: str, discord_id: int) -> Optional[Dict[str, Any]]:
    for request in _load_all()["requests"].values():
        if (
            request.get("war_id") == war_id
            and request.get("requester_discord_id") == discord_id
            and request.get("status") == "pending"
        ):
            return request
    return None


def create_ally_request(
    board: str,
    war_id: str,
    requester_discord_id: int,
    requester_name: str,
    role: str,
) -> Dict[str, Any]:
    request = {
        "request_id": str(uuid.uuid4()),
        "board": board,
        "war_id": war_id,
        "requester_discord_id": requester_discord_id,
        "requester_name": requester_name,
        "role": role,
        "status": "pending",
        "notification_channel_id": None,
        "notification_message_id": None,
        "created_at": datetime.utcnow().isoformat(),
    }
    return upsert_ally_request(request)
