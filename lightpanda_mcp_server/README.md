# OneSeek Lightpanda MCP Server

Extended fork of [lightpanda-io/gomcp](https://github.com/lightpanda-io/gomcp) with additional browser automation tools for the OneSeek AI platform.

Based on the original gomcp (Apache 2.0), this version adds 9 new tools for complete browser automation.

## Tools (14 total)

### Original (5)
| Tool | Description |
|------|-------------|
| `goto` | Navigate to a URL and load the page |
| `search` | Search via DuckDuckGo |
| `markdown` | Get page content as markdown |
| `links` | Extract all hyperlinks (with optional regex filter) |
| `over` | Signal task completion |

### Extended (9)
| Tool | Description |
|------|-------------|
| `get_text` | Extract text from a CSS selector |
| `click` | Click on an element |
| `screenshot` | Capture page/element as PNG (base64) |
| `execute_js` | Run arbitrary JavaScript |
| `fill_form` | Fill form fields and submit |
| `extract_data` | Extract text from multiple selectors at once |
| `fetch_api` | Fetch JSON from API endpoints |
| `save_pdf` | Save page as PDF (base64) |
| `wait_for` | Wait for an element to become visible |

## Quick Start

### Option 1: Docker Compose (with OneSeek)

```bash
docker compose up lightpanda-mcp
```

### Option 2: Standalone with Docker

```bash
docker build -t oneseek-lightpanda-mcp .
docker run -p 8081:8081 oneseek-lightpanda-mcp
```

### Option 3: From source

```bash
go build -o gomcp .
./gomcp download          # Download Lightpanda browser
./gomcp sse               # Start SSE server on :8081
```

## Deploy on Render.com

1. Push this directory to a GitHub repo (or use the OneSeek monorepo)
2. Create a new **Web Service** on Render
3. Set **Root Directory** to `lightpanda_mcp_server`
4. **Environment**: Docker
5. No env vars needed (Lightpanda is bundled in the Docker image)
6. Deploy — you'll get a URL like `https://your-service.onrender.com`

## Connect to OneSeek

In the OneSeek frontend, go to **Add MCP Connector**:

- **Name**: `Lightpanda Browser`
- **Transport**: `sse`
- **URL**: `https://your-service.onrender.com/sse`

That's it. The agent will automatically discover all 14 tools.

## Testing

```bash
# Install test dependencies
pip install playwright httpx

# Test CDP directly (Lightpanda must be running on :9222)
python test_standalone.py --mode cdp

# Test MCP protocol (MCP server must be running on :8081)
python test_standalone.py --mode mcp

# Test both
python test_standalone.py --mode full
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `MCP_API_ADDRESS` | `127.0.0.1:8081` | SSE server listen address |
| `MCP_CDP` | _(empty)_ | External CDP WebSocket URL. If empty, starts bundled browser. |

## Architecture

```
┌──────────────────┐     ┌──────────────────────┐     ┌─────────────────┐
│  OneSeek Agent   │────▶│  This MCP Server     │────▶│  Lightpanda     │
│  (MCP Client)    │ SSE │  (Go, port 8081)     │ CDP │  (bundled)      │
└──────────────────┘     └──────────────────────┘     └─────────────────┘
```

## License

Apache 2.0 (same as original gomcp)
