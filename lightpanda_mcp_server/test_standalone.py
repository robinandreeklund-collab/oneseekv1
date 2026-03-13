#!/usr/bin/env python3
"""
Standalone test script for the OneSeek Lightpanda MCP server.

Usage:
    # Test 1: Direct CDP connection (requires Lightpanda running on port 9222)
    python test_standalone.py --mode cdp

    # Test 2: MCP protocol test (requires MCP server running on port 8081)
    python test_standalone.py --mode mcp

    # Test 3: Full flow — MCP server end-to-end
    python test_standalone.py --mode full

Prerequisites:
    pip install playwright httpx
    # For MCP test: pip install mcp
"""

import argparse
import asyncio
import json
import sys

# ANSI colors
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
RESET = "\033[0m"


def ok(msg: str):
    print(f"  {GREEN}✓{RESET} {msg}")


def fail(msg: str):
    print(f"  {RED}✗{RESET} {msg}")


def info(msg: str):
    print(f"  {BLUE}→{RESET} {msg}")


def header(msg: str):
    print(f"\n{YELLOW}{'='*60}")
    print(f"  {msg}")
    print(f"{'='*60}{RESET}\n")


# ============================================================================
# Test Mode: CDP Direct
# ============================================================================

async def test_cdp(cdp_url: str = "http://localhost:9222"):
    """Test Lightpanda CDP connection directly via Playwright."""
    header("CDP Direct Test")

    try:
        from playwright.async_api import async_playwright
    except ImportError:
        fail("playwright not installed. Run: pip install playwright")
        return False

    success = True

    try:
        async with async_playwright() as p:
            info(f"Connecting to CDP at {cdp_url}...")
            browser = await p.chromium.connect_over_cdp(cdp_url)
            ok("Connected to Lightpanda via CDP")

            # Test 1: Navigate
            page = await browser.new_page()
            await page.goto("https://example.com")
            title = await page.title()
            ok(f"Navigation works — title: '{title}'")

            # Test 2: Get HTML
            html = await page.content()
            ok(f"HTML extraction works — {len(html)} chars")

            # Test 3: Get text
            text = await page.inner_text("body")
            ok(f"Text extraction works — {len(text)} chars")

            # Test 4: Get links
            links = await page.eval_on_selector_all("a[href]", "els => els.map(e => e.href)")
            ok(f"Link extraction works — {len(links)} links found")

            # Test 5: Execute JS
            result = await page.evaluate("() => document.title")
            ok(f"JS execution works — returned: '{result}'")

            await page.close()
            await browser.close()
            ok("Cleanup successful")

    except Exception as e:
        fail(f"CDP test failed: {e}")
        success = False

    return success


# ============================================================================
# Test Mode: MCP Protocol
# ============================================================================

