"""Element tools: reading a form's elements and writing them back.

There is no endpoint that adds, patches or deletes a single element. The only
write is ``PUT /form/{formId}/elements``, which **replaces the form's entire
element list**: anything missing from the request is deleted. Every element edit
is therefore a read-modify-write, and both write tools in this module say so in
their first line, because that docstring is the only warning a model gets before
it empties a form.
"""

from nettskjema_mcp.client import dump, get_client
from nettskjema_mcp.errors import NotFoundError, UpstreamError
from nettskjema_mcp.routes import Route, endpoint
from nettskjema_mcp.server import tool
from nettskjema_mcp.validation import validate_body

LIST_ELEMENTS = Route("GET", "/form/{formId}/elements")
PUT_ELEMENTS = Route("PUT", "/form/{formId}/elements")

# How many existing element ids to name when the requested one is absent. Enough
# for the caller to spot its mistake, bounded so a 400-element form cannot flood
# a model's context.
MAX_IDS_LISTED = 25


def _element_list(payload: object, form_id: int) -> list[dict[str, object]]:
    """
    Narrow a GET response to a list of element objects.

    Args:
        payload: The decoded body of ``GET /form/{formId}/elements``.
        form_id: The form the body came from, for the error message.

    Returns:
        The elements, as a list of dicts.

    Raises:
        UpstreamError: If the body is not an array of objects. Guessing at a
            different shape here would produce a PUT body built from nothing,
            which this endpoint would apply by emptying the form.
    """
    if not isinstance(payload, list) or not all(isinstance(item, dict) for item in payload):
        raise UpstreamError(
            f"GET {LIST_ELEMENTS.path} for form {form_id} did not answer with an array of "
            "element objects, so the element list cannot be safely rewritten."
        )
    # The isinstance check above holds for every item; this restates it for mypy.
    return [dict(item) for item in payload if isinstance(item, dict)]


@tool(annotations={"readOnlyHint": True})
@endpoint(LIST_ELEMENTS)
async def get_form_elements(form_id: int) -> str:
    """
    Get the form's elements: its questions, headings, images and page breaks.

    Use this before any element edit. The only write endpoint replaces the whole
    list, so the array returned here is the starting point for a modified list.

    Args:
        form_id: The form's numeric ID.

    Returns:
        An array of element objects as JSON. elementType is always present and is
        one of TEXT, IMAGE, HEADING, PAGE_BREAK, ACCORDION, RADIO, SELECT,
        CHECKBOX, MATRIX_RADIO, MATRIX_CHECKBOX, DATE, NAME, PHONE, EMAIL, NUMBER,
        QUESTION, USERNAME, ATTACHMENT, LINEAR_SCALE, NATIONAL_ID_NUMBER,
        QUESTION_MULTILINE or SUBMISSION_REFERENCE. Every other field is optional
        and depends on the type: elementId, questionId, externalElementId, text,
        description, sequence, isMandatory, isReadOnly, isHorizontal,
        isRandomizedOrder, isAutofill, isAnswerHashed, answerOptions,
        answerOptionsVisibilityFilter, subElements, validationScripts, image,
        imageUrl, imageAlignment, imageSize, altText, dateFormat,
        maxNumberOfCharacters, maxSelectedAnswerOptions, minimumValue,
        maximumValue, minimumValueText, midValueText, maximumValueText,
        linearScaleType, isRangeMarksShown, numberOfDecimals,
        nationalIdNumberType, nationalIdNumberOfDigits, nationalIdNumberOfLetters,
        repeatedNationalIdRequired, routingReferenceIds,
        sendAdditionalRecipientEmail and useForRedirectToForm.
    """
    # The spec declares no query parameter on this operation, and none is sent:
    # the path is served by two handlers and "?answer" would select the
    # respondent-facing view instead of the one this tool documents.
    return dump(await get_client().json(LIST_ELEMENTS, path={"formId": form_id}))


