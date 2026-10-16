"""Pooled async HTTP client for the Nettskjema v3 API.

Every routed tool goes through :class:`NettskjemaClient`. It owns a single
``httpx.AsyncClient`` per process, attaches the OAuth2 bearer token, maps HTTP
statuses onto the typed error hierarchy, and offers four response shapes:

* :meth:`NettskjemaClient.json` for ordinary JSON endpoints,
* :meth:`NettskjemaClient.text` for plain-text endpoints such as SPSS syntax,
* :meth:`NettskjemaClient.binary` for file downloads, streamed to disk,
* :meth:`NettskjemaClient.ndjson` for streamed newline-delimited exports.
"""

import json
import logging
import mimetypes
import os
import tempfile
from pathlib import Path
from urllib.parse import quote

import httpx

from nettskjema_mcp.auth import TokenProvider
from nettskjema_mcp.config import Settings, get_settings
from nettskjema_mcp.errors import (
    BadRequestError,
    PartialSuccessError,
    UpstreamError,
    error_for_status,
)
from nettskjema_mcp.routes import Route

logger = logging.getLogger(__name__)

# Error bodies are quoted back to the caller. Cap the excerpt so an HTML error
# page from a proxy cannot flood a model's context window.
ERROR_BODY_EXCERPT_LIMIT = 500

# What a tool reports after a request that succeeded with no response body.
# Stable by contract: tools render this verbatim, so models can rely on it.
NO_CONTENT_RESULT: dict[str, object] = {"status": "success", "httpStatus": 204}

DEFAULT_MEDIA_TYPE = "application/octet-stream"

# The pair shape httpx accepts for query parameters.
_QueryParam = tuple[str, str | int | float | bool | None]


def dump(value: object) -> str:
    """
    Render a value as pretty-printed JSON for a tool's string return.

    Args:
        value: Any JSON-serialisable value.

    Returns:
        Indented JSON with non-ASCII characters left intact.
    """
    return json.dumps(value, ensure_ascii=False, indent=2)


def excerpt(text: str, limit: int = ERROR_BODY_EXCERPT_LIMIT) -> str:
    """
    Collapse whitespace and trim a body to a bounded excerpt.

    Args:
        text: Raw response body text.
        limit: Maximum number of characters to keep.

    Returns:
        A single-line excerpt, suffixed with a marker when it was trimmed.
    """
    collapsed = " ".join(text.split())
    if len(collapsed) <= limit:
        return collapsed
    return f"{collapsed[:limit]}… (truncated)"


def _decode_body(response: httpx.Response) -> object:
    """
    Parse a fully read response body without ever raising.

    A failure response is often not JSON at all — a gateway may answer with an
    HTML page — and a decode error raised on top of the real failure would hide
    it. Non-JSON bodies therefore degrade to a trimmed text excerpt.

    Args:
        response: A response whose content has already been read.

    Returns:
        The decoded JSON value, a trimmed text excerpt, or None for an empty body.
    """
    try:
        text = response.text
    except Exception:
        # Broad on purpose: a body we cannot even decode must not mask the real error.
        return "<undecodable response body>"
    if not text.strip():
        return None
    try:
        parsed: object = json.loads(text)
    except ValueError:
        return excerpt(text)
    return parsed