async def test_mcp(mcp_url: str = "http://localhost:8081"):
    """Test the MCP server via SSE transport using raw HTTP."""
    header("MCP Protocol Test (SSE)")

    try:
        import httpx
    except ImportError:
        fail("httpx not installed. Run: pip install httpx")
        return False

    success = True

    try:
        # Step 1: Connect to SSE endpoint
        info(f"Connecting to MCP SSE at {mcp_url}/sse...")

        async with httpx.AsyncClient(timeout=30.0) as client:
            # Get the SSE stream to obtain endpoint
            async with client.stream("GET", f"{mcp_url}/sse") as stream:
                # Read the first event to get the endpoint
                endpoint = None
                async for line in stream.aiter_lines():
                    if line.startswith("data:"):
                        data = line[5:].strip()
                        if "/messages?" in data:
                            endpoint = data.strip('"')
                            break

                if not endpoint:
                    fail("Could not get message endpoint from SSE")
                    return False

                ok(f"Got SSE endpoint: {endpoint}")
                messages_url = f"{mcp_url}{endpoint}"

                # Step 2: Initialize
                init_req = {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2024-11-05",
                        "clientInfo": {"name": "test-client", "version": "1.0"},
                        "capabilities": {},
                    },
                }
                resp = await client.post(messages_url, json=init_req)
                if resp.status_code == 202:
                    ok("Initialize request accepted")
                else:
                    fail(f"Initialize failed: {resp.status_code}")
                    success = False

                # Read init response from SSE
                init_response = None
                async for line in stream.aiter_lines():
                    if line.startswith("data:"):
                        data = line[5:].strip()
                        try:
                            parsed = json.loads(data)
                            if parsed.get("id") == 1:
                                init_response = parsed
                                break
                        except json.JSONDecodeError:
                            continue

                if init_response:
                    server_info = init_response.get("result", {}).get("serverInfo", {})
                    ok(f"Server: {server_info.get('name', '?')} v{server_info.get('version', '?')}")
                else:
                    fail("No initialize response received")

                # Step 3: List tools
                list_req = {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/list",
                    "params": {},
                }
                resp = await client.post(messages_url, json=list_req)

                tools_response = None
                async for line in stream.aiter_lines():
                    if line.startswith("data:"):
                        data = line[5:].strip()
                        try:
                            parsed = json.loads(data)
                            if parsed.get("id") == 2:
                                tools_response = parsed
                                break
                        except json.JSONDecodeError:
                            continue

                if tools_response:
                    tools = tools_response.get("result", {}).get("tools", [])
                    ok(f"Found {len(tools)} tools:")
                    for tool in tools:
                        info(f"  • {tool['name']}: {tool.get('description', '')[:60]}...")
                else:
                    fail("No tools response received")

                # Step 4: Test goto tool
                goto_req = {
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "tools/call",
                    "params": {
                        "name": "goto",
                        "arguments": {"url": "https://example.com"},
                    },
                }
                resp = await client.post(messages_url, json=goto_req)

                goto_response = None
                async for line in stream.aiter_lines():
                    if line.startswith("data:"):
                        data = line[5:].strip()
                        try:
                            parsed = json.loads(data)
                            if parsed.get("id") == 3:
                                goto_response = parsed
                                break
                        except json.JSONDecodeError:
                            continue

                if goto_response:
                    content = goto_response.get("result", {}).get("content", [{}])
                    text = content[0].get("text", "") if content else ""
                    is_error = goto_response.get("result", {}).get("isError", False)
                    if is_error:
                        fail(f"goto returned error: {text}")
                    else:
                        ok(f"goto works: {text[:80]}...")
                else:
                    fail("No goto response received")

                # Step 5: Test markdown tool
                md_req = {
                    "jsonrpc": "2.0",
                    "id": 4,
                    "method": "tools/call",
                    "params": {"name": "markdown", "arguments": {}},
                }
                resp = await client.post(messages_url, json=md_req)

                md_response = None
                async for line in stream.aiter_lines():
                    if line.startswith("data:"):
                        data = line[5:].strip()
                        try:
                            parsed = json.loads(data)
                            if parsed.get("id") == 4:
                                md_response = parsed
                                break
                        except json.JSONDecodeError:
                            continue

                if md_response:
                    content = md_response.get("result", {}).get("content", [{}])
                    text = content[0].get("text", "") if content else ""
                    is_error = md_response.get("result", {}).get("isError", False)
                    if is_error:
                        fail(f"markdown returned error: {text}")
                    else:
                        ok(f"markdown works: {len(text)} chars of content")
                        if "Example Domain" in text:
                            ok("Content verified — 'Example Domain' found in markdown")
                else:
                    fail("No markdown response received")

    except Exception as e:
        fail(f"MCP test failed: {e}")
        success = False

    return success


# ============================================================================
# Main
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description="Test OneSeek Lightpanda MCP Server")
    parser.add_argument(
        "--mode",
        choices=["cdp", "mcp", "full"],
        default="mcp",
        help="Test mode: cdp (direct CDP), mcp (MCP protocol), full (both)",
    )
    parser.add_argument("--cdp-url", default="http://localhost:9222", help="Lightpanda CDP URL")
    parser.add_argument("--mcp-url", default="http://localhost:8081", help="MCP server URL")
    args = parser.parse_args()

    results = []

    if args.mode in ("cdp", "full"):
        results.append(("CDP", asyncio.run(test_cdp(args.cdp_url))))

    if args.mode in ("mcp", "full"):
        results.append(("MCP", asyncio.run(test_mcp(args.mcp_url))))

    # Summary
    header("Test Summary")
    all_passed = True
    for name, passed in results:
        if passed:
            ok(f"{name}: ALL PASSED")
        else:
            fail(f"{name}: FAILED")
            all_passed = False

    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
