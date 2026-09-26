"""HTML → Markdown/text extraction for jarvix (Phase 6).

Provides ``read_page`` tool to fetch a URL and extract readable content.
Uses ``html2text`` if available, otherwise falls back to a regex-based
extractor.  Strips scripts, styles, navigation, and other non-content.
"""

from __future__ import annotations

import asyncio
import re
import urllib.parse
from typing import Any, Dict, Optional

from jarvix.core.execution import ExecContext
from jarvix.core.logger import get_logger
from jarvix.core.permissions import PermissionLevel
from jarvix.core.tool_registry import Tool, ToolResult, tool

_LOG = get_logger("jarvix.web.reader")

# Regex to strip HTML tags
_TAG_RE = re.compile(r"<[^>]+>", re.DOTALL)
_SCRIPT_STYLE_RE = re.compile(
    r"<(script|style|noscript|iframe|svg|canvas|video|audio|object|embed|applet|nav|header|footer|aside)[^>]*>.*?</\1>",
    re.IGNORECASE | re.DOTALL,
)
_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
_WS_RE = re.compile(r"\s+")
_MULTI_NL_RE = re.compile(r"\n\s*\n\s*\n+")


def _fetch_html(url: str, *, timeout: float = 20.0) -> str:
    """Fetch HTML content from URL."""
    import urllib.request

    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("utf-8", errors="replace")


def _clean_html(html: str) -> str:
    """Remove scripts, styles, comments, and non-content tags."""
    # Remove script/style/nav/iframe/etc blocks
    html = _SCRIPT_STYLE_RE.sub("", html)
    # Remove HTML comments
    html = _COMMENT_RE.sub("", html)
    return html


def _extract_with_html2text(html: str) -> str:
    """Convert HTML to markdown using html2text library."""
    import html2text

    h = html2text.HTML2Text()
    h.ignore_links = False
    h.ignore_images = True
    h.ignore_emphasis = False
    h.body_width = 0  # no wrapping
    h.unicode_snob = True
    h.skip_internal_links = True
    h.inline_links = False
    h.protect_links = True
    return h.handle(html)


def _extract_with_regex(html: str) -> str:
    """Fallback HTML → text using regex (no external deps).

    This is a simple but robust extractor that:
    - Keeps heading hierarchy (h1-h6 → # #... markdown)
    - Preserves paragraphs
    - Converts basic links to [text](url)
    - Strips remaining tags
    """
    # Convert headings
    for level in range(6, 0, -1):
        html = re.sub(
            rf"<h{level}[^>]*>(.*?)</h{level}>",
            lambda m: f"{'#' * level} {m.group(1).strip()}\n\n",
            html,
            flags=re.IGNORECASE | re.DOTALL,
        )

    # Convert paragraphs
    html = re.sub(
        r"<p[^>]*>(.*?)</p>",
        lambda m: f"{m.group(1).strip()}\n\n",
        html,
        flags=re.IGNORECASE | re.DOTALL,
    )

    # Convert line breaks
    html = re.sub(r"<br\s*/?>", "\n", html, flags=re.IGNORECASE)

    # Convert links: <a href="...">text</a> -> [text](...)
    def _link_repl(m: re.Match) -> str:
        url = m.group(1)
        text = _TAG_RE.sub("", m.group(2)).strip()
        if not text:
            return url
        return f"[{text}]({url})"

    html = re.sub(
        r'<a\s+[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
        _link_repl,
        html,
        flags=re.IGNORECASE | re.DOTALL,
    )

    # Convert list items
    html = re.sub(
        r"<li[^>]*>(.*?)</li>",
        lambda m: f"- {m.group(1).strip()}\n",
        html,
        flags=re.IGNORECASE | re.DOTALL,
    )

    # Convert blockquotes
    html = re.sub(
        r"<blockquote[^>]*>(.*?)</blockquote>",
        lambda m: f"> {m.group(1).strip()}\n\n",
        html,
        flags=re.IGNORECASE | re.DOTALL,
    )

    # Convert code blocks
    html = re.sub(
        r"<pre[^>]*>(.*?)</pre>",
        lambda m: f"```\n{m.group(1).strip()}\n```\n\n",
        html,
        flags=re.IGNORECASE | re.DOTALL,
    )

    # Convert inline code
    html = re.sub(
        r"<code[^>]*>(.*?)</code>",
        lambda m: f"`{m.group(1).strip()}`",
        html,
        flags=re.IGNORECASE | re.DOTALL,
    )

    # Convert div/section/article to double newlines
    html = re.sub(
        r"</?(div|section|article|main|ul|ol)[^>]*>",
        "\n\n",
        html,
        flags=re.IGNORECASE,
    )

    # Strip remaining tags
    html = _TAG_RE.sub("", html)

    # Decode entities
    html = urllib.parse.unquote(html)

    # Normalize whitespace
    html = _WS_RE.sub(" ", html)
    html = _MULTI_NL_RE.sub("\n\n", html)

    return html.strip()