@tool(annotations={"destructiveHint": True})
@endpoint(PUT_ELEMENTS)
async def replace_form_elements(form_id: int, elements: list[dict[str, object]]) -> str:
    """
    Replace the form's ENTIRE element list. Every element you leave out is DELETED.

    This is not an "add an element" tool. Whatever you send becomes the form's
    complete content: any question, heading, image or page break that is not in
    `elements` is removed from the form. To add or change anything, call
    get_form_elements first, modify the array it returns, and send all of it back
    — or call update_form_element, which does that read-modify-write for one
    element. Sending a one-element list to a ten-element form deletes nine
    elements.

    Nothing locks the form in between: an edit made by someone else after your
    get_form_elements call is overwritten by this one without warning. The
    endpoint offers no version field, ETag or conditional header to detect that.

    Each element is checked against the vendored ElementDTO schema before the
    request is sent. elementType is required on every element; unknown field
    names are rejected locally, with close matches suggested.

    Args:
        form_id: The form's numeric ID.
        elements: The complete list of elements the form should have, in order.
            Anything missing from this list is deleted. Keep each existing
            element's elementId so the API updates it instead of recreating it.

    Returns:
        The endpoint's ErrorMessage object as JSON: message (string), errors (an
        object mapping field names to arrays of strings) and
        confirmForceCleanupErrors. The spec declares ErrorMessage as this
        endpoint's 200 response, so a successful call can still report per-field
        problems — read them rather than assuming the write was clean. A response
        with no body is reported as {"status": "success", "httpStatus": <code>}.
    """
    # Validated as an array, so each element is checked individually and the
    # error names the offending index.
    validate_body("ElementDTO", elements, as_array=True)

    # The body is the bare array: [{...}], not {"elements": [{...}]}.
    return dump(await get_client().json(PUT_ELEMENTS, path={"formId": form_id}, body=elements))


@tool(annotations={"destructiveHint": True})
@endpoint(LIST_ELEMENTS, PUT_ELEMENTS)
async def update_form_element(form_id: int, element_id: int, changes: dict[str, object]) -> str:
    """
    Change one element, by rewriting the form's ENTIRE element list.

    The API has no single-element update, so this tool reads every element, applies
    `changes` to the one whose elementId matches, and writes all of them back
    through the same whole-list PUT that replace_form_elements uses. The other
    elements are sent back exactly as they were read — but they are sent, so an
    edit someone else makes between the read and the write is silently
    overwritten. The operation is NOT atomic, and the endpoint offers no version
    field, ETag or conditional header that would detect the conflict.

    `changes` is merged shallowly, one level deep: each key replaces that key's
    value on the element outright. Nested lists are NOT merged item by item —
    passing `answerOptions` replaces the element's whole answer-option list, so to
    edit one option you must send all of them, each keeping its answerOptionId,
    in the order you want. The same goes for subElements and validationScripts.
    Fetch the element with get_form_elements first if you do not already have
    them.

    If no element in the form has the given element_id, nothing is written: a PUT
    of the unchanged list would report success while changing nothing.

    Args:
        form_id: The form's numeric ID.
        element_id: The elementId of the element to change. It must already exist
            in the form; this tool cannot create one.
        changes: The fields to set on that element, as a partial element object.
            Checked against the vendored ElementDTO schema before anything is
            read or written, so unknown field names are rejected locally.

    Returns:
        The PUT endpoint's ErrorMessage object as JSON: message (string), errors
        (an object mapping field names to arrays of strings) and
        confirmForceCleanupErrors. A response with no body is reported as
        {"status": "success", "httpStatus": <code>}.

    Raises:
        NotFoundError: If the form has no element with that elementId. No write is
            issued in that case.
    """
    # Validate first, so a typo costs nothing and never reaches the read-write
    # window. partial=True because changes is a subset of an element and need not
    # repeat elementType.
    validate_body("ElementDTO", changes, partial=True)

    client = get_client()
    current = _element_list(await client.json(LIST_ELEMENTS, path={"formId": form_id}), form_id)

    # The server's own elements are passed through untouched and deliberately not
    # revalidated: a field newer than the vendored snapshot would otherwise make
    # every read-modify-write on that form impossible to complete.
    updated: list[dict[str, object]] = []
    found = False
    for element in current:
        if element.get("elementId") == element_id:
            found = True
            element = {**element, **changes}
        updated.append(element)

    if not found:
        known = [e["elementId"] for e in current if "elementId" in e]
        shown = ", ".join(str(i) for i in known[:MAX_IDS_LISTED]) or "none"
        more = f" (and {len(known) - MAX_IDS_LISTED} more)" if len(known) > MAX_IDS_LISTED else ""
        raise NotFoundError(
            f"Form {form_id} has no element with elementId {element_id}, so nothing was "
            f"written. The form's element ids are: {shown}{more}. Use get_form_elements "
            "to see them, or replace_form_elements to add a new element — bearing in mind "
            "that it replaces the whole list."
        )

    return dump(await client.json(PUT_ELEMENTS, path={"formId": form_id}, body=updated))
