# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Oliver Ruste Jahren
"""Configuration for Nettskjema MCP server."""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    """Configuration settings for the Nettskjema API client."""

    base_url: str
    auth_url: str
    client_id: str | None
    client_secret: str | None
    timeout: float
    log_level: str
    max_answer_rows: int
    max_text_chars: int


_settings_cache: Settings | None = None


def get_settings() -> Settings:
    """
    Get configuration settings, reading from environment on first call.

    Settings are cached after the first call. Use reset_settings() to clear
    the cache (primarily for testing).

    Returns:
        Settings instance with current configuration.
    """
    global _settings_cache
    if _settings_cache is None:
        _settings_cache = Settings(
            base_url=os.getenv("NETTSKJEMA_BASE_URL", "https://nettskjema.no/api/v3"),
            auth_url=os.getenv(
                "NETTSKJEMA_AUTH_URL", "https://authorization.nettskjema.no/oauth2/token"
            ),
            client_id=os.getenv("NETTSKJEMA_CLIENT_ID"),
            client_secret=os.getenv("NETTSKJEMA_CLIENT_SECRET"),
            timeout=float(os.getenv("NETTSKJEMA_TIMEOUT", "30.0")),
            log_level=os.getenv("NETTSKJEMA_LOG_LEVEL", "INFO"),
            max_answer_rows=int(os.getenv("NETTSKJEMA_MAX_ANSWER_ROWS", "1000")),
            max_text_chars=int(os.getenv("NETTSKJEMA_MAX_TEXT_CHARS", "1000000")),
        )
    return _settings_cache


def reset_settings() -> None:
    """
    Clear the settings cache.

    This is primarily a test hook to allow tests to modify environment
    variables and have them take effect on the next get_settings() call.
    """
    global _settings_cache
    _settings_cache = None
