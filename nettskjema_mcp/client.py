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
    _extract_field_errors,
    error_for_status,
    error_for_success_body,
    trim_excerpt,
)
from nettskjema_mcp.routes import ERROR_BODY_ROUTES, Route

logger = logging.getLogger(__name__)

# Error bodies are quoted back to the caller. Cap the excerpt so an HTML error
# page from a proxy cannot flood a model's context window.
ERROR_BODY_EXCERPT_LIMIT = 500

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
    Collapse whitespace and trim a response body to a bounded excerpt.

    Args:
        text: Raw response body text.
        limit: Maximum number of characters to keep.

    Returns:
        A single-line excerpt, suffixed with a marker when it was trimmed.
    """
    return trim_excerpt(text, limit)


def no_content_result(status: int) -> dict[str, object]:
    """
    Build the success marker for a response that carried no body.

    Args:
        status: The actual HTTP status, so a bodiless 201 is not reported as 204.

    Returns:
        A small, stable dict that tools render verbatim.
    """
    return {"status": "success", "httpStatus": status}


# The canonical shape of a no-body success, for reference and tests. The value
# a tool actually sees carries the real status, which is usually but not always 204.
NO_CONTENT_RESULT: dict[str, object] = no_content_result(204)


class _NotJson:
    """
    A response body that could not be parsed as JSON, with a bounded excerpt.

    A distinct type rather than a bare string, so that a body which legitimately
    decodes to a JSON string is never mistaken for a parse failure.
    """

    __slots__ = ("text",)

    def __init__(self, text: str) -> None:
        """Store the bounded excerpt of the unparseable body."""
        self.text = text


def _decode_body(response: httpx.Response) -> object:
    """
    Parse a fully read response body without ever raising.

    A failure response is often not JSON at all — a gateway may answer with an
    HTML page — and a decode error raised on top of the real failure would hide
    it. Non-JSON bodies therefore degrade to a _NotJson excerpt, which the error
    path quotes and the success path rejects.

    Args:
        response: A response whose content has already been read.

    Returns:
        The decoded JSON value, a _NotJson marker, or None for an empty body.
    """
    try:
        text = response.text
    except Exception:
        # Broad on purpose: a body we cannot even decode must not mask the real error.
        return _NotJson("<undecodable response body>")
    if not text.strip():
        return None
    try:
        parsed: object = json.loads(text)
    except ValueError:
        return _NotJson(excerpt(text))
    return parsed


def _is_success(status: int) -> bool:
    """Report whether a status is a plain success. 207 is a 2xx but not a success."""
    return 200 <= status < 300 and status != 207


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
            The decoded JSON body, or a no-content marker when the body was empty.

        Raises:
            NettskjemaError: For HTTP 207 and for any status outside 2xx.
            PartialSuccessError: For a clean 2xx from a route in
                ERROR_BODY_ROUTES whose body reports the change was rejected.
            UpstreamError: If a successful response carried a body that is not JSON.
        """
        request = await self._build_request(route, path, query, json_body=body)
        response = await self._send(request)
        payload = _decode_body(response)
        self._check_status(route, response, payload)
        self._check_error_body(route, response, payload)
        if response.status_code == 204 or not response.content:
            return no_content_result(response.status_code)
        if isinstance(payload, _NotJson):
            # Reporting success with an HTML login or proxy page as the payload
            # would be worse than failing: the caller cannot tell it went wrong.
            raise UpstreamError(
                f"{route.method} {route.path} answered HTTP {response.status_code} with a "
                f"{_media_type(response)} body that is not JSON. A proxy or login page "
                f"most likely answered instead of the API. Body: {payload.text}",
                status=response.status_code,
            )
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
        if not _is_success(response.status_code):
            # Decoding is only worth its cost on the error path: these bodies are
            # large (an SPSS syntax export is plain text by design, not JSON).
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
        whole in memory. ``truncated`` is True in two cases, told apart by
        ``reason``: the row cap was reached (``"rowCap"``), or the connection
        closed cleanly on a line that is not valid JSON (``"incompleteFinalLine"``).
        A partial final line is reported, never silently included. A connection
        that breaks mid-body is a transport failure and raises instead.

        Args:
            route: The route to call.
            path: Values for the route's path placeholders.
            query: Query parameters; entries whose value is None are dropped.
            max_rows: Row cap. Defaults to ``settings.max_answer_rows``. Must be at
                least 1 when provided.

        Returns:
            ``{"rows": [...], "rowCount": int, "truncated": bool, "reason": str | None}``.

        Raises:
            BadRequestError: If max_rows is less than 1.
            NettskjemaError: For HTTP 207 and for any status outside 2xx.
            UpstreamError: If the connection fails while the body is streaming.
        """
        if max_rows is not None and max_rows < 1:
            raise BadRequestError(
                f"max_rows must be at least 1, got {max_rows}. "
                "To retrieve all rows, omit max_rows or set it to a large value."
            )
        cap = max_rows if max_rows is not None else self._settings.max_answer_rows
        request = await self._build_request(
            route, path, query, accept="application/x-ndjson, application/json"
        )
        rows: list[object] = []
        reason: str | None = None

        response = await self._send(request, stream=True)
        try:
            await self._check_streamed_status(route, response)
            async for line in response.aiter_lines():
                stripped = line.strip()
                if not stripped:
                    continue
                if len(rows) >= cap:
                    reason = "rowCap"
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
                    reason = "incompleteFinalLine"
                    break
        except httpx.RequestError as exc:
            # The loop runs after _send has returned, so transport failures land
            # here rather than in _send and must be translated here too.
            raise self._transport_error(exc) from exc
        finally:
            await response.aclose()

        return {
            "rows": rows,
            "rowCount": len(rows),
            "truncated": reason is not None,
            "reason": reason,
        }

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
            body: Pre-serialised request body, if the endpoint takes one. Sent as
                raw bytes with no content type, so a caller that supplies one must
                also pass the matching header itself. No route in the current spec
                needs this; the parameter exists for endpoints that may gain one.
            output_path: Destination file. A temp file is used when omitted.

        Returns:
            ``{"path": str, "bytes": int, "mediaType": str}``.

        Raises:
            BadRequestError: If output_path's parent is missing or not writable.
            NettskjemaError: For HTTP 207 and for any status outside 2xx.
            UpstreamError: If the connection fails while the body is streaming.
        """
        target = _validate_output_path(output_path) if output_path is not None else None

        request = await self._build_request(route, path, query, content=body, accept="*/*")
        response = await self._send(request, stream=True)
        written = 0
        # The file to clean up if the download does not complete. Set only once
        # the file is ours: a failure before that must not delete an existing file.
        partial: Path | None = None
        try:
            await self._check_streamed_status(route, response)
            media_type = _media_type(response)
            if target is None:
                target = _temp_target(response, media_type)
                partial = target
            with target.open("wb") as handle:
                partial = target
                async for chunk in response.aiter_bytes():
                    handle.write(chunk)
                    written += len(chunk)
            partial = None
        except BaseException as exc:
            # A half-written export must not be left behind looking complete.
            _discard_partial(partial)
            if isinstance(exc, httpx.RequestError):
                raise self._transport_error(exc) from exc
            raise
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
        try:
            # Acquiring the token is itself an HTTP call, so it needs the same
            # translation as the request it is about to authenticate.
            token = await self._token_provider().token()
        except httpx.RequestError as exc:
            raise self._transport_error(exc) from exc
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
        except httpx.RequestError as exc:
            raise self._transport_error(exc) from exc

    def _transport_error(self, exc: httpx.RequestError) -> UpstreamError:
        """
        Translate an httpx transport failure into a typed error.

        Shared by every stage that touches the network — token acquisition, the
        request itself, and the streaming loops that run after the response
        headers have arrived — so httpx exceptions never reach the tool layer.
        """
        if isinstance(exc, httpx.TimeoutException):
            return UpstreamError(
                f"The Nettskjema API did not respond within {self._settings.timeout}s."
            )
        return UpstreamError(f"Could not reach the Nettskjema API: {type(exc).__name__}.")

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
            raise PartialSuccessError(
                f"Partial success (HTTP 207) for {route.method} {route.path}: some changes "
                f"were applied and others were rejected. Response: {_detail_text(payload)}",
                status=207,
                field_errors=_field_errors(payload),
            )
        if _is_success(status):
            return
        raise error_for_status(status, _error_body(route, response, payload))

    def _check_error_body(self, route: Route, response: httpx.Response, payload: object) -> None:
        """
        Raise when a clean 2xx reports, in its body, that the change was rejected.

        Only routes listed in ``routes.ERROR_BODY_ROUTES`` are checked: they are
        the ones the vendored spec declares with an ErrorMessage success schema,
        where a 200 means "understood", not "applied". For every other route a
        2xx body is the result and must be returned untouched.
        """
        if route not in ERROR_BODY_ROUTES:
            return
        failure = error_for_success_body(
            f"{route.method} {route.path}", response.status_code, payload
        )
        if failure is not None:
            raise failure

    async def _check_streamed_status(self, route: Route, response: httpx.Response) -> None:
        """Read and raise on a streamed response that did not succeed."""
        if not _is_success(response.status_code):
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
    detail = _detail_text(payload)
    if detail:
        return f"HTTP {response.status_code} {reason} from {where}: {detail}"
    return f"HTTP {response.status_code} {reason} from {where} (empty response body)."


