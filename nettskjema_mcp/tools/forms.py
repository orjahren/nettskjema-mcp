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
        An array of form summary objects as JSON. Each object includes formId, title,
        open (boolean), modifiedDate, lastSubmissionDate, numberOfDeliveredSubmissions,
        deliveryDestination, and myFormsFormListingGroup.
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
        A mapping object as JSON. The schema defines it as an object with integer values.
    """
    return dump(await get_client().json(LOOKUP_BY_TITLE, path={"titleShort": title_short}))


@tool(annotations={"readOnlyHint": True})
@endpoint(FORM_INFO)
async def get_form_info(form_id: int) -> str:
    """
    Get operational metadata about a form: submission counts, open/closed status, and edit permissions.

    Args:
        form_id: The form's numeric ID.

    Returns:
        Form metadata as JSON, including title, isOpen, canEditForm, numberOfSubmissions,
        numberOfInvitations, hasSubmissions, modifiedBy, modifiedDate, lastSubmissionDate,
        deleteDate, and deliveryDestination. Does not include creation date or owner.
    """
    return dump(await get_client().json(FORM_INFO, path={"formId": form_id}))


@tool(annotations={"readOnlyHint": True})
@endpoint(FORM_SETTINGS)
async def get_form_settings(form_id: int, is_for_create_form: bool = False) -> str:
    """
    Get the form's configuration: all 51 settings controlling form behavior and permissions.

    Args:
        form_id: The form's numeric ID.
        is_for_create_form: Whether to return settings suitable for creating a new form.

    Returns:
        The form settings as JSON, including title, editors, editorsSubmissionEmailType,
        emailInvitationText, emailReminderText, deleteSubmissionsAfterNumberOfDays,
        personalDataPurposeDescription, openFrom, openTo, maxSubmissionsForm, languageCode,
        and 40 other configuration fields. Does not include a plain description field.
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
    Get validation errors or constraints for the form's settings.

    Args:
        form_id: The form's numeric ID.

    Returns:
        An error message object as JSON, with message (string), errors (object), and
        confirmForceCleanupErrors fields, describing validation issues or constraints.
    """
    return dump(await get_client().json(FORM_SETTINGS_VALIDATION, path={"formId": form_id}))


@tool(annotations={"readOnlyHint": True})
@endpoint(FORM_DEFINITION)
async def get_form_definition(form_id: int) -> str:
    """
    Get the form's structure and creation history: the elements array and authorship metadata.

    Args:
        form_id: The form's numeric ID.

    Returns:
        The form definition as JSON, including elements (array of form elements with their
        types and configuration), createdBy, createdDate, modifiedBy, modifiedDate, editors,
        title, formType, version, languageCode, and personal data settings. Includes creation
        date and author, unlike get_form_info.
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
        An array of form records as JSON. Each object includes formId, deliveryDestination,
        editors, numberOfDeliveredSubmissions, openFrom, openTo, personalDataPurposeDescription,
        personalDataSharedOutsideWith, purposes, and lastSubmissionDate.
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
