# ADS Code Templates

# Agent template
AGENT_TEMPLATE = '''from __future__ import annotations

from typing import Any

from app.agents.base import Agent, AgentMetadata
from app.agents.types import SystemAgent


class {class_name}(SystemAgent):
    """Agent: {description}"""

    def __init__(self, agent_id: str = "") -> None:
        metadata = AgentMetadata(
            agent_id=agent_id,
            name="{name}",
            version="{version}",
            description="{description}",
            agent_type="system",
            capabilities={capabilities},
        )
        super().__init__(metadata=metadata)
'''

# Tool template
TOOL_TEMPLATE = '''from __future__ import annotations

from typing import Any

from app.agents.types import ToolAgent


class {class_name}(ToolAgent):
    """Tool: {description}"""

    def __init__(self) -> None:
        super().__init__(tool_name="{tool_name}")
'''

# Plugin template
PLUGIN_TEMPLATE = '''from __future__ import annotations

from typing import Any

from app.agents.base import Agent, AgentMetadata


class {class_name}(Agent):
    """Plugin: {description}"""

    def __init__(self, agent_id: str = "") -> None:
        metadata = AgentMetadata(
            agent_id=agent_id,
            name="{name}",
            version="{version}",
            description="{description}",
            agent_type="plugin",
            capabilities={capabilities},
        )
        super().__init__(metadata=metadata)
'''

# Skill template
SKILL_TEMPLATE = '''from __future__ import annotations

from typing import Any

from app.agents.base import Agent, AgentMetadata


class {class_name}(Agent):
    """Skill: {description}"""

    name = "{name}"
    version = "{version}"
    description = "{description}"

    def execute(self, request: Any = None) -> dict[str, Any]:
        return {{"status": "ok", "result": "{name} executed"}}
'''

# Workflow template
WORKFLOW_TEMPLATE = '''name: {name}
version: "{version}"
type: workflow
description: "{description}"
steps:
{steps}
'''

# Pipeline template
PIPELINE_TEMPLATE = '''name: {name}
version: "{version}"
type: pipeline
description: "{description}"
stages:
{stages}
'''

# Knowledge Pack template
KNOWLEDGE_PACK_TEMPLATE = '''{{
    "name": "{name}",
    "version": "{version}",
    "type": "knowledge_pack",
    "domain": "{domain}",
    "description": "{description}",
    "entries": []
}}
'''

# Test Suite template
TEST_SUITE_TEMPLATE = '''from __future__ import annotations

import pytest


class Test{class_name}:
    """Tests for {target}."""

    def test_{test_name}_basic(self):
        assert True

    def test_{test_name}_edge_cases(self):
        assert True
'''

# Integration template
INTEGRATION_TEMPLATE = '''from __future__ import annotations

from typing import Any

from app.agents.base import Agent, AgentMetadata


class {class_name}(Agent):
    """Integration: {description}"""

    def __init__(self, agent_id: str = "") -> None:
        metadata = AgentMetadata(
            agent_id=agent_id,
            name="{name}",
            version="{version}",
            description="{description}",
            agent_type="integration",
            capabilities={capabilities},
        )
        super().__init__(metadata=metadata)
'''

# Documentation template
DOCUMENTATION_TEMPLATE = '''# {name}

{description}

## Overview

{description}

## Usage

```python
# Example usage
```

## API Reference

- `execute()`: Main entry point
- `status()`: Get current status
- `configure()`: Update configuration

## Version

{version}
'''
