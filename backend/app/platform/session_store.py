# Generated from design: enterprise-voice-agent-system-design-v1.md (v1)
# Supporting design: enterprise-voice-agent-data-design-v1.md (v1)
# Ticket: none
"""Redis-backed conversation and confirmation state with a local test fallback."""

from __future__ import annotations

import json
import os
from typing import Any

from redis.asyncio import Redis
from redis.exceptions import RedisError

SESSION_TTL_SECONDS = 30 * 60
CONFIRMATION_TTL_SECONDS = 5 * 60


class SessionStore:
    def __init__(self) -> None:
        self._redis: Redis | None = None
        self._local_sessions: dict[str, dict[str, Any]] = {}
        self._local_confirmations: dict[str, dict[str, Any]] = {}
        self._local_action_results: dict[str, dict[str, Any]] = {}
        self._local_tool_cache: dict[str, Any] = {}

    async def connect(self) -> None:
        url = os.getenv("REDIS_URL")
        if url:
            self._redis = Redis.from_url(url, decode_responses=True, socket_connect_timeout=2)
            await self._redis.ping()

    async def close(self) -> None:
        if self._redis:
            await self._redis.aclose()
            self._redis = None

    async def save_session(self, session_id: str, session: dict[str, Any]) -> None:
        payload = json.dumps(session, separators=(",", ":"))
        if self._redis:
            await self._redis.setex(f"session:{session_id}", SESSION_TTL_SECONDS, payload)
        else:
            self._local_sessions[session_id] = session

    async def get_session(self, session_id: str) -> dict[str, Any] | None:
        if self._redis:
            payload = await self._redis.get(f"session:{session_id}")
            if payload:
                await self._redis.expire(f"session:{session_id}", SESSION_TTL_SECONDS)
            return json.loads(payload) if payload else None
        return self._local_sessions.get(session_id)

    async def save_confirmation(self, token: str, action: dict[str, Any]) -> None:
        payload = json.dumps(action, separators=(",", ":"))
        if self._redis:
            await self._redis.setex(f"confirm:{token}", CONFIRMATION_TTL_SECONDS, payload)
        else:
            self._local_confirmations[token] = action

    async def get_confirmation(self, token: str) -> dict[str, Any] | None:
        if self._redis:
            payload = await self._redis.get(f"confirm:{token}")
            return json.loads(payload) if payload else None
        return self._local_confirmations.get(token)

    async def consume_confirmation(self, token: str) -> dict[str, Any] | None:
        if self._redis:
            payload = await self._redis.getdel(f"confirm:{token}")
            return json.loads(payload) if payload else None
        return self._local_confirmations.pop(token, None)

    async def get_action_result(self, token: str) -> dict[str, Any] | None:
        if self._redis:
            payload = await self._redis.get(f"action-result:{token}")
            return json.loads(payload) if payload else None
        return self._local_action_results.get(token)

    async def save_action_result(self, token: str, result: dict[str, Any]) -> None:
        payload = json.dumps(result, separators=(",", ":"))
        if self._redis:
            await self._redis.setex(f"action-result:{token}", 24 * 60 * 60, payload)
        else:
            self._local_action_results[token] = result

    async def get_tool_cache(self, key: str) -> Any:
        if self._redis:
            payload = await self._redis.get(f"cache:{key}")
            return json.loads(payload) if payload else None
        return self._local_tool_cache.get(key)

    async def set_tool_cache(self, key: str, value: Any, ttl_seconds: int) -> None:
        payload = json.dumps(value, separators=(",", ":"), default=str)
        if self._redis:
            await self._redis.setex(f"cache:{key}", ttl_seconds, payload)
        else:
            self._local_tool_cache[key] = json.loads(payload)


state = SessionStore()
