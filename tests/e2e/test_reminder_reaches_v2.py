"""E2E test for reminder reaching v2-created invitations.

The remind_all_pending_invitations tool works through the v1 invitation layer
over tables the v2 layer shares, so it most likely reaches v2-created
invitations — but that is an inference, not something the API states.

If this test fails, remind_all_pending_invitations is cut from the surface
before release and moved into OUT_OF_SCOPE with that reason.
"""

import pytest


@pytest.mark.e2e
async def test_remind_reaches_v2_created_invitations(temp_form: int, e2e_email: str) -> None:
    """
    Verify remind_all_pending_invitations reaches v2-created invitations.

    Must establish: create a v2 batch by calling
    /private/form/{formId}/invitations-v2 DIRECTLY from the test (the server
    avoids private endpoints, the harness need not), then call
    remind_all_pending_invitations and assert the invitation state changes.

    If this test fails, remind_all_pending_invitations is cut from the surface
    and moved into OUT_OF_SCOPE.

    This sends real invitations to e2e_email. It is unfinished. The guard and
    fixtures are complete; the behaviour verification is deferred.
    """
    pytest.skip("Skeleton only — behaviour verification deferred")
