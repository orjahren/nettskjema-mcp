"""Form read tools: listing, lookup, and fetching form metadata and structure."""

from nettskjema_mcp.client import dump, get_client
from nettskjema_mcp.routes import Route, endpoint
from nettskjema_mcp.server import tool

LIST_MY_FORMS = Route("GET", "/form/me")
LOOKUP_BY_TITLE = Route("GET", "/form/titleshort/{titleShort}")
FORM_INFO = Route("GET", "/form/{formId}/info")
FORM_SETTINGS = Route("GET", "/form/{formId}/settings")
FORM_SETTINGS_VALIDATION = Route("GET", "/form/{formId}/settings/validation")
FORM_DEFINITION = Route("GET", "/form/{formId}/definition")
PERSONAL_DATA = Route("GET", "/personal-data/collects-personal-data")


@tool(annotations={"readOnlyHint": True})
@endpoint(LIST_MY_FORMS)
async def list_my_forms() -> str:
    """
    List all forms owned by the authenticated API client.

    Returns:
        An array of form metadata objects as JSON, each with formId, title, and status.
    """
    return dump(await get_client().json(LIST_MY_FORMS))


@tool(annotations={"readOnlyHint": True})
@endpoint(LOOKUP_BY_TITLE)
async def lookup_form_by_title(title_short: str) -> str:
    """
    Look up a form by its short title (the URL-safe identifier).

    Args:
        title_short: The form's titleShort, as it appears in the form's public URL.

    Returns:
        The form metadata as JSON, with formId, title, and other basic fields.
    """
    return dump(await get_client().json(LOOKUP_BY_TITLE, path={"titleShort": title_short}))


@tool(annotations={"readOnlyHint": True})
@endpoint(FORM_INFO)
async def get_form_info(form_id: int) -> str:
    """
    Get basic information about a form: owner, creation date, and access settings.

    Args:
        form_id: The form's numeric ID.

    Returns:
        The form info as JSON, including owner, created timestamp, and visibility flags.
    """
    return dump(await get_client().json(FORM_INFO, path={"formId": form_id}))


@tool(annotations={"readOnlyHint": True})
@endpoint(FORM_SETTINGS)
async def get_form_settings(form_id: int, is_for_create_form: bool = False) -> str:
    """
    Get the form's settings: title, description, notifications, and data retention policy.

    Args:
        form_id: The form's numeric ID.
        is_for_create_form: Whether to return settings suitable for creating a new form.

    Returns:
        The form settings as JSON, including title, description, and configuration options.
    """
    return dump(
        await get_client().json(
            FORM_SETTINGS,
            path={"formId": form_id},
            query={"is-for-create-form": is_for_create_form if is_for_create_form else None},
        )
    )


@tool(annotations={"readOnlyHint": True})
@endpoint(FORM_SETTINGS_VALIDATION)
async def get_form_settings_validation(form_id: int) -> str:
    """
    Get the validation rules configured for the form's settings.

    Args:
        form_id: The form's numeric ID.

    Returns:
        The validation constraints as JSON, describing which settings are required or restricted.
    """
    return dump(await get_client().json(FORM_SETTINGS_VALIDATION, path={"formId": form_id}))


@tool(annotations={"readOnlyHint": True})
@endpoint(FORM_DEFINITION)
async def get_form_definition(form_id: int) -> str:
    """
    Get the form's complete structure: all elements, their types, options, and ordering.

    Args:
        form_id: The form's numeric ID.

    Returns:
        The form definition as JSON, with a elements array describing the form's structure.
    """
    return dump(await get_client().json(FORM_DEFINITION, path={"formId": form_id}))


@tool(annotations={"readOnlyHint": True})
@endpoint(PERSONAL_DATA)
async def list_forms_collecting_personal_data(
    anonymous: bool | None = None,
    inactive_personal_data_suspected: bool | None = None,
) -> str:
    """
    List forms that collect personal data, with optional filters.

    Args:
        anonymous: Filter to anonymous (True) or non-anonymous (False) forms, or None for all.
        inactive_personal_data_suspected: Filter to forms suspected of collecting data when
            inactive (True), or exclude those (False), or None for all.

    Returns:
        An array of form records as JSON, each flagging its personal data collection status.
    """
    return dump(
        await get_client().json(
            PERSONAL_DATA,
            query={
                "anonymous": anonymous,
                "inactive-personal-data-suspected": inactive_personal_data_suspected,
            },
        )
    )
