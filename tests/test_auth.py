"""Tests for OAuth2 client credentials token provider."""

import asyncio

import httpx
import pytest
import respx

from nettskjema_mcp import auth
from nettskjema_mcp.config import Settings, reset_settings
from nettskjema_mcp.errors import AuthenticationError


@pytest.fixture
def settings() -> Settings:
    """Return test settings with valid credentials."""
    return Settings(
        base_url="https://nettskjema.no/api/v3",
        auth_url="https://authorization.nettskjema.no/oauth2/token",
        client_id="test-client",
        client_secret="test-secret",
        timeout=30.0,
        log_level="INFO",
        max_answer_rows=1000,
    )


@pytest.fixture
def settings_no_creds() -> Settings:
    """Return test settings with missing credentials."""
    return Settings(
        base_url="https://nettskjema.no/api/v3",
        auth_url="https://authorization.nettskjema.no/oauth2/token",
        client_id=None,
        client_secret=None,
        timeout=30.0,
        log_level="INFO",
        max_answer_rows=1000,
    )


@pytest.fixture(autouse=True)
def reset_time_monotonic() -> None:
    """Reset time.monotonic patch after each test."""
    # Reset to real implementation
    import time

    auth._now = time.monotonic


@pytest.fixture(autouse=True)
def reset_config() -> None:
    """Reset cached settings after each test."""
    reset_settings()


async def test_fetches_and_returns_access_token(settings: Settings) -> None:
    """Test that TokenProvider fetches and returns the access token."""
    with respx.mock:
        route = respx.post("https://authorization.nettskjema.no/oauth2/token").mock(
            return_value=httpx.Response(
                200,
                json={"access_token": "test-token-123", "expires_in": 86400},
            )
        )

        async with httpx.AsyncClient() as client:
            provider = auth.TokenProvider(client, settings)
            token = await provider.token()

        assert token == "test-token-123"
        assert route.call_count == 1

        # Verify the request used HTTP basic auth and client_credentials grant
        request = route.calls[0].request
        assert request.headers["authorization"] == "Basic dGVzdC1jbGllbnQ6dGVzdC1zZWNyZXQ="
        content = request.content.decode("utf-8")
        assert "grant_type=client_credentials" in content


async def test_second_call_uses_the_cache(settings: Settings) -> None:
    """Test that a second token() call uses the cached token."""
    with respx.mock:
        route = respx.post("https://authorization.nettskjema.no/oauth2/token").mock(
            return_value=httpx.Response(
                200,
                json={"access_token": "cached-token", "expires_in": 86400},
            )
        )

        async with httpx.AsyncClient() as client:
            provider = auth.TokenProvider(client, settings)
            token1 = await provider.token()
            token2 = await provider.token()

        assert token1 == "cached-token"
        assert token2 == "cached-token"
        assert route.call_count == 1


async def test_expired_token_is_refetched(settings: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that an expired token triggers a refetch."""
    # Start at time 0
    fake_time = 0.0

    def mock_now() -> float:
        return fake_time

    monkeypatch.setattr(auth, "_now", mock_now)

    with respx.mock:
        route = respx.post("https://authorization.nettskjema.no/oauth2/token").mock(
            side_effect=[
                httpx.Response(200, json={"access_token": "first-token", "expires_in": 86400}),
                httpx.Response(200, json={"access_token": "second-token", "expires_in": 86400}),
            ]
        )

        async with httpx.AsyncClient() as client:
            provider = auth.TokenProvider(client, settings)

            # First call at time 0
            token1 = await provider.token()
            assert token1 == "first-token"
            assert route.call_count == 1

            # Advance past expiry (86400s) minus the buffer (3600s), plus a bit more
            fake_time = 86400 - auth.REFRESH_BUFFER_SECONDS + 1

            # Second call should refetch
            token2 = await provider.token()
            assert token2 == "second-token"
            assert route.call_count == 2


async def test_refresh_buffer_refetches_an_hour_early(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test that the refresh buffer causes refetch before actual expiry."""
    fake_time = 0.0

    def mock_now() -> float:
        return fake_time

    monkeypatch.setattr(auth, "_now", mock_now)

    with respx.mock:
        route = respx.post("https://authorization.nettskjema.no/oauth2/token").mock(
            side_effect=[
                httpx.Response(200, json={"access_token": "token-1", "expires_in": 86400}),
                httpx.Response(200, json={"access_token": "token-2", "expires_in": 86400}),
            ]
        )

        async with httpx.AsyncClient() as client:
            provider = auth.TokenProvider(client, settings)

            token1 = await provider.token()
            assert token1 == "token-1"

            # Advance to 3000 seconds inside the 3600s buffer
            # Token expires at 86400, buffer starts at 86400-3600 = 82800
            # So at 83000 we're 200 seconds inside the buffer
            fake_time = 83000

            token2 = await provider.token()
            assert token2 == "token-2"
            assert route.call_count == 2


async def test_missing_credentials_raises_authentication_error(
    settings_no_creds: Settings,
) -> None:
    """Test that missing credentials raise AuthenticationError on token()."""
    async with httpx.AsyncClient() as client:
        provider = auth.TokenProvider(client, settings_no_creds)

        with pytest.raises(
            AuthenticationError,
            match="NETTSKJEMA_CLIENT_ID.*NETTSKJEMA_CLIENT_SECRET",
        ):
            await provider.token()


async def test_401_from_token_endpoint_raises_authentication_error(settings: Settings) -> None:
    """Test that a 401 from the token endpoint raises AuthenticationError."""
    with respx.mock:
        respx.post("https://authorization.nettskjema.no/oauth2/token").mock(
            return_value=httpx.Response(401, json={"error": "invalid_client"})
        )

        async with httpx.AsyncClient() as client:
            provider = auth.TokenProvider(client, settings)

            with pytest.raises(AuthenticationError):
                await provider.token()


async def test_invalidate_forces_a_refetch(settings: Settings) -> None:
    """Test that invalidate() clears the cache and forces a refetch."""
    with respx.mock:
        route = respx.post("https://authorization.nettskjema.no/oauth2/token").mock(
            side_effect=[
                httpx.Response(200, json={"access_token": "first", "expires_in": 86400}),
                httpx.Response(200, json={"access_token": "second", "expires_in": 86400}),
            ]
        )

        async with httpx.AsyncClient() as client:
            provider = auth.TokenProvider(client, settings)

            token1 = await provider.token()
            assert token1 == "first"
            assert route.call_count == 1

            # Invalidate should clear the cache
            provider.invalidate()

            # Next call should refetch
            token2 = await provider.token()
            assert token2 == "second"
            assert route.call_count == 2


async def test_concurrent_callers_fetch_once(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test that concurrent token() calls result in a single fetch."""
    # Make the response slow enough that the race is real
    async def slow_response(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(0.1)
        return httpx.Response(200, json={"access_token": "concurrent-token", "expires_in": 86400})

    with respx.mock:
        route = respx.post("https://authorization.nettskjema.no/oauth2/token").mock(
            side_effect=slow_response
        )

        async with httpx.AsyncClient() as client:
            provider = auth.TokenProvider(client, settings)

            # Launch two concurrent calls
            token1, token2 = await asyncio.gather(provider.token(), provider.token())

        assert token1 == "concurrent-token"
        assert token2 == "concurrent-token"
        assert route.call_count == 1
