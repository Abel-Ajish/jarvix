"""Web search tools for jarvix.

Search is performed via the DuckDuckGo HTML endpoint (no API key required).
If DuckDuckGo is unreachable, a Google HTML fallback is attempted.  Results
are returned as structured dicts: ``title``, ``url``, ``snippet``.
"""

from __future__ import annotations

import asyncio
import html as html_module
import re
import urllib.parse
from typing import Any, Dict, List, Optional

from jarvix.core.execution import ExecContext
from jarvix.core.logger import get_logger
from jarvix.core.permissions import PermissionLevel
from jarvix.core.tool_registry import Tool, ToolResult, tool

_LOG = get_logger("jarvix.web.search")

# Regex used to strip HTML tags from snippets/titles.
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def _strip_tags(text: str) -> str:
    """Remove HTML tags, decode entities, and collapse whitespace."""
    if not text:
        return ""
    text = _TAG_RE.sub("", text)
    text = html_module.unescape(text)
    text = urllib.parse.unquote(text)
    text = _WS_RE.sub(" ", text)
    return text.strip()


def _http_get(url: str, *, timeout: float = 15.0) -> str:
    """Fetch ``url`` and return decoded text. Raises on failure."""
    import urllib.request

    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "en-US,en;q=0.9",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("utf-8", errors="replace")


def _parse_duckduckgo(html: str, *, max_results: int) -> List[Dict[str, str]]:
    """Extract structured results from DuckDuckGo HTML response."""
    results: List[Dict[str, str]] = []

    block_re = re.compile(
        r'<a[^>]*class="[^"]*result__a[^"]*"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
        re.IGNORECASE | re.DOTALL,
    )
    snippet_re = re.compile(
        r'class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</(?:a|div|p)>',
        re.IGNORECASE | re.DOTALL,
    )

    titles = block_re.findall(html)
    snippets = snippet_re.findall(html)

    for i, (raw_url, raw_title) in enumerate(titles):
        if len(results) >= max_results:
            break
        title = _strip_tags(raw_title)
        if not title:
            continue

        url = raw_url
        parsed = urllib.parse.urlparse(url)
        if parsed.netloc == "duckduckgo.com" and parsed.path.startswith("/l/"):
            query = urllib.parse.parse_qs(parsed.query)
            uddg = query.get("uddg") or query.get("u")
            if uddg:
                url = urllib.parse.unquote(uddg[0])

        snippet = ""
        if i < len(snippets):
            snippet = _strip_tags(snippets[i])

        results.append({"title": title, "url": url, "snippet": snippet})

    return results


def _parse_google(html: str, *, max_results: int) -> List[Dict[str, str]]:
    """Extract structured results from Google HTML response."""
    results: List[Dict[str, str]] = []

    item_re = re.compile(
        r'<a[^>]*href="([^"]+)"[^>]*>.*?<h3[^>]*>(.*?)</h3>',
        re.IGNORECASE | re.DOTALL,
    )
    snippet_re = re.compile(
        r'<span[^>]*class="[^"]*st[^"]*"[^>]*>(.*?)</span>',
        re.IGNORECASE | re.DOTALL,
    )

    items = item_re.findall(html)
    snippets = snippet_re.findall(html)

    for i, (raw_url, raw_title) in enumerate(items):
        if len(results) >= max_results:
            break
        title = _strip_tags(raw_title)
        if not title:
            continue

        url = raw_url
        parsed = urllib.parse.urlparse(url)
        if parsed.netloc == "www.google.com" and parsed.path == "/url":
            q = urllib.parse.parse_qs(parsed.query).get("q")
            if q:
                url = q[0]

        snippet = ""
        if i < len(snippets):
            snippet = _strip_tags(snippets[i])

        results.append({"title": title, "url": url, "snippet": snippet})

    return results


async def search(
    query: str,
    *,
    max_results: int = 10,
    engine: str = "duckduckgo",
    cancel_event: Optional[asyncio.Event] = None,
) -> List[Dict[str, str]]:
    """Run a web search and return structured results.

    ``engine`` is ``"duckduckgo"`` (default) or ``"google"``.  If the
    primary engine fails, the other is tried as a fallback.
    """
    if cancel_event is not None and cancel_event.is_set():
        raise asyncio.CancelledError()

    engines: List[str]
    if engine == "google":
        engines = ["google", "duckduckgo"]
    else:
        engines = ["duckduckgo", "google"]

    last_error: Optional[Exception] = None
    for name in engines:
        if cancel_event is not None and cancel_event.is_set():
            raise asyncio.CancelledError()
        try:
            if name == "duckduckgo":
                q = urllib.parse.quote(query)
                url = f"https://html.duckduckgo.com/html/?q={q}"
            else:
                q = urllib.parse.quote(query)
                url = f"https://www.google.com/search?q={q}&hl=en"

            html = await asyncio.to_thread(_http_get, url)
            if cancel_event is not None and cancel_event.is_set():
                raise asyncio.CancelledError()

            if name == "duckduckgo":
                results = _parse_duckduckgo(html, max_results=max_results)
            else:
                results = _parse_google(html, max_results=max_results)

            if results:
                return results
            last_error = RuntimeError(f"{name} returned no results")
        except asyncio.CancelledError:
            raise
        except Exception as e:
            last_error = e
            _LOG.warning("Search engine '%s' failed: %s", name, e)
            continue

    if last_error is not None:
        raise last_error
    return []


@tool(
    "web_search",
    permission=PermissionLevel.CONFIRM,
    description="Search the web and return structured results",
)
class WebSearchTool(Tool):
    """Search the web using DuckDuckGo (with Google fallback)."""

    name = "web_search"
    description = "Search the web and return a list of results (title, url, snippet)"
    permission = PermissionLevel.CONFIRM

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query (e.g. 'python asyncio tutorial')",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of results to return",
                    "default": 10,
                },
                "engine": {
                    "type": "string",
                    "description": "Search engine to use: 'duckduckgo' or 'google'",
                    "default": "duckduckgo",
                    "enum": ["duckduckgo", "google"],
                },
            },
            "required": ["query"],
        }

    async def execute(self, args: Dict[str, Any], ctx: ExecContext) -> ToolResult:
        query = args.get("query", "").strip()
        if not query:
            return ToolResult.failure("query is required")

        max_results = args.get("max_results", 10)
        try:
            max_results = int(max_results)
        except (TypeError, ValueError):
            max_results = 10
        max_results = max(1, min(50, max_results))

        engine = args.get("engine", "duckduckgo")
        if engine not in ("duckduckgo", "google"):
            engine = "duckduckgo"

        ctx.check_cancelled()

        try:
            results = await search(
                query,
                max_results=max_results,
                engine=engine,
                cancel_event=ctx.cancel_event,
            )
        except asyncio.CancelledError:
            raise
        except Exception as e:
            _LOG.exception("Search failed")
            return ToolResult.failure(f"Search failed: {e}")

        if not results:
            return ToolResult.success(
                f"No results found for '{query}'",
                data={"query": query, "results": []},
            )

        lines = []
        for r in results:
            lines.append(f"- {r.get('title', '')}: {r.get('url', '')}")
        summary = "\n".join(lines)
        return ToolResult.success(
            f"Found {len(results)} results for '{query}'",
            data={"query": query, "results": results, "summary": summary},
        )