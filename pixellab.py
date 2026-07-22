"""Minimal MCP-over-HTTP client for PixelLab.

The pixellab MCP server is registered in ~/.claude.json but was not loaded into
the running Claude Code session, so we speak the protocol directly instead of
making the user restart. Same endpoint, same token, same tools.
"""

import json
import os
import sys
import urllib.request

CONFIG = os.path.expanduser("~/.claude.json")
PROJECT = "E:/Workspace"
_session = None


def _server():
    with open(CONFIG, encoding="utf-8") as f:
        cfg = json.load(f)
    return cfg["projects"][PROJECT]["mcpServers"]["pixellab"]


def _post(method, params, session=None, rid=1, timeout=180):
    srv = _server()
    headers = dict(srv.get("headers") or {})
    headers.update({
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    })
    if session:
        headers["Mcp-Session-Id"] = session
    body = json.dumps({
        "jsonrpc": "2.0", "id": rid, "method": method, "params": params,
    }).encode()
    req = urllib.request.Request(srv["url"], data=body, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.headers.get("Mcp-Session-Id"), response.read().decode("utf-8", "replace")


def _parse(raw):
    """The server answers with SSE frames; pull the JSON-RPC payload out."""
    for line in raw.splitlines():
        if line.startswith("data: "):
            return json.loads(line[6:])
    return json.loads(raw) if raw.strip() else {}


def connect():
    global _session
    if _session:
        return _session
    _session, _ = _post("initialize", {
        "protocolVersion": "2024-11-05",
        "capabilities": {},
        "clientInfo": {"name": "codepet", "version": "1.0"},
    })
    return _session


def list_tools():
    session = connect()
    _, raw = _post("tools/list", {}, session=session, rid=2)
    return _parse(raw).get("result", {}).get("tools", [])


def call(name, arguments, timeout=300):
    session = connect()
    _, raw = _post(
        "tools/call", {"name": name, "arguments": arguments},
        session=session, rid=3, timeout=timeout,
    )
    return _parse(raw)


def text_of(result):
    """Flatten a tools/call result into plain text."""
    chunks = []
    for item in result.get("result", {}).get("content", []):
        if item.get("type") == "text":
            chunks.append(item["text"])
    if not chunks and "error" in result:
        return json.dumps(result["error"], ensure_ascii=False)
    return "\n".join(chunks)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    wanted = sys.argv[1:] or ["create_character"]
    for tool in list_tools():
        if tool["name"] in wanted:
            print("=" * 70)
            print(tool["name"], "-", tool.get("description", "")[:200])
            print(json.dumps(tool.get("inputSchema", {}), indent=2, ensure_ascii=False)[:2600])
