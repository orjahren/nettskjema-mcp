#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Oliver Ruste Jahren
"""Fetch the production OpenAPI spec and write it to nettskjema_mcp/spec/openapi.json."""

import json
import sys
from pathlib import Path

import httpx


def main() -> None:
    """Fetch production spec and write it pretty-printed with sorted keys."""
    spec_url = "https://nettskjema.no/api/v3/v3/api-docs"

    print(f"Fetching OpenAPI spec from {spec_url}...", file=sys.stderr)

    try:
        response = httpx.get(spec_url, timeout=30.0)
        response.raise_for_status()
    except httpx.HTTPError as e:
        print(f"Failed to fetch spec: {e}", file=sys.stderr)
        sys.exit(1)

    spec = response.json()

    # Determine output path relative to this script
    script_dir = Path(__file__).parent
    repo_root = script_dir.parent
    output_path = repo_root / "nettskjema_mcp" / "spec" / "openapi.json"

    # Ensure directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Write pretty-printed with sorted keys and trailing newline
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(spec, f, indent=2, sort_keys=True, ensure_ascii=False)
        f.write("\n")

    paths_count = len(spec.get("paths", {}))
    operations_count = sum(
        1
        for p in spec.get("paths", {}).values()
        for m in p
        if m in {"get", "post", "put", "patch", "delete"}
    )

    print(
        f"Wrote {output_path} ({paths_count} paths, {operations_count} operations)",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
