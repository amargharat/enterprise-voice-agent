# Generated from design: enterprise-voice-agent-system-design-v1.md (v1)
# Supporting design: tool-platform-enterprise-systems-integration-design-v1.md (v1)
# Ticket: none
"""Prometheus metrics and optional OTLP/OpenTelemetry tracing setup."""

from __future__ import annotations

import os

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from prometheus_client import Counter, Histogram, make_asgi_app

TOOL_CALLS = Counter("voice_agent_tool_calls_total", "Tool calls by system and outcome", ["system", "tool", "status"])
TOOL_LATENCY = Histogram("voice_agent_tool_latency_seconds", "Tool service latency by system", ["system", "tool"], buckets=(.05, .1, .25, .5, 1, 2, 3.5, 5))
TURN_CALLS = Counter("voice_agent_turns_total", "Conversation turns by channel and outcome", ["channel", "outcome"])
TURN_LATENCY = Histogram("voice_agent_turn_latency_seconds", "Total turn latency by channel", ["channel"], buckets=(.1, .25, .5, 1, 2, 4, 6, 10, 15))
TURN_STAGE_LATENCY = Histogram("voice_agent_turn_stage_latency_seconds", "Turn stage latency by channel and stage", ["channel", "stage"], buckets=(.025, .05, .1, .25, .5, 1, 2, 4, 6, 10, 15))
ACTION_CALLS = Counter("voice_agent_actions_total", "Confirmed actions by type and result", ["type", "outcome"])


def configure_tracing() -> None:
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", "")
    if not endpoint or isinstance(trace.get_tracer_provider(), TracerProvider):
        return
    provider = TracerProvider(resource=Resource.create({"service.name": "enterprise-voice-agent"}))
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
    trace.set_tracer_provider(provider)


def current_traceparent() -> str | None:
    context = trace.get_current_span().get_span_context()
    if not context.is_valid:
        return None
    return f"00-{context.trace_id:032x}-{context.span_id:016x}-{context.trace_flags:02x}"


prometheus_app = make_asgi_app()
tracer = trace.get_tracer("enterprise-voice-agent")
