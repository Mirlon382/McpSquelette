# MCPSquelette 🦴

"Just the tools"

Python MCP server template based on the FastMCP v4 lib. It handles starting the server with pre configured :
- logging
- server config
- rate limiting
- Docker image

Bundled with a Skill (to do)

## Build

Simply retrieve the skeleton repository 🦴

```{bash}
git clone <url>
```

Start building tools in the `tools/` directory. For a better Agent Experience, don't forget to add input and output schema in the `models/` directory.

When deemed finished, launch with

```{bash}
uv sync
uv run mcpserver
```

'It's Alive 🧟'

```{bash}
npx @modelcontextprotocol/inspector
```

To inspect it. By default on http://localhost:8000/mcp

## Make it portable

```{bash}
docker build . -t myserver
```

There is also some Kubernetes config available in `k8s/`