"""Tests for documentation accuracy and completeness.

The docs are the raw material a Claude skill will be written from, so their
accuracy is tested. These tests enforce:
- Every tool is documented in the API coverage table
- Dropped operations are explicitly listed as out-of-scope, not omitted
- The invitation gap is documented everywhere it must be
- Stale documentation is deleted
- No tools that no longer exist are mentioned in documentation
"""

import re
from pathlib import Path

from nettskjema_mcp.routes import LOCAL_TOOLS, OUT_OF_SCOPE, REGISTRY


def test_api_coverage_lists_every_tool() -> None:
    """API coverage must list every tool in REGISTRY and LOCAL_TOOLS."""
    text = Path("docs/api-coverage.md").read_text()
    for tool in set(REGISTRY) | LOCAL_TOOLS:
        assert tool in text, f"Tool {tool} not found in docs/api-coverage.md"


def test_api_coverage_lists_the_dropped_invitation_operations() -> None:
    """API coverage must list the out-of-scope invitation routes."""
    text = Path("docs/api-coverage.md").read_text()
    for method_path, _ in OUT_OF_SCOPE.items():
        _, path = method_path
        assert path in text, f"Out-of-scope path {path} not found in docs/api-coverage.md"
    # The reason must mention frontend
    assert "frontend" in text.lower(), "Out-of-scope reason must mention frontend"


def test_the_invitation_gap_is_documented_everywhere_it_must_be() -> None:
    """The invitation gap must appear in README and workflows."""
    for f in ("README.md", "docs/workflows.md"):
        text = Path(f).read_text()
        assert "collect-responses/invited" in text, f"{f} must document the frontend invitation URL"


def test_no_deleted_doc_survives() -> None:
    """Stale documentation files must be deleted."""
    for f in (
        "INTEGRATION_SUMMARY.md",
        "NEXTJS_INTEGRATION.md",
        "example_usage.py",
        "TESTING.md",
        "nextjs-example",
    ):
        assert not Path(f).exists(), f"Stale file {f} must be deleted"


def test_docs_do_not_mention_tools_that_do_not_exist() -> None:
    """Documentation must not mention removed tool names.

    CHANGELOG.md is exempt: naming what was removed is what a changelog is for.
    .venv, .superpowers, docs/superpowers, and worktrees are also exempt.
    """
    gone = {
        "add_form_element",
        "delete_form_element",
        "reorder_form_elements",
        "duplicate_form_element",
        "create_invitation",
        "get_invitations",
        "delete_invitations",
        "send_reminder",
    }
    for md in Path(".").rglob("*.md"):
        # Skip exempted paths
        if (
            md.name == "CHANGELOG.md"
            or ".venv" in md.parts
            or ".superpowers" in md.parts
            or ("docs" in md.parts and "superpowers" in md.parts)
            or "worktrees" in md.parts
        ):
            continue
        words = set(re.findall(r"\w+", md.read_text()))
        found = gone & words
        assert not found, f"{md}: mentions removed tools: {sorted(found)}"
