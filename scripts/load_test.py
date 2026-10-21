# Generated from design: enterprise-voice-agent-system-design-v1.md (v1)
# Supporting design: enterprise-voice-agent-prd-v1.md (v1)
# Ticket: none
"""Bounded local-only smoke load test for the synthetic Compose conversation service."""

from __future__ import annotations

import argparse
import asyncio
import time
from urllib.parse import urlparse
import json

import httpx
from websockets.asyncio.client import connect
from websockets.exceptions import WebSocketException

CUSTOMER_ID = "CU-2291"
DEMO_OTP = "246810"
QUESTION = "Why did my EMI change? What would ₹50,000 prepaid save?"


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    return ordered[min(len(ordered) - 1, round((len(ordered) - 1) * fraction))]


async def run_one(client: httpx.AsyncClient, base_url: str, semaphore: asyncio.Semaphore) -> tuple[float, float, bool]:
    async with semaphore:
        started = time.perf_counter()
        try:
            session = (await client.post(f"{base_url}/api/session/start", json={"workflowId": "loan-servicing"})).raise_for_status().json()
            session_id = session["sessionId"]
            verify = await client.post("/api/session/verify", json={"sessionId": session_id, "customerId": CUSTOMER_ID, "otp": DEMO_OTP})
            verify.raise_for_status()
            socket_url = base_url.replace("http://", "ws://").replace("https://", "wss://") + f"/ws/conversations/{session_id}"
            first_response: float | None = None
            async with connect(socket_url, open_timeout=5, close_timeout=2) as socket:
                await socket.send(json.dumps({"type": "turn", "message": QUESTION, "workflowId": "loan-servicing", "channel": "TEXT"}))
                while True:
                    frame = json.loads(await socket.recv())
                    if frame["type"] in {"turn.progress", "assistant.delta"} and first_response is None:
                        first_response = (time.perf_counter() - started) * 1000
                    if frame["type"] == "error":
                        return (time.perf_counter() - started) * 1000, first_response or 0, False
                    if frame["type"] == "turn.completed":
                        break
            total = (time.perf_counter() - started) * 1000
            return total, first_response or total, True
        except (httpx.HTTPError, WebSocketException, OSError, TimeoutError):
            return (time.perf_counter() - started) * 1000, 0, False


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8000", help="Local conversation API base URL")
    parser.add_argument("--requests", type=int, default=20, help="Total synthetic demo turns (1–500)")
    parser.add_argument("--concurrency", type=int, default=5, help="Parallel local sessions (1–50)")
    args = parser.parse_args()
    parsed = urlparse(args.url)
    if parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        parser.error("For safety, this load test only targets localhost")
    if not 1 <= args.requests <= 500 or not 1 <= args.concurrency <= 50:
        parser.error("Use 1–500 requests and concurrency from 1–50")

    semaphore = asyncio.Semaphore(args.concurrency)
    async with httpx.AsyncClient(base_url=args.url, timeout=20) as client:
        results = await asyncio.gather(*(run_one(client, args.url, semaphore) for _ in range(args.requests)))
    durations = [duration for duration, _, _ in results]
    first_responses = [duration for _, duration, _ in results if duration > 0]
    failures = sum(not success for _, _, success in results)
    print(f"Requests: {args.requests}; concurrency: {args.concurrency}; failures: {failures}")
    print(f"First response ms — p50: {percentile(first_responses, .50):.0f}; p95: {percentile(first_responses, .95):.0f}; p99: {percentile(first_responses, .99):.0f}")
    print(f"Full turn ms — p50: {percentile(durations, .50):.0f}; p95: {percentile(durations, .95):.0f}; p99: {percentile(durations, .99):.0f}")
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
