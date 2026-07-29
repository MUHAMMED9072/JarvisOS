from __future__ import annotations

import csv
import io
import json
import os
import time
from datetime import datetime
from typing import Any

from app.tools.base import Tool, ToolMetadata, ToolParameter, ToolResult, ToolStatus


class OfficeTool(Tool):
    """Generate documents in various formats.

    Supported formats: markdown (.md), html (.html), csv (.csv),
    json (.json), text (.txt).

    Parameters:
      - action (required): Operation (generate, convert)
      - format (required): Target format (markdown, html, csv, json, text)
      - content (required): Document content structure
      - output_path: File path to write the document
      - title: Document title
      - author: Document author

    For CSV format, content should be a list of dicts with the same keys.
    For JSON format, content should be any JSON-serializable structure.
    For markdown/html/text, content should be a string or structured dict.
    """

    def __init__(self) -> None:
        metadata = ToolMetadata(
            name="office_tool",
            version="1.0.0",
            description="Generate documents: markdown, HTML, CSV, JSON, text",
            tool_type="builtin",
            status=ToolStatus.ACTIVE,
            parameters=[
                ToolParameter(name="action", description="Operation: generate, convert", type="string", required=True),
                ToolParameter(name="format", description="Output format: markdown, html, csv, json, text", type="string", required=True),
                ToolParameter(name="content", description="Document content", type="object", required=True),
                ToolParameter(name="output_path", description="Output file path", type="string", required=False),
                ToolParameter(name="title", description="Document title", type="string", required=False),
                ToolParameter(name="author", description="Document author", type="string", required=False),
            ],
            permissions_required=["tools.office.generate"],
            capabilities=["document_generation", "file_conversion"],
            owner="system",
            tags=["office", "document", "markdown", "html", "csv", "json"],
        )
        super().__init__(metadata)

    def _render_markdown(self, content: Any, title: str = "", author: str = "") -> str:
        lines: list[str] = []
        if title:
            lines.append(f"# {title}\n")
        if author:
            lines.append(f"*Author: {author}*\n")
        lines.append(f"*Generated: {datetime.now().isoformat()}*\n")
        lines.append("---\n")

        if isinstance(content, str):
            lines.append(content)
        elif isinstance(content, dict):
            for key, value in content.items():
                lines.append(f"## {key}\n")
                if isinstance(value, str):
                    lines.append(f"{value}\n")
                elif isinstance(value, list):
                    for item in value:
                        if isinstance(item, dict):
                            for k, v in item.items():
                                lines.append(f"- **{k}**: {v}")
                        else:
                            lines.append(f"- {item}")
                    lines.append("")
                elif isinstance(value, dict):
                    for k, v in value.items():
                        lines.append(f"- **{k}**: {v}")
                    lines.append("")
        elif isinstance(content, list):
            for item in content:
                if isinstance(item, dict):
                    lines.extend([f"- **{k}**: {v}" for k, v in item.items()])
                else:
                    lines.append(f"- {item}")
                lines.append("")

        return "\n".join(lines)

    def _render_html(self, content: Any, title: str = "", author: str = "") -> str:
        body_parts: list[str] = []
        if title:
            body_parts.append(f"<h1>{title}</h1>")
        if author:
            body_parts.append(f"<p><em>Author: {author}</em></p>")
        body_parts.append(f"<p><em>Generated: {datetime.now().isoformat()}</em></p>")
        body_parts.append("<hr>")

        if isinstance(content, str):
            body_parts.append(f"<p>{content}</p>")
        elif isinstance(content, dict):
            for key, value in content.items():
                body_parts.append(f"<h2>{key}</h2>")
                if isinstance(value, str):
                    body_parts.append(f"<p>{value}</p>")
                elif isinstance(value, list):
                    body_parts.append("<ul>")
                    for item in value:
                        if isinstance(item, dict):
                            body_parts.append("<li>" + ", ".join(f"<strong>{k}</strong>: {v}" for k, v in item.items()) + "</li>")
                        else:
                            body_parts.append(f"<li>{item}</li>")
                    body_parts.append("</ul>")
                elif isinstance(value, dict):
                    for k, v in value.items():
                        body_parts.append(f"<p><strong>{k}</strong>: {v}</p>")
        elif isinstance(content, list):
            body_parts.append("<ul>")
            for item in content:
                if isinstance(item, dict):
                    body_parts.append("<li>" + ", ".join(f"<strong>{k}</strong>: {v}" for k, v in item.items()) + "</li>")
                else:
                    body_parts.append(f"<li>{item}</li>")
            body_parts.append("</ul>")

        body = "\n".join(body_parts)
        return (
            f"<!DOCTYPE html>\n<html><head><meta charset='utf-8'>"
            f"<title>{title or 'Document'}</title></head><body>\n{body}\n</body></html>"
        )

    def _render_csv(self, content: Any) -> str:
        output = io.StringIO()
        if isinstance(content, list) and content and isinstance(content[0], dict):
            writer = csv.DictWriter(output, fieldnames=content[0].keys())
            writer.writeheader()
            writer.writerows(content)
        elif isinstance(content, list) and content and isinstance(content[0], list):
            writer = csv.writer(output)
            writer.writerows(content)
        else:
            output.write(str(content))
        return output.getvalue()

    def execute(self, params: dict[str, Any]) -> ToolResult:
        errors = self.validate_params(params)
        if errors:
            return ToolResult(success=False, error_message="; ".join(errors))

        action = params["action"]
        fmt = params["format"]
        content = params["content"]
        title = params.get("title", "")
        author = params.get("author", "")
        output_path = params.get("output_path")
        start = time.time()

        try:
            if action == "generate":
                if fmt == "markdown":
                    result_content = self._render_markdown(content, title, author)
                elif fmt == "html":
                    result_content = self._render_html(content, title, author)
                elif fmt == "csv":
                    result_content = self._render_csv(content)
                elif fmt == "json":
                    result_content = json.dumps(content, indent=2, default=str)
                elif fmt == "text":
                    result_content = str(content)
                else:
                    return ToolResult(success=False, error_message=f"Unsupported format: '{fmt}'", execution_time=time.time() - start)

                elapsed = time.time() - start

                if output_path:
                    os.makedirs(os.path.dirname(os.path.abspath(output_path)) or ".", exist_ok=True)
                    with open(output_path, "w", encoding="utf-8") as f:
                        f.write(result_content)
                    return ToolResult(
                        success=True,
                        output={"format": fmt, "path": output_path, "size": len(result_content), "content": result_content[:2000]},
                        execution_time=elapsed,
                    )
                return ToolResult(
                    success=True,
                    output={"format": fmt, "size": len(result_content), "content": result_content},
                    execution_time=elapsed,
                )

            elif action == "convert":
                source_format = params.get("source_format", fmt)
                target_format = params.get("target_format", params.get("format", ""))
                return ToolResult(
                    success=False,
                    error_message="convert action not yet implemented",
                    execution_time=time.time() - start,
                )

            else:
                return ToolResult(success=False, error_message=f"Unknown action: '{action}'", execution_time=time.time() - start)

        except Exception as e:
            return ToolResult(success=False, error_message=str(e), execution_time=time.time() - start)
