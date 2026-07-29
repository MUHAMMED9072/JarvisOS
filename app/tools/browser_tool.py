from __future__ import annotations

import json
import re
import time
from typing import Any
from urllib.parse import urljoin, urlparse

from app.tools.base import Tool, ToolMetadata, ToolParameter, ToolResult, ToolStatus


class BrowserTool(Tool):
    """Web scraping, search, and form interaction.

    Parameters:
      - url (required): Target URL to scrape or search
      - action: Operation (scrape, search, links, text, forms). Default: scrape.
      - selector: CSS selector or specific element to extract
      - query: Search query (for search action)
      - headers: Custom HTTP headers as dict
      - timeout: Request timeout in seconds (default 30)

    Security: URLs are validated, local/internal hosts are blocked.
    Requires 'tools.browser.scrape' permission.
    """

    _BLOCKED_HOSTS = ["localhost", "127.0.0.1", "0.0.0.0", "[::1]", "169.254."]

    def __init__(self) -> None:
        metadata = ToolMetadata(
            name="browser_tool",
            version="1.0.0",
            description="Web scraping, search, link extraction, and form discovery",
            tool_type="builtin",
            status=ToolStatus.ACTIVE,
            parameters=[
                ToolParameter(name="url", description="Target URL", type="string", required=True),
                ToolParameter(name="action", description="Operation: scrape, search, links, text, forms", type="string", required=False, default="scrape"),
                ToolParameter(name="selector", description="CSS selector to extract", type="string", required=False),
                ToolParameter(name="query", description="Search query text", type="string", required=False),
                ToolParameter(name="headers", description="Custom HTTP headers", type="object", required=False),
                ToolParameter(name="timeout", description="Request timeout in seconds", type="number", required=False, default=30.0),
            ],
            permissions_required=["tools.browser.scrape"],
            capabilities=["web_scraping", "html_parsing", "link_extraction"],
            owner="system",
            tags=["browser", "scraping", "html", "web"],
        )
        super().__init__(metadata)

    def _fetch(self, url: str, headers: dict | None, timeout: float) -> tuple[str, int, dict]:
        import requests as req
        resp = req.get(url, headers=headers or {}, timeout=timeout)
        resp.raise_for_status()
        return resp.text, resp.status_code, dict(resp.headers)

    def _soup(self, html: str):
        from bs4 import BeautifulSoup
        return BeautifulSoup(html, "html.parser")

    def execute(self, params: dict[str, Any]) -> ToolResult:
        errors = self.validate_params(params)
        if errors:
            return ToolResult(success=False, error_message="; ".join(errors))

        url = params["url"]
        action = params.get("action", "scrape")
        selector = params.get("selector")
        query = params.get("query")
        custom_headers = params.get("headers", {}) or {}
        timeout = float(params.get("timeout", 30.0))

        for blocked in self._BLOCKED_HOSTS:
            if blocked in url.lower():
                return ToolResult(success=False, error_message=f"URL blocked: requests to '{blocked}' are not allowed")

        start = time.time()
        try:
            html, status, resp_headers = self._fetch(url, custom_headers, timeout)
            soup = self._soup(html)
            elapsed = time.time() - start

            if action == "scrape":
                title = soup.title.string.strip() if soup.title and soup.title.string else ""
                text = soup.get_text(separator=" ", strip=True)
                meta_tags = {}
                for tag in soup.find_all("meta"):
                    if tag.get("name"):
                        meta_tags[tag["name"]] = tag.get("content", "")
                output = {
                    "url": url,
                    "status_code": status,
                    "title": title,
                    "text_length": len(text),
                    "text_preview": text[:2000],
                    "meta_tags": meta_tags,
                }
                if selector:
                    selected = soup.select(selector)
                    output["selected"] = [str(el) for el in selected]
                    output["selected_text"] = [el.get_text(strip=True) for el in selected]
                    output["selected_count"] = len(selected)
                return ToolResult(success=True, output=output, execution_time=elapsed)

            elif action == "search":
                text = soup.get_text(separator=" ", strip=True)
                query_lower = (query or selector or "").lower()
                if not query_lower:
                    return ToolResult(success=False, error_message="query or selector required for search", execution_time=elapsed)
                matches = []
                for i, line in enumerate(text.split("\n")):
                    if query_lower in line.lower():
                        context = line.strip()[:300]
                        matches.append({"line": i, "text": context})
                return ToolResult(
                    success=True,
                    output={"url": url, "query": query_lower, "match_count": len(matches), "matches": matches[:50]},
                    execution_time=elapsed,
                )

            elif action == "links":
                links = []
                seen = set()
                for a_tag in soup.find_all("a", href=True):
                    href = a_tag["href"]
                    absolute = urljoin(url, href)
                    if absolute not in seen:
                        seen.add(absolute)
                        links.append({
                            "href": absolute,
                            "text": a_tag.get_text(strip=True)[:200],
                        })
                return ToolResult(
                    success=True,
                    output={"url": url, "link_count": len(links), "links": links[:100]},
                    execution_time=elapsed,
                )

            elif action == "text":
                text = soup.get_text(separator="\n", strip=True)
                return ToolResult(
                    success=True,
                    output={"url": url, "text_length": len(text), "text": text[:5000]},
                    execution_time=elapsed,
                )

            elif action == "forms":
                forms = []
                for form in soup.find_all("form"):
                    form_data = {
                        "action": form.get("action", ""),
                        "method": form.get("method", "get").upper(),
                        "inputs": [],
                    }
                    for inp in form.find_all("input"):
                        form_data["inputs"].append({
                            "name": inp.get("name", ""),
                            "type": inp.get("type", "text"),
                            "value": inp.get("value", ""),
                        })
                    for sel in form.find_all("select"):
                        options = [{"value": opt.get("value", ""), "text": opt.get_text(strip=True)} for opt in sel.find_all("option")]
                        form_data["inputs"].append({
                            "name": sel.get("name", ""),
                            "type": "select",
                            "options": options,
                        })
                    forms.append(form_data)
                return ToolResult(
                    success=True,
                    output={"url": url, "form_count": len(forms), "forms": forms},
                    execution_time=elapsed,
                )

            else:
                return ToolResult(success=False, error_message=f"Unknown action: '{action}'", execution_time=elapsed)

        except ImportError as e:
            return ToolResult(success=False, error_message=f"Missing library: {e}", execution_time=time.time() - start)
        except Exception as e:
            return ToolResult(success=False, error_message=str(e), execution_time=time.time() - start)
