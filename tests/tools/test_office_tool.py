from __future__ import annotations

import os
import tempfile

from app.tools.office_tool import OfficeTool


class TestOfficeTool:
    def test_name_and_version(self) -> None:
        tool = OfficeTool()
        assert tool.name == "office_tool"
        assert tool.version == "1.0.0"

    def test_parameters_defined(self) -> None:
        tool = OfficeTool()
        names = [p.name for p in tool.metadata.parameters]
        assert "action" in names
        assert "format" in names
        assert "content" in names

    def test_required_params(self) -> None:
        tool = OfficeTool()
        assert tool.metadata.parameters[0].required is True
        assert tool.metadata.parameters[1].required is True
        assert tool.metadata.parameters[2].required is True

    def test_permissions(self) -> None:
        tool = OfficeTool()
        assert "tools.office.generate" in tool.metadata.permissions_required

    def test_capabilities(self) -> None:
        tool = OfficeTool()
        assert "document_generation" in tool.metadata.capabilities

    def test_validate_missing_action(self) -> None:
        tool = OfficeTool()
        errors = tool.validate_params({"format": "markdown", "content": "hi"})
        assert any("action" in e for e in errors)

    def test_validate_missing_format(self) -> None:
        tool = OfficeTool()
        errors = tool.validate_params({"action": "generate", "content": "hi"})
        assert any("format" in e for e in errors)

    def test_unknown_action(self) -> None:
        tool = OfficeTool()
        result = tool.execute({"action": "unknown", "format": "text", "content": "test"})
        assert not result.success
        assert "unknown" in (result.error_message or "").lower()

    def test_unsupported_format(self) -> None:
        tool = OfficeTool()
        result = tool.execute({"action": "generate", "format": "pdf", "content": "test"})
        assert not result.success
        assert "unsupported" in (result.error_message or "").lower()

    def test_generate_markdown_string(self) -> None:
        tool = OfficeTool()
        result = tool.execute({"action": "generate", "format": "markdown", "content": "Hello **world**", "title": "Test"})
        assert result.success
        assert "# Test" in result.output["content"]
        assert "Hello" in result.output["content"]

    def test_generate_markdown_dict(self) -> None:
        tool = OfficeTool()
        content = {"Section 1": "Body text", "Section 2": ["item1", "item2"]}
        result = tool.execute({"action": "generate", "format": "markdown", "content": content, "title": "Doc"})
        assert result.success
        assert "## Section 1" in result.output["content"]
        assert "## Section 2" in result.output["content"]

    def test_generate_html(self) -> None:
        tool = OfficeTool()
        result = tool.execute({"action": "generate", "format": "html", "content": "<p>Hello</p>", "title": "Page"})
        assert result.success
        assert "<h1>Page</h1>" in result.output["content"]
        assert "<html>" in result.output["content"]

    def test_generate_html_with_dict(self) -> None:
        tool = OfficeTool()
        result = tool.execute({"action": "generate", "format": "html", "content": {"Key": "Value"}, "title": "Data"})
        assert result.success
        assert "<h2>Key</h2>" in result.output["content"]

    def test_generate_csv_from_dicts(self) -> None:
        tool = OfficeTool()
        content = [{"name": "Alice", "age": 30}, {"name": "Bob", "age": 25}]
        result = tool.execute({"action": "generate", "format": "csv", "content": content})
        assert result.success
        assert "Alice" in result.output["content"]
        assert "name,age" in result.output["content"]

    def test_generate_csv_from_lists(self) -> None:
        tool = OfficeTool()
        content = [["a", "b"], ["c", "d"]]
        result = tool.execute({"action": "generate", "format": "csv", "content": content})
        assert result.success
        assert "a,b" in result.output["content"]

    def test_generate_json(self) -> None:
        tool = OfficeTool()
        content = {"name": "test", "values": [1, 2, 3]}
        result = tool.execute({"action": "generate", "format": "json", "content": content})
        assert result.success
        assert '"name": "test"' in result.output["content"]

    def test_generate_text(self) -> None:
        tool = OfficeTool()
        result = tool.execute({"action": "generate", "format": "text", "content": "plain text output"})
        assert result.success
        assert result.output["content"] == "plain text output"

    def test_generate_with_output_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            outpath = os.path.join(tmpdir, "test.md")
            tool = OfficeTool()
            result = tool.execute({"action": "generate", "format": "markdown", "content": "# Saved", "output_path": outpath})
            assert result.success
            assert os.path.exists(outpath)
            with open(outpath) as f:
                content = f.read()
                assert "# Saved" in content

    def test_execution_time_positive(self) -> None:
        tool = OfficeTool()
        result = tool.execute({"action": "generate", "format": "text", "content": "timing"})
        assert result.execution_time > 0

    def test_to_dict(self) -> None:
        tool = OfficeTool()
        d = tool.to_dict()
        assert d["name"] == "office_tool"
