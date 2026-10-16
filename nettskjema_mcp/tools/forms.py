"""Form read tools: listing, lookup, and fetching form metadata and structure."""

from nettskjema_mcp.client import dump, get_client
from nettskjema_mcp.enums import FormType, RespondentGroup
from nettskjema_mcp.routes import Route, endpoint
from nettskjema_mcp.server import tool
from nettskjema_mcp.validation import validate_body

LIST_MY_FORMS = Route("GET", "/form/me")
LOOKUP_BY_TITLE = Route("GET", "/form/titleshort/{titleShort}")
FORM_INFO = Route("GET", "/form/{formId}/info")
FORM_SETTINGS = Route("GET", "/form/{formId}/settings")
FORM_SETTINGS_VALIDATION = Route("GET", "/form/{formId}/settings/validation")
FORM_DEFINITION = Route("GET", "/form/{formId}/definition")
PERSONAL_DATA = Route("GET", "/personal-data/collects-personal-data")
CREATE_FORM = Route("POST", "/form")
DELETE_FORMS = Route("DELETE", "/form")
UPDATE_SETTINGS = Route("PATCH", "/form/{formId}/settings")


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


@tool()
@endpoint(CREATE_FORM)
async def create_form(
    title: str,
    language_code: str,
    form_type: FormType,
    respondent_group: RespondentGroup,
    collects_personal_data: bool,
    sensitive_personal_data_collected: bool,
    extra_settings: dict[str, object] | None = None,
    elements: list[dict[str, object]] | None = None,
) -> str:
    """
    Create a new form with the given settings and optional elements.

    The six required settings are taken as named parameters so a model cannot omit them.
    Additional settings can be provided via extra_settings. If a required setting appears
    in extra_settings, the named parameter takes precedence.

    Args:
        title: The form's title.
        language_code: The form's language code (e.g., "en", "no").
        form_type: The form type.
        respondent_group: The respondent group (access control).
        collects_personal_data: Whether the form collects personal data.
        sensitive_personal_data_collected: Whether the form collects sensitive personal data.
        extra_settings: Additional settings beyond the six required ones.
        elements: Optional list of form elements to include when creating the form.

    Returns:
        The created form's ID as JSON. The response includes formId (integer).
    """
    # Build formSettings with the six required fields first, then merge extra_settings
    form_settings: dict[str, object] = {
        "title": title,
        "languageCode": language_code,
        "formType": form_type.value,
        "respondentGroup": respondent_group.value,
        "collectsPersonalData": collects_personal_data,
        "sensitivePersonalDataCollected": sensitive_personal_data_collected,
    }

    # Merge extra_settings, but required parameters take precedence
    if extra_settings:
        for key, value in extra_settings.items():
            if key not in form_settings:
                form_settings[key] = value

    # Validate formSettings against CreateFormSettingsDTO to reject unknown keys
    validate_body("CreateFormSettingsDTO", form_settings)

    # Assemble the FormSettingsAndElementsDTO shape
    body: dict[str, object] = {
        "formSettings": form_settings,
        "elements": elements or [],
    }

    # Validate the complete body shape
    validate_body("FormSettingsAndElementsDTO", body)

    return dump(await get_client().json(CREATE_FORM, body=body))


@tool(annotations={"destructiveHint": True})
@endpoint(DELETE_FORMS)
async def delete_forms(form_ids: list[int]) -> str:
    """
    Delete one or more forms by their IDs.

    Deleted forms are moved to the trash and can be restored for a limited time.
    This operation is destructive and cannot be undone after the trash retention
    period expires.

    Args:
        form_ids: A list of form IDs to delete.

    Returns:
        A success marker as JSON.
    """
    # Send the bare array: [1, 2, 3], not {"formIds": [1, 2, 3]}
    # The route has a days-in-trash-can query param, but we do not send it
    return dump(await get_client().json(DELETE_FORMS, body=form_ids))


@tool()
@endpoint(UPDATE_SETTINGS)
async def update_form_settings(
    form_id: int,
    settings: dict[str, object],
    force_cleanup: bool = False,
) -> str:
    """
    Update one or more settings on an existing form.

    This endpoint accepts partial updates: only the settings included in the settings
    dict will be updated. A 207 Multi-Status response means some settings were applied
    and others were rejected; this is reported as an error listing the failed settings.

    The settings dict is validated as a partial FormSettingsDTO before the request is
    sent. Required-field constraints are relaxed for partial updates, but unknown keys
    are rejected locally to catch typos and flag fields that are newer than the vendored
    spec snapshot.

    Args:
        form_id: The form's numeric ID.
        settings: A dict of settings to update. Only the settings included are changed.
        force_cleanup: Whether to force cleanup of conflicting settings.

    Returns:
        A success marker as JSON when all settings were applied (HTTP 204).
    """
    # Validate the settings dict as a partial FormSettingsDTO
    validate_body("FormSettingsDTO", settings, partial=True)

    return dump(
        await get_client().json(
            UPDATE_SETTINGS,
            path={"formId": form_id},
            query={"forceCleanup": force_cleanup if force_cleanup else None},
            body=settings,
        )
    )
