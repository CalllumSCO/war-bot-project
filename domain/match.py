"""Match request / finalize domain API (Discord channel creation stays in utils.match_service)."""

from utils.ally_request_store import (
    create_ally_request,
    delete_ally_request,
    get_ally_request,
    pending_ally_for_war,
    pending_ally_for_war_and_user,
    pending_ally_for_user,
    upsert_ally_request,
)
from utils.match_request_store import (
    create_request as create_match_request,
    delete_request as delete_match_request,
    get_request as get_match_request,
    pending_for_target_war,
    upsert_request as upsert_match_request,
)
from utils.match_service import (
    board_for_party,
    finalize_match,
    roster_member_ids,
    start_match_request,
)
from utils.match_session_store import (
    create_session,
    delete_session,
    get_session,
    get_session_by_channel,
    get_session_by_war_id,
    get_session_for_user,
    upsert_session,
)
from utils.party_invite_store import (
    create_party_invite,
    delete_party_invite,
    get_party_invite,
    list_inbound_invites,
    list_outbound_invites,
    upsert_party_invite,
)

__all__ = [
    "board_for_party",
    "create_ally_request",
    "create_match_request",
    "create_party_invite",
    "create_session",
    "delete_ally_request",
    "delete_match_request",
    "delete_party_invite",
    "delete_session",
    "finalize_match",
    "get_ally_request",
    "get_match_request",
    "get_party_invite",
    "get_session",
    "get_session_by_channel",
    "get_session_by_war_id",
    "get_session_for_user",
    "list_inbound_invites",
    "list_outbound_invites",
    "pending_ally_for_user",
    "pending_ally_for_war",
    "pending_ally_for_war_and_user",
    "pending_for_target_war",
    "roster_member_ids",
    "start_match_request",
    "upsert_ally_request",
    "upsert_match_request",
    "upsert_party_invite",
    "upsert_session",
]
