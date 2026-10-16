# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Oliver Ruste Jahren
"""Model Context Protocol server for the Nettskjema v3 API.

The server itself lives in :mod:`nettskjema_mcp.server` and the tools in
:mod:`nettskjema_mcp.tools`. This module only re-exports the entry point, so
that importing the package stays cheap and free of side effects beyond tool
registration.
"""

from nettskjema_mcp.server import main, mcp

__version__ = "0.1.0"

__all__ = ["__version__", "main", "mcp"]
