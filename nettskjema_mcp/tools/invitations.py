# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Oliver Ruste Jahren
"""Invitation reminder tool.

The tool sends reminder emails to every pending invitation on a form, in one
all-or-nothing operation. Creating, listing and deleting invitations are public
Nettskjema features — supported, documented, production-ready — but are not
exposed through this MCP server. Those operations are managed through the web
frontend instead.
"""

from nettskjema_mcp.client import dump, get_client
from nettskjema_mcp.routes import Route, endpoint
from nettskjema_mcp.server import tool

REMIND = Route("POST", "/form/{formId}/remind")


@tool(annotations={"destructiveHint": True})
@endpoint(REMIND)
async def remind_all_pending_invitations(form_id: int) -> str:
    """
    Send reminder emails to every pending invitation on a form.

    This operation is all-or-nothing: every sent invitation on the form receives
    a reminder. There is no endpoint to remind a subset of invitations. Whether
    it also reaches invitations created through the newer batch interface is not
    documented anywhere; they may share the same storage, but that is an
    inference and not something the API states.

    Creating, viewing and deleting invitations are not available through this MCP
    server. Those operations are public Nettskjema features — supported,
    documented, production-ready — but are managed through the web frontend
    instead. Use the form management interface to handle invitations:
    https://nettskjema.no/user/form/{formId}/collect-responses/invited/create
    and https://nettskjema.no/user/form/{formId}/collect-responses/invited/overview

    Args:
        form_id: The form's numeric ID.

    Returns:
        A success marker as JSON: {"status": "success", "httpStatus": 200}.
        The spec declares no response body for this operation.
    """
    return dump(await get_client().json(REMIND, path={"formId": form_id}))
