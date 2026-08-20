"""
mcp_server — expose Vera's SAFE tools to an MCP client (VS Code, Claude, …).

MCP is JSON-RPC 2.0 over stdio. We implement it with the standard library only —
no SDK, no pydantic/uvicorn/starlette pulled in — which keeps Vera lean, offline,
and fully in-house (matching its local-first, minimal-dependency posture).

Scope (deliberate, read-mostly): only tools that READ or THINK are exposed —
think_routes, list_projects, projects_needing_attention, plus the sandboxed
drive_read / drive_list. Anything that WRITES or RUNS (drive_write/run,
account/email actions) is withheld, so connecting Vera to an editor adds no new
risk surface. Acting still happens only through the drive the user launches.

Run:
  python -m cognitive_twin.mcp_server          # speaks MCP over stdio

VS Code / Claude Desktop config (mcpServers):
  "vera": { "command": "python", "args": ["-m", "cognitive_twin.mcp_server"] }

© Ankur Sinha. Personal use.
"""

from __future__ import annotations

import json
import sys
from typing import Any

# Import the CLI module for its side effect: it registers every skill into the
# shared registry. We then filter to the safe allow-list below.
from . import cli  # noqa: F401  (registers all skills)
from .skills.base import default_registry as R

PROTOCOL_VERSION = "2025-06-18"
SERVER_INFO = {"name": "vera", "version": "1.0.0"}

# The ONLY tools exposed over MCP — read/think, never write/run. Add to this list
# deliberately (and, for write tools, behind a confirm hook) — never widen by
# default. Keeping it explicit is the security boundary.
SAFE_TOOLS = {
    "think_routes",
    "list_projects",
    "projects_needing_attention",
    "drive_read",
    "drive_list",
}


def _safe_skills() -> dict[str, Any]:
    """The registry's skills, filtered to the safe allow-list that actually exist."""
    all_skills = getattr(R, "_skills", {})
    return {name: s for name, s in all_skills.items() if name in SAFE_TOOLS}


def _tool_list() -> list[dict[str, Any]]:
    """MCP `tools/list` shape: name, description, inputSchema (JSON schema)."""
    out = []
    for name, s in _safe_skills().items():
        out.append({
            "name": name,
            "description": s.description,
            "inputSchema": s.parameters or {"type": "object", "properties": {}},
        })
    return out


def _call_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """MCP `tools/call`: run a safe skill, return its text content. Refuses
    anything outside the allow-list even if the client asks — the boundary is
    enforced here, not trusted to the caller."""
    skills = _safe_skills()
    if name not in skills:
        return {
            "content": [{"type": "text", "text": f"Tool '{name}' is not exposed by Vera's MCP server (read/think tools only)."}],
            "isError": True,
        }
    try:
        result = skills[name].run(**(arguments or {}))
        return {"content": [{"type": "text", "text": str(result)}]}
    except Exception as exc:  # never crash the server on one bad call
        return {"content": [{"type": "text", "text": f"[error] {type(exc).__name__}: {exc}"}], "isError": True}


def _handle(req: dict[str, Any]) -> dict[str, Any] | None:
    """Route one JSON-RPC request. Returns a response dict, or None for a
    notification (no id → no reply, per JSON-RPC)."""
    method = req.get("method")
    req_id = req.get("id")
    params = req.get("params") or {}

    def ok(result: Any) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": req_id, "result": result}

    def err(code: int, message: str) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}

    if method == "initialize":
        return ok({
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": SERVER_INFO,
        })
    if method in ("notifications/initialized", "initialized"):
        return None  # notification, no reply
    if method == "tools/list":
        return ok({"tools": _tool_list()})
    if method == "tools/call":
        return ok(_call_tool(params.get("name", ""), params.get("arguments") or {}))
    if method == "ping":
        return ok({})
    if req_id is None:
        return None  # unknown notification — ignore
    return err(-32601, f"Method not found: {method}")


def serve(stdin=None, stdout=None) -> None:
    """Read newline-delimited JSON-RPC from stdin, write responses to stdout.
    (MCP's stdio transport is line-delimited JSON.)"""
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue  # ignore malformed input rather than die
        resp = _handle(req)
        if resp is not None:
            stdout.write(json.dumps(resp) + "\n")
            stdout.flush()


if __name__ == "__main__":
    serve()