class NettskjemaClient:
    """An authenticated, connection-pooled client for the Nettskjema v3 API."""

    def __init__(self, settings: Settings | None = None) -> None:
        """
        Initialize the client.

        The underlying ``httpx.AsyncClient`` is created on first use, not here,
        so constructing a client performs no I/O and binds to no event loop.

        Args:
            settings: Configuration to use. Defaults to the process settings.
        """
        self._settings = settings if settings is not None else get_settings()
        self._http: httpx.AsyncClient | None = None
        self._tokens: TokenProvider | None = None

    async def aclose(self) -> None:
        """Close the pooled transport and drop the cached token provider."""
        if self._http is not None:
            await self._http.aclose()
            self._http = None
            self._tokens = None

    # ---------------------------------------------------------------- requests

    async def json(
        self,
        route: Route,
        *,
        path: dict[str, object] | None = None,
        query: dict[str, object] | None = None,
        body: object | None = None,
    ) -> object:
        """
        Call a JSON endpoint and return the decoded body.

        Args:
            route: The route to call.
            path: Values for the route's path placeholders.
            query: Query parameters; entries whose value is None are dropped.
            body: Request body. Sent as-is, so a list becomes a bare JSON array.

        Returns:
            The decoded JSON body, or NO_CONTENT_RESULT when the response was empty.

        Raises:
            NettskjemaError: For HTTP 207 and for any status outside 2xx.
        """
        request = await self._build_request(route, path, query, json_body=body)
        response = await self._send(request)
        payload = _decode_body(response)
        self._check_status(route, response, payload)
        if response.status_code == 204 or not response.content:
            return NO_CONTENT_RESULT
        return payload

    async def text(
        self,
        route: Route,
        *,
        path: dict[str, object] | None = None,
        query: dict[str, object] | None = None,
    ) -> str:
        """
        Call an endpoint and return its body as text, unchanged.

        Args:
            route: The route to call.
            path: Values for the route's path placeholders.
            query: Query parameters; entries whose value is None are dropped.

        Returns:
            The response body verbatim, including surrounding whitespace.

        Raises:
            NettskjemaError: For HTTP 207 and for any status outside 2xx.
        """
        request = await self._build_request(route, path, query, accept="text/plain, */*")
        response = await self._send(request)
        self._check_status(route, response, _decode_body(response))
        return response.text

    async def ndjson(
        self,
        route: Route,
        *,
        path: dict[str, object] | None = None,
        query: dict[str, object] | None = None,
        max_rows: int | None = None,
    ) -> dict[str, object]:
        """
        Stream a newline-delimited JSON export, one object per line.

        The body is consumed line by line so a large answer export is never held
        whole in memory. ``truncated`` is True in two cases: the row cap was
        reached, or the stream ended on a line that is not valid JSON — a cut-off
        export. A partial final line is reported, never silently included.

        Args:
            route: The route to call.
            path: Values for the route's path placeholders.
            query: Query parameters; entries whose value is None are dropped.
            max_rows: Row cap. Defaults to ``settings.max_answer_rows``.

        Returns:
            ``{"rows": [...], "rowCount": int, "truncated": bool}``.

        Raises:
            NettskjemaError: For HTTP 207 and for any status outside 2xx.
        """
        cap = max_rows if max_rows is not None else self._settings.max_answer_rows
        request = await self._build_request(
            route, path, query, accept="application/x-ndjson, application/json"
        )
        rows: list[object] = []
        truncated = False

        response = await self._send(request, stream=True)
        try:
            await self._check_streamed_status(route, response)
            async for line in response.aiter_lines():
                stripped = line.strip()
                if not stripped:
                    continue
                if len(rows) >= cap:
                    truncated = True
                    break
                try:
                    rows.append(json.loads(stripped))
                except ValueError:
                    # The export was cut short mid-line. Report it rather than
                    # presenting a partial export as a complete one.
                    logger.warning(
                        "NDJSON stream for %s ended on an incomplete line after %d rows",
                        route.path,
                        len(rows),
                    )
                    truncated = True
                    break
        finally:
            await response.aclose()

        return {"rows": rows, "rowCount": len(rows), "truncated": truncated}

    async def binary(
        self,
        route: Route,
        *,
        path: dict[str, object] | None = None,
        query: dict[str, object] | None = None,
        body: bytes | None = None,
        output_path: str | None = None,
    ) -> dict[str, object]:
        """
        Download a file, streaming it to disk rather than into the reply.

        A multi-megabyte workbook inlined as base64 is useless to a model, so the
        file path is returned instead. ``output_path`` is validated *before* the
        request is issued, so an unusable destination fails without spending a
        possibly expensive export on the server.

        Args:
            route: The route to call.
            path: Values for the route's path placeholders.
            query: Query parameters; entries whose value is None are dropped.
            body: Pre-serialised request body, if the endpoint takes one.
            output_path: Destination file. A temp file is used when omitted.

        Returns:
            ``{"path": str, "bytes": int, "mediaType": str}``.

        Raises:
            BadRequestError: If output_path's parent is missing or not writable.
            NettskjemaError: For HTTP 207 and for any status outside 2xx.
        """
        target = _validate_output_path(output_path) if output_path is not None else None

        request = await self._build_request(route, path, query, content=body, accept="*/*")
        response = await self._send(request, stream=True)
        try:
            await self._check_streamed_status(route, response)
            media_type = _media_type(response)
            if target is None:
                target = _temp_target(response, media_type)
            written = 0
            with target.open("wb") as handle:
                async for chunk in response.aiter_bytes():
                    handle.write(chunk)
                    written += len(chunk)
        finally:
            await response.aclose()

        logger.debug("Wrote %d bytes from %s to %s", written, route.path, target)
        return {"path": str(target), "bytes": written, "mediaType": media_type}

    # ---------------------------------------------------------------- internals

    def _client(self) -> httpx.AsyncClient:
        """Return the pooled transport, creating it on first use."""
        if self._http is None:
            self._http = httpx.AsyncClient(timeout=self._settings.timeout)
            self._tokens = TokenProvider(self._http, self._settings)
        return self._http

    def _token_provider(self) -> TokenProvider:
        """Return the token provider bound to the pooled transport."""
        self._client()
        assert self._tokens is not None  # created alongside the transport
        return self._tokens

    def _url(self, route: Route, path: dict[str, object] | None) -> str:
        """Substitute path placeholders and join the result onto the base URL."""
        rendered = route.path
        for name, value in (path or {}).items():
            placeholder = "{" + name + "}"
            if placeholder not in rendered:
                raise BadRequestError(
                    f"Unknown path parameter {name!r} for {route.method} {route.path}."
                )
            rendered = rendered.replace(placeholder, quote(str(value), safe=""))
        if "{" in rendered:
            raise BadRequestError(
                f"Missing path parameter(s) for {route.method} {route.path}: "
                f"nothing was supplied for {_unfilled(rendered)}."
            )
        return f"{self._settings.base_url.rstrip('/')}{rendered}"

    async def _build_request(
        self,
        route: Route,
        path: dict[str, object] | None,
        query: dict[str, object] | None,
        *,
        json_body: object | None = None,
        content: bytes | None = None,
        accept: str = "application/json",
    ) -> httpx.Request:
        """Build an authenticated request for a route."""
        url = self._url(route, path)
        token = await self._token_provider().token()
        headers = {"Authorization": f"Bearer {token}", "Accept": accept}
        params = _query_params(query)
        return self._client().build_request(
            route.method,
            url,
            params=params or None,
            json=json_body,
            content=content,
            headers=headers,
        )

    async def _send(self, request: httpx.Request, *, stream: bool = False) -> httpx.Response:
        """Dispatch a request, translating transport failures into typed errors."""
        try:
            return await self._client().send(request, stream=stream)
        except httpx.TimeoutException as exc:
            raise UpstreamError(
                f"The Nettskjema API did not respond within {self._settings.timeout}s."
            ) from exc
        except httpx.RequestError as exc:
            raise UpstreamError(
                f"Could not reach the Nettskjema API: {type(exc).__name__}."
            ) from exc

    def _check_status(self, route: Route, response: httpx.Response, payload: object) -> None:
        """
        Raise the typed error for a non-success status.

        207 is a 2xx, so ``raise_for_status()`` never fires on it. It means some
        changes were applied and others rejected; reporting that as a complete
        success would be wrong, so it is checked first and raised explicitly with
        the body attached.
        """
        status = response.status_code
        if status == 207:
            detail = payload if isinstance(payload, str) else dump(payload)
            raise PartialSuccessError(
                f"Partial success (HTTP 207) for {route.method} {route.path}: some changes "
                f"were applied and others were rejected. Response: {excerpt(detail)}",
                status=207,
                field_errors=_field_errors(payload),
            )
        if 200 <= status < 300:
            return
        raise error_for_status(status, _error_body(route, response, payload))

    async def _check_streamed_status(self, route: Route, response: httpx.Response) -> None:
        """Read and raise on a streamed response that did not succeed."""
        if response.status_code == 207 or not (200 <= response.status_code < 300):
            await response.aread()
            self._check_status(route, response, _decode_body(response))


