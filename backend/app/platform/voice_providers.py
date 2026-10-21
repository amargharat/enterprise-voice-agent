# Generated from design: enterprise-voice-agent-system-design-v1.md (v1)
# Supporting design: ADR-002-cascaded-stt-llm-tts-for-voice.md (v1)
# Ticket: none
"""Provider-neutral HTTP adapters for cascaded speech recognition and synthesis."""

from __future__ import annotations

import os
from dataclasses import dataclass

import httpx


@dataclass(frozen=True)
class VoiceProviderStatus:
    stt_configured: bool
    tts_configured: bool


class VoiceProviderAdapter:
    """Minimal streaming-gateway seam; configure vendor-compatible endpoints via environment."""

    def __init__(self) -> None:
        self.stt_endpoint = os.getenv("STT_ENDPOINT", "")
        self.tts_endpoint = os.getenv("TTS_ENDPOINT", "")
        self.api_key = os.getenv("VOICE_PROVIDER_API_KEY", "")

    @property
    def status(self) -> VoiceProviderStatus:
        return VoiceProviderStatus(bool(self.stt_endpoint), bool(self.tts_endpoint))

    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}

    async def transcribe(self, audio: bytes, mime_type: str) -> str:
        if not self.stt_endpoint:
            raise RuntimeError("Speech-to-text provider is not configured")
        async with httpx.AsyncClient(timeout=httpx.Timeout(15)) as client:
            response = await client.post(self.stt_endpoint, content=audio, headers={**self.headers(), "Content-Type": mime_type})
            response.raise_for_status()
        transcript = response.json().get("text")
        if not isinstance(transcript, str) or not transcript.strip():
            raise ValueError("Speech provider returned an empty transcript")
        return transcript.strip()

    async def synthesize(self, text: str, voice: str = "en-IN") -> bytes:
        if not self.tts_endpoint:
            raise RuntimeError("Text-to-speech provider is not configured")
        async with httpx.AsyncClient(timeout=httpx.Timeout(15)) as client:
            response = await client.post(self.tts_endpoint, json={"text": text, "voice": voice}, headers=self.headers())
            response.raise_for_status()
        return response.content


voice_provider = VoiceProviderAdapter()
