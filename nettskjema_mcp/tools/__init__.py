# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Oliver Ruste Jahren
"""Tool modules for the Nettskjema MCP server.

Each module registers its own tools with the shared server when it is
imported; :mod:`nettskjema_mcp.server` imports them for that side effect.
Nothing is re-exported here, so importing this package alone registers
nothing and — importantly — cannot import the server back.
"""