def _error_body(route: Route, response: httpx.Response, payload: object) -> object:
    """
    Shape an error body for ``error_for_status``.

    A dict body carries the backend's own message and field errors and is passed
    through. Anything else — an HTML proxy page, an empty body — is turned into a
    self-describing string so the caller still learns what failed and where.
    """
    if isinstance(payload, dict):
        return payload
    where = f"{route.method} {route.path}"
    reason = response.reason_phrase or "error"
    if isinstance(payload, str) and payload:
        return f"HTTP {response.status_code} {reason} from {where}: {payload}"
    return f"HTTP {response.status_code} {reason} from {where} (empty response body)."


def _query_params(query: dict[str, object] | None) -> list[_QueryParam]:
    """
    Flatten query parameters into pairs, dropping None values.

    A list value becomes one pair per item, which is how the API expects
    repeated parameters such as several element ids.

    Args:
        query: Raw query parameters, possibly containing None and list values.

    Returns:
        A list of (name, value) pairs ready for httpx.
    """
    pairs: list[_QueryParam] = []
    for name, value in (query or {}).items():
        if value is None:
            continue
        if isinstance(value, (list, tuple)):
            pairs.extend((name, _param_str(item)) for item in value if item is not None)
        else:
            pairs.append((name, _param_str(value)))
    return pairs


