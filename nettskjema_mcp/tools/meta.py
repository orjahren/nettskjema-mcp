"""Meta tools: who the credentials belong to, and how the server is configured.

This module is the template every other tool module follows:

* Call ``get_client()`` **inside** the tool body, never at module level. A
  client built at import time would bind settings before ``main()`` has read
  the environment, which is exactly the import-time trap ``get_settings()``
  exists to avoid. Same for ``get_settings()`` itself.
* Register with ``@tool`` from :mod:`nettskjema_mcp.server`, not ``@mcp.tool``:
  ``@tool`` routes the body through the error bridge, so a typed error reaches
  the model with its per-field detail intact. A contract test enforces this.
* Put ``@endpoint(...)`` *below* ``@tool`` so it records the undecorated
  function's name. A tool that issues no request has no ``@endpoint`` and is
  listed in ``LOCAL_TOOLS`` instead.
* Raise the typed errors from :mod:`nettskjema_mcp.errors` and never catch
  them; the bridge translates them.
* Annotate read-only tools with ``{"readOnlyHint": True}``.
* Return a string. ``dump()`` renders a decoded body as pretty JSON.
"""

import logging

from nettskjema_mcp.client import dump, get_client
from nettskjema_mcp.config import get_settings
from nettskjema_mcp.routes import Route, endpoint
from nettskjema_mcp.server import tool

logger = logging.getLogger(__name__)

ME = Route("GET", "/me")

# The two variables the client credentials flow needs. Named here so the
# diagnostic can tell the caller exactly what to set.
CREDENTIAL_VARIABLES = ("NETTSKJEMA_CLIENT_ID", "NETTSKJEMA_CLIENT_SECRET")


@tool(annotations={"readOnlyHint": True})
@endpoint(ME)
async def get_user_info() -> str:
    """
    Get the Nettskjema user record for the authenticated API client.

    Returns:
        The user record as JSON.
    """
    return dump(await get_client().json(ME))


@tool(annotations={"readOnlyHint": True})
async def check_auth_status() -> str:
    """
    Report which Nettskjema credentials and URLs this server is configured with.

    Makes no request, so it still answers when authentication is the thing that
    is broken. The client secret is never included: only whether it is set.

    Returns:
        A JSON object describing the current configuration, the names of any
        missing environment variables, and whether the server is ready to call
        the API.
    """
    settings = get_settings()
    missing = [
        name
        for name, value in zip(
            CREDENTIAL_VARIABLES, (settings.client_id, settings.client_secret), strict=True
        )
        if not value
    ]
    status: dict[str, object] = {
        "baseUrl": settings.base_url,
        "authUrl": settings.auth_url,
        "clientId": settings.client_id,
        "clientIdSet": settings.client_id is not None and settings.client_id != "",
        "clientSecretSet": settings.client_secret is not None and settings.client_secret != "",
        "clientUsername": f"{settings.client_id}@apiclient" if settings.client_id else None,
        "missingEnvironmentVariables": missing,
        "ready": not missing,
    }
    if missing:
        status["hint"] = (
            f"Set {' and '.join(missing)} in the environment or in a .env file. "
            "Credentials are issued at https://authorization.nettskjema.no/."
        )
    return dump(status)