def _detail_text(payload: object) -> str:
    """Render any decoded body as a bounded single-line excerpt."""
    if payload is None:
        return ""
    if isinstance(payload, _NotJson):
        return payload.text
    if isinstance(payload, str):
        return excerpt(payload)
    return excerpt(dump(payload))


def _discard_partial(target: Path | None) -> None:
    """
    Remove a half-written download, best effort.

    Cleanup must never mask the error that caused it, so a failure to unlink is
    logged and swallowed.
    """
    if target is None:
        return
    try:
        target.unlink(missing_ok=True)
    except OSError as exc:
        logger.warning("Could not remove the partial download at %s: %s", target, exc)


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
    """
    Extract per-field errors from an ErrorMessage response body.

    The vendored spec documents errors as the field-error object in ErrorMessage.
    This function extracts and validates those errors, filtering out the spec's
    special properties (empty, all) that are not field errors.

    Args:
        payload: The decoded response body.

    Returns:
        A dict of field errors, or None if the body carries none.
    """
    if isinstance(payload, dict):
        errors_obj = payload.get("errors")
        if errors_obj is not None:
            field_errors = _extract_field_errors(errors_obj)
            if field_errors:
                return field_errors
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
        The resolved, absolute destination path.

    Raises:
        BadRequestError: If the parent is missing, is not a directory, is not
            writable, or the destination itself is a directory.
    """
    target = Path(output_path).expanduser().resolve()
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
    whole server. Use aclose_client() to tear it down (primarily for testing).

    Returns:
        The shared NettskjemaClient instance.
    """
    global _client_cache
    if _client_cache is None:
        _client_cache = NettskjemaClient()
    return _client_cache


async def aclose_client() -> None:
    """
    Close the pooled client and clear the cache.

    Prefer this over reset_client(): it closes the connection pool it discards.
    Safe to call when no client was ever created.
    """
    global _client_cache
    if _client_cache is not None:
        await _client_cache.aclose()
    _client_cache = None


def reset_client() -> None:
    """
    Clear the pooled client cache without closing it.

    This mirrors config.reset_settings() for synchronous call sites such as a
    pytest fixture that also serves non-async tests. Prefer aclose_client()
    wherever an await is possible: this one leaves an open connection pool behind
    if a client was created and never closed.
    """
    global _client_cache
    _client_cache = None


__all__ = [
    "NO_CONTENT_RESULT",
    "NettskjemaClient",
    "aclose_client",
    "dump",
    "excerpt",
    "get_client",
    "no_content_result",
    "reset_client",
]
