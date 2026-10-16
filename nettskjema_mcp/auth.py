"""OAuth2 client credentials token provider."""

import asyncio
import logging
import time
from typing import Any

import httpx

from nettskjema_mcp.config import Settings
from nettskjema_mcp.errors import (
    AuthenticationError,
    NettskjemaError,
    UpstreamError,
    trim_excerpt,
)

# Module-level time source for testing
_now = time.monotonic

# Refresh tokens this many seconds before actual expiry
REFRESH_BUFFER_SECONDS: int = 3600

# How much of a failed token response to quote back. Bounded for the same reason
# API error bodies are: an outage page must not flood a model's context.
AUTH_ERROR_EXCERPT_LIMIT: int = 300

logger = logging.getLogger(__name__)


class TokenProvider:
    """
    Cached OAuth2 client credentials token provider.

    Fetches access tokens from the authorization server and caches them
    until they expire. Thread-safe for concurrent access.
    """

    def __init__(self, http: httpx.AsyncClient, settings: Settings) -> None:
        """
        Initialize the token provider.

        Args:
            http: The HTTP client to use for token requests.
            settings: Configuration settings including auth URL and credentials.
        """
        self._http = http
        self._settings = settings
        self._cached_token: str | None = None
        self._expires_at: float | None = None
        self._lock = asyncio.Lock()

    async def token(self) -> str:
        """
        Get a valid access token.

        Returns the cached token if it hasn't expired, otherwise fetches
        a new one from the authorization server.

        Returns:
            A valid access token.

        Raises:
            AuthenticationError: If credentials are missing or authentication fails.
        """
        # Fast path: return cached token if still valid
        if self._is_valid():
            assert self._cached_token is not None  # for type checker
            return self._cached_token

        # Slow path: acquire lock and refetch
        async with self._lock:
            # Double-check after acquiring lock (another caller may have fetched)
            if self._is_valid():
                assert self._cached_token is not None
                return self._cached_token

            # Check credentials before making the request
            if not self._settings.client_id or not self._settings.client_secret:
                raise AuthenticationError(
                    "Missing OAuth2 credentials. Set both NETTSKJEMA_CLIENT_ID "
                    "and NETTSKJEMA_CLIENT_SECRET environment variables."
                )

            # Fetch a new token
            token, expires_in = await self._fetch_token()
            self._cached_token = token
            self._expires_at = _now() + expires_in - REFRESH_BUFFER_SECONDS
            logger.debug("Fetched new access token (expires in %ds)", expires_in)
            return token

    def invalidate(self) -> None:
        """Clear the cached token, forcing a refetch on the next call to token()."""
        self._cached_token = None
        self._expires_at = None
        logger.debug("Invalidated cached token")

    def _is_valid(self) -> bool:
        """Check if the cached token is still valid."""
        if self._cached_token is None or self._expires_at is None:
            return False
        return _now() < self._expires_at

    async def _fetch_token(self) -> tuple[str, int]:
        """
        Fetch a new access token from the authorization server.

        Returns:
            A tuple of (access_token, expires_in_seconds).

        Raises:
            AuthenticationError: If the credentials or the client were rejected.
            UpstreamError: If the authorization server itself failed.
        """
        # Credentials are checked in token() before calling this method
        assert self._settings.client_id is not None
        assert self._settings.client_secret is not None

        try:
            response = await self._http.post(
                self._settings.auth_url,
                auth=(self._settings.client_id, self._settings.client_secret),
                data={"grant_type": "client_credentials"},
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise _token_error(exc.response) from exc

        body: dict[str, Any] = response.json()
        access_token: str = body["access_token"]
        expires_in: int = body["expires_in"]
        return access_token, expires_in


def _token_error(response: httpx.Response) -> NettskjemaError:
    """
    Map a token-endpoint failure onto the project's own error hierarchy.

    No tool should ever see a raw httpx exception, so every error status the
    authorization server can return is translated here.

    A 4xx from an OAuth2 token endpoint means the client or its credentials were
    refused — RFC 6749 spends those on invalid_client, invalid_grant and
    unauthorized_client — so 4xx stays AuthenticationError. A 5xx is the
    authorization server failing rather than us, which is an upstream problem.

    error_for_status is deliberately not reused: its 403 branch explains how to
    grant a client form-editing permissions in Nettskjema, which is about the
    API and would misdirect someone whose token request was refused.

    Args:
        response: The failed response from the token endpoint.

    Returns:
        The typed error to raise. Never quotes the request, so the client secret
        cannot reach a log line or a model's context.
    """
    status = response.status_code
    if status == 401:
        message = "OAuth2 authentication failed. Check your client credentials."
    elif status < 500:
        message = (
            f"The authorization server refused the token request (HTTP {status}). "
            "Check that the client exists and is allowed the client_credentials grant."
        )
    else:
        message = (
            f"The authorization server could not issue a token (HTTP {status}). "
            "This is usually a temporary outage; retry shortly."
        )

    detail = _token_error_detail(response)
    if detail:
        message = f"{message} Server said: {detail}"

    if status < 500:
        return AuthenticationError(message, status=status)
    return UpstreamError(message, status=status)


def _token_error_detail(response: httpx.Response) -> str:
    """
    Summarise a failed token response as a bounded excerpt.

    Prefers the OAuth2 error fields when the body is JSON, and falls back to the
    raw text — an outage often answers with an HTML page rather than JSON, and a
    decode error raised on top of the real failure would hide it.
    """
    try:
        body: object = response.json()
    except ValueError:
        return trim_excerpt(response.text, AUTH_ERROR_EXCERPT_LIMIT)

    if isinstance(body, dict):
        parts = [str(body[key]) for key in ("error", "error_description") if body.get(key)]
        if parts:
            return trim_excerpt(": ".join(parts), AUTH_ERROR_EXCERPT_LIMIT)
    return trim_excerpt(response.text, AUTH_ERROR_EXCERPT_LIMIT)
