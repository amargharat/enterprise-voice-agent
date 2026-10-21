# Generated from design: tool-platform-component-design-v1.md (v1)
# Supporting design: enterprise-voice-agent-system-design-v1.md (v1), tool-platform-enterprise-systems-integration-design-v1.md (v1)
# Ticket: none
"""Declarative, typed gateway: workflow authorization, trusted identity, resilience, and evidence."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import random
import re
import time
import uuid
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field
from pydantic import ValidationError
from redis.exceptions import RedisError

from .response_models import validate_tool_output
from .session_store import state
from .telemetry import current_traceparent

REGISTRY_PATH = Path(__file__).with_name("tool_registry.json")


class TurnContext(BaseModel):
    session_id: str
    turn_id: str
    customer_id: str
    workflow_id: str
    scopes: frozenset[str]
    deadline: datetime


class ToolCall(BaseModel):
    model_config = ConfigDict(extra="forbid")
    call_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class EvidenceRecord(BaseModel):
    model_config = ConfigDict(alias_generator=lambda value: re.sub(r"_([a-z])", lambda match: match.group(1).upper(), value), populate_by_name=True)
    system: str
    operation: str
    request_id: str
    correlation_id: str
    fetched_at: datetime
    latency_ms: int
    stale: bool = False
    source_ids: list[str] = Field(default_factory=list)


class ToolError(BaseModel):
    code: str
    retryable: bool
    message: str


class ToolResult(BaseModel):
    call_id: str
    status: Literal["OK", "STALE", "ERROR"]
    data: Any = None
    evidence: EvidenceRecord | None = None
    error: ToolError | None = None


class ToolGatewayError(RuntimeError):
    """A typed, classified failure raised at the tool boundary."""

    def __init__(self, code: str, message: str, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable


class CircuitBreaker:
    def __init__(self) -> None:
        self.failures: dict[str, deque[float]] = defaultdict(deque)
        self.open_until: dict[str, float] = {}

    def permit(self, system: str) -> bool:
        now = time.monotonic()
        if self.open_until.get(system, 0) > now:
            return False
        if self.open_until.get(system, 0):
            self.open_until.pop(system, None)
        return True

    def record(self, system: str, failed: bool) -> None:
        now = time.monotonic()
        window = self.failures[system]
        while window and now - window[0] > 30:
            window.popleft()
        if failed:
            window.append(now)
        if len(window) >= 10 and sum(now - value <= 30 for value in window) >= 5:
            self.open_until[system] = now + 15

    def state(self, system: str) -> str:
        return "OPEN" if self.open_until.get(system, 0) > time.monotonic() else "CLOSED"


class ToolRegistry:
    def __init__(self, path: Path = REGISTRY_PATH) -> None:
        self.config = json.loads(path.read_text(encoding="utf-8"))
        self.tools = self.config["tools"]
        self.workflows = self.config["workflows"]
        self.validate()

    def validate(self) -> None:
        if not self.tools or not self.workflows:
            raise ValueError("RegistryConfigInvalid: tool and workflow definitions are required")
        for workflow_id, workflow in self.workflows.items():
            for name in workflow["tools"]:
                if name not in self.tools:
                    raise ValueError(f"RegistryConfigInvalid: {workflow_id} references unknown tool {name}")
        for name, tool in self.tools.items():
            if tool["mode"] not in {"read", "write"} or tool["method"] not in {"GET", "POST"}:
                raise ValueError(f"RegistryConfigInvalid: invalid mode/method on {name}")
            if "customer_id" in tool.get("arguments", {}):
                raise ValueError(f"RegistryConfigInvalid: identity is context-only on {name}")

    def list_tools(self, workflow_id: str) -> list[dict[str, Any]]:
        workflow = self.workflows.get(workflow_id)
        if not workflow:
            raise ToolGatewayError("WorkflowNotFound", f"Unknown workflow: {workflow_id}")
        return [{"name": name, **self.tools[name]} for name in workflow["tools"]]

    def scopes_for(self, workflow_id: str) -> frozenset[str]:
        workflow = self.workflows.get(workflow_id)
        if not workflow:
            raise ToolGatewayError("WorkflowNotFound", f"Unknown workflow: {workflow_id}")
        return frozenset(self.tools[name]["scope"] for name in workflow["tools"])


class ToolGateway:
    def __init__(self, registry: ToolRegistry | None = None) -> None:
        self.registry = registry or ToolRegistry()
        self.breaker = CircuitBreaker()
        self.base_url = os.getenv("MOCK_ENTERPRISE_URL", "").rstrip("/")
        self.service_token = os.getenv("MOCK_SERVICE_TOKEN", "local-demo-service")
        self.timeout_scale = float(os.getenv("TOOL_TIMEOUT_SCALE", "1"))
        self.failure_override: dict[str, bool] = {}

    @staticmethod
    def _validate_arguments(arguments: dict[str, Any], definition: dict[str, Any], path: str) -> None:
        if "customer_id" in arguments or "customerId" in arguments:
            raise ToolGatewayError("ArgumentValidationError", "Customer identity is supplied by the verified session")
        schemas = definition.get("arguments", {})
        path_fields = set(re.findall(r"\{([A-Za-z][A-Za-z0-9]*)\}", path)) - {"customerId"}
        allowed = set(schemas) | path_fields
        extras = set(arguments) - allowed
        if extras:
            raise ToolGatewayError("ArgumentValidationError", f"Unexpected tool arguments: {', '.join(sorted(extras))}")
        for key, kind in schemas.items():
            value = arguments.get(key)
            required = kind == "required" or key in path_fields
            if required and (value is None or value == ""):
                raise ToolGatewayError("ArgumentValidationError", f"Missing required argument: {key}")
            if value is None:
                continue
            if kind in {"loan-id", "card-id", "required", "optional"} and not isinstance(value, str):
                raise ToolGatewayError("ArgumentValidationError", f"Argument {key} must be text")
            if kind == "integer" and (not isinstance(value, int) or isinstance(value, bool) or value < 1):
                raise ToolGatewayError("ArgumentValidationError", f"Argument {key} must be a positive integer")

    async def execute_many(self, calls: list[ToolCall], ctx: TurnContext, fallback: dict[str, Any] | None = None) -> list[ToolResult]:
        if len(calls) > 8:
            raise ToolGatewayError("TooManyCalls", "At most eight tools may run in one turn")
        if datetime.now(timezone.utc) >= ctx.deadline:
            raise ToolGatewayError("DeadlineExceeded", "Turn deadline passed before tool dispatch", True)
        allowed = set(self.registry.workflows.get(ctx.workflow_id, {}).get("tools", []))
        async def execute(call: ToolCall) -> ToolResult:
            if call.tool_name not in allowed:
                raise ToolGatewayError("ToolNotAllowed", f"{call.tool_name} is not enabled for {ctx.workflow_id}")
            definition = self.registry.tools[call.tool_name]
            if definition["mode"] != "read":
                raise ToolGatewayError("ToolNotAllowed", "Write tools require the confirmation gate")
            self._validate_arguments(call.arguments, definition, definition["path"])
            if definition["scope"] not in ctx.scopes:
                raise ToolGatewayError("ScopeDenied", "The verified session lacks the required tool scope")
            if self.failure_override.get(definition["system"].lower(), False):
                return ToolResult(call_id=call.call_id, status="ERROR", error=ToolError(code="UpstreamUnavailable", retryable=True, message="The connected system is unavailable"))
            return await self._execute_one(call, definition, ctx, (fallback or {}).get(call.call_id))
        return await asyncio.gather(*(execute(call) for call in calls))

    async def _execute_one(self, call: ToolCall, definition: dict[str, Any], ctx: TurnContext, fallback_data: Any) -> ToolResult:
        system = definition["system"]
        if not self.breaker.permit(system):
            return ToolResult(call_id=call.call_id, status="ERROR", error=ToolError(code="CircuitOpen", retryable=True, message=f"{system} is temporarily unavailable"))
        started = time.perf_counter()
        request_id = str(uuid.uuid4())
        fetched_at = datetime.now(timezone.utc)
        url_path = definition["path"]
        args = {**call.arguments}
        for match in re.findall(r"\{([A-Za-z][A-Za-z0-9]*)\}", url_path):
            if match == "customerId":
                args[match] = ctx.customer_id
            elif match not in args:
                raise ToolGatewayError("ArgumentValidationError", f"Missing required argument: {match}")
            url_path = url_path.replace("{" + match + "}", str(args.pop(match)))
        if "customerId" in call.arguments:
            raise ToolGatewayError("ArgumentValidationError", "Customer identity is supplied by the verified session")
        query = {key: value for key, value in args.items() if value is not None}
        if "customerId" not in url_path:
            query["customerId"] = ctx.customer_id
        cache_ttl = int(definition.get("cache_ttl_s", 0))
        cache_key = hashlib.sha256(json.dumps({"tool": call.tool_name, "customer": ctx.customer_id, "args": call.arguments}, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
        if cache_ttl:
            try:
                cached = await state.get_tool_cache(cache_key)
            except RedisError:
                cached = None
            if cached:
                elapsed = round((time.perf_counter() - started) * 1000)
                return ToolResult(
                    call_id=call.call_id, status="OK", data=cached["data"],
                    evidence=EvidenceRecord(system=system, operation=f"{definition['method']} {url_path} (cache)", request_id=request_id, correlation_id=ctx.turn_id, fetched_at=datetime.fromisoformat(cached["fetched_at"]), latency_ms=elapsed, stale=False, source_ids=self.source_ids(cached["data"])),
                )
        if not self.base_url:
            await asyncio.sleep(random.uniform(.10, .30))
            data = fallback_data
            status = "OK"
        else:
            headers = {
                "Authorization": f"Bearer {self.service_token}",
                "X-Mock-System": system,
                "X-Correlation-Id": ctx.turn_id,
                "X-Request-Id": request_id,
            }
            if traceparent := current_traceparent():
                headers["traceparent"] = traceparent
            timeout = definition["timeout_ms"] / 1000 * self.timeout_scale
            data = None
            status = "ERROR"
            for attempt in range(2):
                try:
                    async with httpx.AsyncClient(base_url=self.base_url, timeout=timeout) as client:
                        response = await client.request(definition["method"], url_path, params=query, headers=headers)
                    if response.status_code >= 500 or response.status_code == 429:
                        raise ToolGatewayError("UpstreamUnavailable", f"{system} service returned {response.status_code}", True)
                    if response.status_code >= 400:
                        raise ToolGatewayError("UpstreamRejected", f"{system} service rejected the request", False)
                    data = response.json()
                    status = "OK"
                    break
                except (httpx.TimeoutException, httpx.NetworkError, ToolGatewayError) as error:
                    if isinstance(error, ToolGatewayError) and not error.retryable:
                        raise
                    if attempt == 0:
                        await asyncio.sleep(random.uniform(.1, .4))
                    else:
                        self.breaker.record(system, True)
                        elapsed = round((time.perf_counter() - started) * 1000)
                        return ToolResult(
                            call_id=call.call_id, status="ERROR",
                            evidence=EvidenceRecord(system=system, operation=f"{definition['method']} {url_path}", request_id=request_id, correlation_id=ctx.turn_id, fetched_at=fetched_at, latency_ms=elapsed),
                            error=ToolError(code="UpstreamTimeout" if isinstance(error, httpx.TimeoutException) else "UpstreamUnavailable", retryable=True, message=f"{system} could not return this data"),
                        )
        self.breaker.record(system, status != "OK")
        elapsed = round((time.perf_counter() - started) * 1000)
        try:
            data = validate_tool_output(call.tool_name, data)
        except ValidationError:
            self.breaker.record(system, True)
            evidence = EvidenceRecord(system=system, operation=f"{definition['method']} {url_path}", request_id=request_id, correlation_id=ctx.turn_id, fetched_at=fetched_at, latency_ms=elapsed)
            return ToolResult(call_id=call.call_id, status="ERROR", evidence=evidence, error=ToolError(code="SchemaViolation", retryable=False, message=f"{system} returned data outside the expected schema"))
        if cache_ttl and status == "OK":
            try:
                await state.set_tool_cache(cache_key, {"data": data, "fetched_at": fetched_at.isoformat()}, cache_ttl)
            except RedisError:
                pass
        evidence = EvidenceRecord(
            system=system, operation=f"{definition['method']} {url_path}", request_id=request_id,
            correlation_id=ctx.turn_id, fetched_at=fetched_at, latency_ms=elapsed,
            source_ids=self.source_ids(data),
        )
        return ToolResult(call_id=call.call_id, status=status, data=data, evidence=evidence)

    async def execute_write(self, tool_name: str, arguments: dict[str, Any], ctx: TurnContext, idempotency_key: str) -> dict[str, Any]:
        """Execute a confirmed write; the caller must consume a server-issued confirmation first."""
        allowed = set(self.registry.workflows.get(ctx.workflow_id, {}).get("tools", []))
        definition = self.registry.tools.get(tool_name)
        if not definition or tool_name not in allowed or definition["mode"] != "write":
            raise ToolGatewayError("ToolNotAllowed", "This write tool is not enabled for the workflow")
        if definition["scope"] not in ctx.scopes:
            raise ToolGatewayError("ScopeDenied", "The verified session lacks the write scope")
        self._validate_arguments(arguments, definition, definition["path"])
        if not self.base_url:
            return {"requestId": f"SR-{uuid.uuid4().hex[:6].upper()}", "status": "OPEN", "type": arguments["type"], "createdAt": datetime.now(timezone.utc).isoformat(), "replayed": False}
        request_id = str(uuid.uuid4())
        headers = {
            "Authorization": f"Bearer {self.service_token}",
            "X-Mock-System": definition["system"],
            "X-Correlation-Id": ctx.turn_id,
            "X-Request-Id": request_id,
            "Idempotency-Key": idempotency_key,
        }
        if traceparent := current_traceparent():
            headers["traceparent"] = traceparent
        body = {**arguments, "customerId": ctx.customer_id, "confirmedAt": datetime.now(timezone.utc).isoformat(), "sourceCorrelationId": ctx.turn_id}
        timeout = definition["timeout_ms"] / 1000 * self.timeout_scale
        for attempt in range(2):
            try:
                async with httpx.AsyncClient(base_url=self.base_url, timeout=timeout) as client:
                    response = await client.post(definition["path"], json=body, headers=headers)
                if response.status_code >= 500 or response.status_code == 429:
                    raise ToolGatewayError("UpstreamUnavailable", "Service Operations is temporarily unavailable", True)
                if response.status_code >= 400:
                    raise ToolGatewayError("BusinessRuleRejected", "Service Operations rejected this request")
                self.breaker.record(definition["system"], False)
                return response.json()
            except (httpx.TimeoutException, httpx.NetworkError, ToolGatewayError) as error:
                if isinstance(error, ToolGatewayError) and not error.retryable:
                    raise
                if attempt == 0:
                    await asyncio.sleep(random.uniform(.1, .4))
                    continue
                self.breaker.record(definition["system"], True)
                raise ToolGatewayError("OutcomeUnknown", "The request outcome is not confirmed; retry with the same idempotency key", True) from error

    @staticmethod
    def source_ids(data: Any) -> list[str]:
        if isinstance(data, dict):
            identifiers = [str(data[key]) for key in ("loanId", "cardId", "paymentId", "ruleId", "requestId", "transactionId") if data.get(key)]
            for key in ("loans", "payments", "rules", "transactions"):
                if isinstance(data.get(key), list):
                    identifiers.extend(ToolGateway.source_ids(item) for item in data[key])
            return [identifier for item in identifiers for identifier in (item if isinstance(item, list) else [item])]
        if isinstance(data, list):
            return [str(row.get("paymentId") or row.get("transactionId")) for row in data if isinstance(row, dict) and (row.get("paymentId") or row.get("transactionId"))]
        return []


gateway = ToolGateway()
