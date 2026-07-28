"""Discord Label + String Select modals (interactions.py still only models text inputs)."""

from __future__ import annotations

import uuid
from typing import Any, Optional

from interactions.models.internal.context import ModalContext


LABEL = 18
STRING_SELECT = 3
MODAL_CALLBACK = 9


class ModalHandle:
    """Minimal stand-in so wait_for_modal can match custom_id when sending a raw dict."""

    def __init__(self, custom_id: Optional[str] = None) -> None:
        self.custom_id = custom_id or str(uuid.uuid4())


def select_option(label: str, value: str, description: Optional[str] = None) -> dict[str, str]:
    opt: dict[str, str] = {"label": label, "value": value}
    if description:
        opt["description"] = description
    return opt


def label_string_select(
    *,
    label: str,
    custom_id: str,
    options: list[dict[str, str]],
    placeholder: Optional[str] = None,
    description: Optional[str] = None,
    required: bool = True,
) -> dict[str, Any]:
    select: dict[str, Any] = {
        "type": STRING_SELECT,
        "custom_id": custom_id,
        "options": options,
        "required": required,
        "min_values": 1,
        "max_values": 1,
    }
    if placeholder:
        select["placeholder"] = placeholder
    out: dict[str, Any] = {"type": LABEL, "label": label, "component": select}
    if description:
        out["description"] = description
    return out


def build_label_modal(
    *,
    title: str,
    labels: list[dict[str, Any]],
    custom_id: Optional[str] = None,
) -> tuple[dict[str, Any], ModalHandle]:
    handle = ModalHandle(custom_id)
    payload = {
        "type": MODAL_CALLBACK,
        "data": {
            "title": title,
            "custom_id": handle.custom_id,
            "components": labels,
        },
    }
    return payload, handle


def parse_modal_components(components: list[dict[str, Any]]) -> dict[str, str]:
    """Map custom_id → value for Action Row text inputs and Label selects/text."""
    responses: dict[str, str] = {}
    for comp in components or []:
        ctype = comp.get("type")
        if ctype == 1:  # ACTION_ROW (legacy text inputs)
            for inner in comp.get("components") or []:
                _store_inner(responses, inner)
        elif ctype == LABEL:
            _store_inner(responses, comp.get("component") or {})
    return responses


def _store_inner(responses: dict[str, str], inner: dict[str, Any]) -> None:
    cid = inner.get("custom_id")
    if not cid:
        return
    if "values" in inner:
        vals = inner.get("values") or []
        responses[cid] = vals[0] if vals else ""
    else:
        responses[cid] = inner.get("value") or ""


_patched = False


def patch_modal_context() -> None:
    """Allow ModalContext to parse Label + String Select submits."""
    global _patched
    if _patched:
        return

    @classmethod
    def from_dict(cls, client, payload):  # type: ignore[no-untyped-def]
        instance = super(ModalContext, cls).from_dict(client, payload)
        instance.responses = parse_modal_components(payload.get("data", {}).get("components") or [])
        instance.kwargs = instance.responses
        instance.custom_id = payload["data"]["custom_id"]
        instance.edit_origin = False
        return instance

    ModalContext.from_dict = from_dict  # type: ignore[method-assign]
    _patched = True
