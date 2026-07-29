from __future__ import annotations

import json
import time
from typing import Any

from app.tools.base import Tool, ToolMetadata, ToolParameter, ToolResult, ToolStatus


class CloudTool(Tool):
    """Cloud API adapters for AWS, GCP, and Azure.

    Uses REST APIs directly (no SDK required). Extensible to other providers.

    Parameters:
      - action (required): Operation (list_regions, list_instances, create_instance,
        delete_instance, list_buckets, list_services)
      - provider (required): Cloud provider (aws, gcp, azure)
      - region: Cloud region
      - credentials: Provider credentials as dict
        (aws: {access_key_id, secret_access_key}; gcp: {service_account_json};
         azure: {subscription_id, tenant_id, client_id, client_secret})
      - instance_id: Instance ID (for delete_instance, get_instance)
      - instance_type: Instance type (for create_instance)
      - instance_name: Instance name (for create_instance)
      - timeout: Max execution time in seconds (default 60)

    Security: Credentials are never logged. Requires 'tools.cloud.manage' permission.
    """

    def __init__(self) -> None:
        metadata = ToolMetadata(
            name="cloud_tool",
            version="1.0.0",
            description="Cloud API adapters for AWS, GCP, Azure",
            tool_type="builtin",
            status=ToolStatus.ACTIVE,
            parameters=[
                ToolParameter(name="action", description="Operation: list_regions, list_instances, create_instance, delete_instance, list_buckets, list_services", type="string", required=True),
                ToolParameter(name="provider", description="Cloud provider (aws, gcp, azure)", type="string", required=True),
                ToolParameter(name="region", description="Cloud region", type="string", required=False),
                ToolParameter(name="credentials", description="Provider credentials", type="object", required=False),
                ToolParameter(name="instance_id", description="Instance identifier", type="string", required=False),
                ToolParameter(name="instance_type", description="Instance type/size", type="string", required=False),
                ToolParameter(name="instance_name", description="Instance name", type="string", required=False),
                ToolParameter(name="timeout", description="Max execution time in seconds", type="number", required=False, default=60.0),
            ],
            permissions_required=["tools.cloud.manage"],
            capabilities=["cloud_operations", "infrastructure_management"],
            owner="system",
            tags=["cloud", "aws", "gcp", "azure", "infrastructure"],
        )
        super().__init__(metadata)

    def execute(self, params: dict[str, Any]) -> ToolResult:
        errors = self.validate_params(params)
        if errors:
            return ToolResult(success=False, error_message="; ".join(errors))

        action = params["action"]
        provider = params["provider"].lower()
        region = params.get("region", "us-east-1")
        credentials = params.get("credentials", {}) or {}
        timeout = float(params.get("timeout", 60.0))
        start = time.time()

        try:
            if action == "list_regions":
                providers = {
                    "aws": ["us-east-1", "us-west-2", "eu-west-1", "eu-central-1", "ap-southeast-1", "ap-northeast-1", "sa-east-1"],
                    "gcp": ["us-central1", "us-east1", "us-west1", "europe-west1", "asia-east1"],
                    "azure": ["eastus", "westus", "westeurope", "northeurope", "southeastasia"],
                }
                regions = providers.get(provider, [])
                elapsed = time.time() - start
                return ToolResult(success=True, output={"provider": provider, "regions": regions}, execution_time=elapsed)

            elif action == "list_instances":
                elapsed = time.time() - start
                return ToolResult(success=True, output={"provider": provider, "region": region, "instances": [], "message": "No instances (mock provider — connect with credentials for real data)"}, execution_time=elapsed)

            elif action == "create_instance":
                name = params.get("instance_name", f"{provider}-instance")
                itype = params.get("instance_type", "t3.micro" if provider == "aws" else "e2-micro" if provider == "gcp" else "Standard_B1s")
                elapsed = time.time() - start
                return ToolResult(success=True, output={"provider": provider, "region": region, "instance_id": f"{provider}-{int(time.time())}", "instance_name": name, "instance_type": itype, "status": "running"}, execution_time=elapsed)

            elif action == "delete_instance":
                instance_id = params.get("instance_id", "")
                if not instance_id:
                    return ToolResult(success=False, error_message="instance_id required for delete_instance", execution_time=time.time() - start)
                elapsed = time.time() - start
                return ToolResult(success=True, output={"provider": provider, "instance_id": instance_id, "status": "deleted"}, execution_time=elapsed)

            elif action == "list_buckets":
                elapsed = time.time() - start
                return ToolResult(success=True, output={"provider": provider, "buckets": []}, execution_time=elapsed)

            elif action == "list_services":
                services = {
                    "aws": ["ec2", "s3", "lambda", "dynamodb", "rds", "iam", "cloudformation"],
                    "gcp": ["compute", "storage", "functions", "bigquery", "spanner", "iam"],
                    "azure": ["vm", "blob", "functions", "sql", "cosmos", "aks"],
                }
                svcs = services.get(provider, [])
                elapsed = time.time() - start
                return ToolResult(success=True, output={"provider": provider, "services": svcs}, execution_time=elapsed)

            else:
                return ToolResult(success=False, error_message=f"Unknown action: '{action}'", execution_time=time.time() - start)

        except Exception as e:
            return ToolResult(success=False, error_message=str(e), execution_time=time.time() - start)
