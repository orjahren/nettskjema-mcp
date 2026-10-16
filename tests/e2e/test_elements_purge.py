"""E2E test for PUT /form/{formId}/elements keep-list semantics.

This test must establish whether omitted elements are deleted (keep-list
semantics) or left unchanged (merge semantics). The element tool docstrings
warn about keep-list behaviour, but that is an inference from the v1 API that
was never verified against v3. If this test fails, the docstrings are wrong.
"""

import pytest


@pytest.mark.e2e
async def test_put_elements_deletes_omitted_elements(temp_form: int) -> None:
    """
    Verify PUT /form/{formId}/elements uses keep-list semantics.

    Must establish: PUT with three elements, then PUT with only the first two;
    GET must return exactly two elements (the third is deleted). If GET returns
    three, the route uses merge semantics and the element docstrings must be
    updated to remove the keep-list warning.

    This is unfinished. The guard and fixtures are complete; the behaviour
    verification is deferred.
    """
    pytest.skip("Skeleton only — behaviour verification deferred")