def extract_readable(html: str, *, use_html2text: bool = True) -> str:
    """Extract readable markdown/text from raw HTML.

    Tries ``html2text`` first (if available and ``use_html2text=True``),
    falls back to regex-based extraction.
    """
    if not html or not html.strip():
        return ""

    html = _clean_html(html)

    if use_html2text:
        try:
            import html2text  # noqa: F401
            return _extract_with_html2text(html)
        except Exception as e:
            _LOG.debug("html2text unavailable or failed: %s, using regex", e)

    return _extract_with_regex(html)


async def read_page(
    url: str,
    *,
    timeout: float = 20.0,
    max_length: int = 50_000,
    use_html2text: bool = True,
    cancel_event: Optional[asyncio.Event] = None,
) -> Dict[str, Any]:
    """Fetch a URL and return extracted readable content.

    Returns dict with: ``url``, ``title``, ``content`` (markdown), ``length``.
    """
    if cancel_event is not None and cancel_event.is_set():
        raise asyncio.CancelledError()

    # Fetch HTML
    html = await asyncio.to_thread(_fetch_html, url, timeout=timeout)
    if cancel_event is not None and cancel_event.is_set():
        raise asyncio.CancelledError()

    # Extract title from <title> tag
    title = ""
    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    if m:
        title = _TAG_RE.sub("", m.group(1)).strip()

    # Extract main content
    content = extract_readable(html, use_html2text=use_html2text)

    # Truncate if needed
    if len(content) > max_length:
        content = content[:max_length] + f"\n\n... [truncated at {max_length} chars]"

    return {
        "url": url,
        "title": title,
        "content": content,
        "length": len(content),
    }


@tool(
    "read_page",
    permission=PermissionLevel.CONFIRM,
    description="Fetch a URL and extract readable text/markdown",
)
class ReadPageTool(Tool):
    name = "read_page"
    description = "Fetch a web page and return its readable content as markdown/text"
    permission = PermissionLevel.CONFIRM

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "URL to fetch and read (e.g. 'https://example.com')",
                },
                "max_length": {
                    "type": "integer",
                    "description": "Maximum characters to return (0 = no limit)",
                    "default": 50000,
                },
                "timeout": {
                    "type": "integer",
                    "description": "Fetch timeout in milliseconds",
                    "default": 20000,
                },
            },
            "required": ["url"],
        }

    async def execute(self, args: Dict[str, Any], ctx: ExecContext) -> ToolResult:
        url = args.get("url", "").strip()
        if not url:
            return ToolResult.failure("url is required")
        if not (url.startswith("http://") or url.startswith("https://")):
            url = "https://" + url

        max_length = args.get("max_length", 50000)
        try:
            max_length = int(max_length)
        except (TypeError, ValueError):
            max_length = 50000
        if max_length < 0:
            max_length = 50000

        timeout = args.get("timeout", 20000)
        try:
            timeout = int(timeout) / 1000.0
        except (TypeError, ValueError):
            timeout = 20.0
        timeout = max(1.0, min(120.0, timeout))

        ctx.check_cancelled()

        try:
            result = await read_page(
                url,
                timeout=timeout,
                max_length=max_length,
                use_html2text=True,
                cancel_event=ctx.cancel_event,
            )
        except asyncio.CancelledError:
            raise
        except Exception as e:
            _LOG.exception("Read page failed")
            return ToolResult.failure(f"Failed to read page: {e}")

        content = result.get("content", "")
        if not content.strip():
            return ToolResult.failure(f"No readable content found at {url}")

        return ToolResult.success(
            f"Read {result['title'] or url} ({result['length']} chars)",
            data={
                "url": result["url"],
                "title": result["title"],
                "content": content,
                "length": result["length"],
            },
        )