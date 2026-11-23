"""`MCP_TRANSPORT=stdio` really speaks the protocol on the process's pipes.

This is the mode a client like Claude Desktop uses: it launches `uv run mcpserver` itself and
talks JSON-RPC over stdin/stdout. One handshake is enough to prove the entrypoint is wired.
"""

import json
import os
import subprocess
import sys

INITIALIZE = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-06-18",
        "capabilities": {},
        "clientInfo": {"name": "test", "version": "0"},
    },
}


def test_the_stdio_transport_answers_a_handshake() -> None:
    env = {**os.environ, "MCP_TRANSPORT": "stdio", "LOG_LEVEL": "CRITICAL"}

    completed = subprocess.run(
        [sys.executable, "-m", "mcpserver.server"],
        input=json.dumps(INITIALIZE) + "\n",
        capture_output=True,
        text=True,
        timeout=60,
        env=env,
        check=False,
    )

    reply = json.loads(completed.stdout.strip().splitlines()[0])
    assert reply["result"]["serverInfo"]["name"] == "McpSquelette"
    assert "tools" in reply["result"]["capabilities"]
