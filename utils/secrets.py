"""Google Secret Manager helpers (shared by bot startup and DB)."""

from __future__ import annotations

import os

from google.api_core.exceptions import NotFound, PermissionDenied
from google.cloud import secretmanager


def get_project_secret_id() -> str:
    return os.getenv("GOOGLE_CLOUD_PROJECT_SECRET_ID", "war-bot")


# Back-compat for callers that read the module attribute after dotenv load.
PROJECT_SECRET_ID = get_project_secret_id()


def decode_and_normalise_secret(raw: bytes) -> str:
    """Try UTF-8 first, then UTF-16 (handles BOM), then latin-1."""
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        try:
            text = raw.decode("utf-16")
        except UnicodeDecodeError:
            text = raw.decode("latin-1")

    text = text.replace("\ufeff", "").replace("\x00", "")
    return text.strip()


def get_secret(secret_id: str, version_id: str = "latest") -> str:
    """Fetch a secret string from Google Secret Manager and normalise it."""
    client = secretmanager.SecretManagerServiceClient()
    project = get_project_secret_id()
    name = f"projects/{project}/secrets/{secret_id}/versions/{version_id}"
    try:
        resp = client.access_secret_version(request={"name": name})
        secret_text = decode_and_normalise_secret(resp.payload.data)

        if secret_id.startswith("discord_"):
            if secret_text.count(".") != 2:
                raise RuntimeError(
                    f"Secret '{secret_id}' does not look like a Discord bot token "
                    "(expected three dot-separated parts)."
                )
        return secret_text
    except PermissionDenied:
        raise RuntimeError(f"No access to secret '{secret_id}'. Check IAM permissions.")
    except NotFound:
        raise RuntimeError(f"Secret or version not found: {name}")