def _param_str(value: object) -> str:
    """Render a single query value, spelling booleans the way the API reads them."""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _field_errors(payload: object) -> dict[str, list[str]] | None:
    """Extract per-field errors from a body, if it carries any."""
    if isinstance(payload, dict):
        errors = payload.get("errorKeysAndErrorMessages")
        if isinstance(errors, dict):
            return errors
    return None


def _unfilled(rendered: str) -> str:
    """Name the placeholders still present in a partially rendered path."""
    names = [part.split("}")[0] for part in rendered.split("{")[1:] if "}" in part]
    return ", ".join(names) or "an unnamed parameter"


def _validate_output_path(output_path: str) -> Path:
    """
    Check that a destination file can plausibly be written.

    Args:
        output_path: The requested destination.

    Returns:
        The resolved destination path.

    Raises:
        BadRequestError: If the parent is missing, is not a directory, is not
            writable, or the destination itself is a directory.
    """
    target = Path(output_path).expanduser()
    parent = target.parent
    if not parent.is_dir():
        raise BadRequestError(
            f"Cannot write to {output_path!r}: the directory {str(parent)!r} does not exist. "
            "Create it first, or choose a path inside an existing directory."
        )
    if not os.access(parent, os.W_OK):
        raise BadRequestError(
            f"Cannot write to {output_path!r}: the directory {str(parent)!r} is not writable."
        )
    if target.is_dir():
        raise BadRequestError(
            f"Cannot write to {output_path!r}: that path is an existing directory."
        )
    return target


def _media_type(response: httpx.Response) -> str:
    """Return the response media type without any charset parameter."""
    header = response.headers.get("content-type", "")
    media_type = header.split(";")[0].strip()
    return media_type or DEFAULT_MEDIA_TYPE


def _temp_target(response: httpx.Response, media_type: str) -> Path:
    """Create an empty temp file with a suffix matching the response."""
    suffix = _suffix_for(response, media_type)
    handle, name = tempfile.mkstemp(prefix="nettskjema-", suffix=suffix)
    os.close(handle)
    return Path(name)


def _suffix_for(response: httpx.Response, media_type: str) -> str:
    """Pick a file suffix from the filename the server suggested, or the media type."""
    disposition = response.headers.get("content-disposition", "")
    if "filename=" in disposition:
        filename = disposition.split("filename=", 1)[1].strip().strip('";')
        suffix = Path(filename).suffix
        if suffix:
            return suffix
    return mimetypes.guess_extension(media_type) or ".bin"


_client_cache: NettskjemaClient | None = None


def get_client() -> NettskjemaClient:
    """
    Get the process-wide client, creating it on first call.

    One instance means one connection pool and one cached access token for the
    whole server. Use reset_client() to clear the cache (primarily for testing).

    Returns:
        The shared NettskjemaClient instance.
    """
    global _client_cache
    if _client_cache is None:
        _client_cache = NettskjemaClient()
    return _client_cache


def reset_client() -> None:
    """
    Clear the pooled client cache.

    This is primarily a test hook, mirroring config.reset_settings(). It does not
    close the discarded client: closing is async, so callers that created one
    should await aclose() on it first.
    """
    global _client_cache
    _client_cache = None


__all__ = [
    "NO_CONTENT_RESULT",
    "NettskjemaClient",
    "dump",
    "excerpt",
    "get_client",
    "reset_client",
]
